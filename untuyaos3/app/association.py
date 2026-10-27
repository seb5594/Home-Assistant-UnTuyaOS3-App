"""Verify an actual Wi-Fi association before upstream is allowed to start DHCP."""
from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

from wifi import Adapter, same_device


class AssociationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AccessPoint:
    ssid: str
    bssid: str
    frequency: int
    signal: float


def access_points(output, ssid):
    """Keep only open BSS entries for the SSID already selected by upstream."""
    points = []
    for block in re.split(r"(?m)^BSS ", output)[1:]:
        mac = re.match(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})(?:\(|\s|$)", block)
        name = re.search(r"(?m)^\s*SSID: (.*)$", block)
        freq = re.search(r"(?m)^\s*freq: ([0-9]+)(?:\.0+)?\s*$", block)
        signal = re.search(r"(?m)^\s*signal: (-?[0-9]+(?:\.[0-9]+)?) dBm", block)
        encrypted = re.search(r"(?m)^\s*(?:RSN:|WPA:|capability:.*\bPrivacy\b)", block)
        if mac and name and name[1] == ssid and freq and not encrypted:
            points.append(AccessPoint(ssid, mac[1].lower(), int(freq[1]), float(signal[1]) if signal else float("-inf")))
    return sorted(points, key=lambda point: (-point.signal, point.bssid))


def link_matches(output, point):
    mac = re.search(r"(?m)^Connected to ([0-9a-fA-F:]{17})(?:\s|$)", output)
    name = re.search(r"(?m)^\s*SSID: (.*)$", output)
    freq = re.search(r"(?m)^\s*freq: ([0-9]+)(?:\.0+)?\s*$", output)
    return bool(mac and mac[1].lower() == point.bssid and name and name[1] == point.ssid
                and freq and int(freq[1]) == point.frequency)


def command(*args, timeout=8):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, "LC_ALL": "C"})
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired as exc:
        output = "".join(part.decode("utf-8", "replace") if isinstance(part, bytes) else (part or "")
                         for part in (exc.stdout, exc.stderr))
        return 124, f"Command timed out after {timeout}s. {output}"
    except OSError as exc:
        raise AssociationError(f"Cannot execute {args[0]}: {exc}") from exc


def report(label, result, log):
    code, output = result
    log(f"{label}: exit={code}; {output.strip() or '(no output)'}")


def diagnostics(adapter, log, run):
    driver = Path(f"/sys/class/net/{adapter.name}/device/driver")
    log(f"Adapter={adapter.name}; radio={adapter.phy}; driver={driver.resolve().name if driver.exists() else 'unknown'}; "
        f"kernel={platform.release()}")
    for label, args in (("Interface", ("iw", "dev", adapter.name, "info")),
                        ("Power saving (read only)", ("iw", "dev", adapter.name, "get", "power_save")),
                        ("Regulatory information (read only)", ("iw", "reg", "get"))):
        report(label, run(*args), log)


def associate(adapter, ssid, log=print, run=command, guard=same_device, wait=time.sleep):
    guard(adapter)
    diagnostics(adapter, log, run)
    code, scan = run("iw", "dev", adapter.name, "scan", "dump")
    if code:
        report("Scan cache", (code, scan), log)
        raise AssociationError("Cannot inspect the selected AP before connecting; DHCP was not started")
    points = access_points(scan, ssid)
    if not points:
        # The kernel drops stale BSS entries from the dump after ~30 s, so ask the radio for a fresh look.
        code, scan = run("iw", "dev", adapter.name, "scan", "ssid", ssid, timeout=20)
        if code:
            report("Directed scan", (code, scan), log)
        points = access_points(scan, ssid) if not code else []
    if not points:
        raise AssociationError(f"Selected open AP {ssid!r} is no longer visible; put the device back into AP pairing mode and start a new session")
    point = points[0]
    for attempt in range(1, 4):
        guard(adapter)
        log(f"Association attempt {attempt}/3: SSID={point.ssid!r}; BSSID={point.bssid}; "
            f"frequency={point.frequency} MHz; signal={point.signal:g} dBm")
        report("Disconnect previous attempt", run("iw", "dev", adapter.name, "disconnect"), log)
        # iw -w may exit zero even after a failed connect event. Its status is
        # diagnostic only: require a matching live BSSID, SSID and frequency.
        result = run("iw", "dev", adapter.name, "connect", "-w", point.ssid,
                     str(point.frequency), point.bssid, "auth", "open", timeout=15)
        report("Connect event", result, log)
        for check in range(3):
            guard(adapter)
            code, link = run("iw", "dev", adapter.name, "link")
            report(f"Link verification {check + 1}/3", (code, link), log)
            if code == 0 and link_matches(link, point):
                log("Wi-Fi association verified against the selected AP; DHCP may now start")
                return
            if check < 2:
                wait(1)
        if attempt < 3:
            log("Association not established. Retrying only the same selected SSID; DHCP remains blocked")
            wait(2)
            guard(adapter)
            code, scan = run("iw", "dev", adapter.name, "scan", "freq", str(point.frequency), timeout=20)
            if code:
                report("Target-channel rescan", (code, scan), log)
            else:
                points = access_points(scan, ssid)
                if not points:
                    raise AssociationError(f"Selected AP {ssid!r} disappeared on {point.frequency} MHz; restore AP pairing mode and start a new session. DHCP was not started")
                point = points[0]
    diagnostics(adapter, log, run)
    raise AssociationError("Wi-Fi association failed after 3 attempts; DHCP was not started and no firmware was transferred. "
                           "Keep the lamp powered in AP pairing mode and close to the adapter. If this repeats, "
                           "try an AP-capable USB Wi-Fi adapter by selecting its interface in both app configurations. "
                           "Review the driver, signal and connect events above")


def main():
    if len(sys.argv) != 3:
        raise AssociationError("Expected the approved Wi-Fi interface and selected SSID")
    name, ssid = sys.argv[1:]
    if name != os.environ.get("UNTUYAOS3_ALLOWED_IFACE") or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name):
        raise AssociationError("Unapproved Wi-Fi interface")
    phy = os.environ.get("UNTUYAOS3_ALLOWED_PHY", "")
    if not re.fullmatch(r"phy[0-9]+", phy):
        raise AssociationError("Missing approved radio identity")
    adapter = Adapter(name, phy, int(os.environ["UNTUYAOS3_ALLOWED_IFINDEX"]))
    associate(adapter, ssid, log=lambda text: print("[Wi-Fi] " + text, flush=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[Wi-Fi] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
