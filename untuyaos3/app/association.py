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
from supplicant import Control


class AssociationError(RuntimeError):
    """Association could not be verified; DHCP must not start."""
    pass


@dataclass(frozen=True)
class AccessPoint:
    """One open access point seen in a scan."""
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
    """True if `iw link` output describes exactly the access point the supplicant reports."""
    mac = re.search(r"(?m)^Connected to ([0-9a-fA-F:]{17})(?:\s|$)", output)
    name = re.search(r"(?m)^\s*SSID: (.*)$", output)
    freq = re.search(r"(?m)^\s*freq: ([0-9]+)(?:\.0+)?\s*$", output)
    return bool(mac and mac[1].lower() == point.bssid and name and name[1] == point.ssid
                and freq and int(freq[1]) == point.frequency)


def command(*args, timeout=8):
    """Run a fixed command, return (exit code, combined output); a timeout is reported as 124."""
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
    """Log a command result in one line."""
    code, output = result
    log(f"{label}: exit={code}; {output.strip() or '(no output)'}")


def diagnostics(adapter, log, run):
    """Log adapter, driver and read-only radio information to help with weak-signal reports."""
    driver = Path(f"/sys/class/net/{adapter.name}/device/driver")
    log(f"Adapter={adapter.name}; radio={adapter.phy}; driver={driver.resolve().name if driver.exists() else 'unknown'}; "
        f"kernel={platform.release()}")
    for label, args in (("Interface", ("iw", "dev", adapter.name, "info")),
                        ("Power saving (read only)", ("iw", "dev", adapter.name, "get", "power_save")),
                        ("Regulatory information (read only)", ("iw", "reg", "get"))):
        report(label, run(*args), log)


def associate(adapter, ssid, log=print, run=command, guard=same_device, wait=time.sleep,
              control=None, checks=45):
    """Join the open device AP through the private supplicant and verify the link independently.

    DHCP only starts once the supplicant reports COMPLETED *and* `iw` agrees on SSID, BSSID and
    frequency. The network entry is removed again if anything fails."""
    guard(adapter)
    if not ssid or len(ssid.encode("utf-8")) > 32 or any(ord(c) < 32 for c in ssid):
        raise AssociationError("Invalid selected SSID")
    diagnostics(adapter, log, run)
    code, scan = run("iw", "dev", adapter.name, "scan", "dump")
    points = access_points(scan, ssid) if code == 0 else []
    if not points:
        code, scan = run("iw", "dev", adapter.name, "scan", "ssid", ssid, timeout=20)
        points = access_points(scan, ssid) if code == 0 else []
    point = points[0] if points else None
    if point:
        log(f"Selected open AP: SSID={ssid!r}; BSSID={point.bssid}; frequency={point.frequency} MHz; signal={point.signal:g} dBm")
        if point.signal < -85:
            log("Weak received signal: check the computer's Wi-Fi antennas or choose another adapter. Distance alone does not establish good reception")
    else:
        log(f"Selected SSID {ssid!r} temporarily missing from scan; supplicant will rescan within the connection deadline")
    if control is None:
        raise AssociationError("Private supplicant control is missing; DHCP was not started")
    network = control.request("ADD_NETWORK")
    if not re.fullmatch(r"[0-9]+", network):
        raise AssociationError(f"Cannot create private Wi-Fi network: {network}")
    success = False
    def checked(message):
        reply = control.request(message)
        if reply != "OK":
            raise AssociationError(f"Supplicant rejected {message.split()[0]}: {reply}")
    try:
        # Hex encoding prevents SSID text from becoming a control command/config directive.
        settings = {"ssid": ssid.encode("utf-8").hex(), "key_mgmt": "NONE", "auth_alg": "OPEN", "scan_ssid": "1"}
        if point:
            settings["bssid"] = point.bssid
        for field, value in settings.items():
            checked(f"SET_NETWORK {network} {field} {value}")
        checked(f"SELECT_NETWORK {network}")
        last_state = None
        for check in range(checks):
            guard(adapter)
            status = dict(line.split("=", 1) for line in control.request("STATUS").splitlines() if "=" in line)
            state = status.get("wpa_state", "UNKNOWN")
            if state != last_state or check % 5 == 0:
                log(f"Association {check + 1}/{checks}: state={state}; selected SSID={ssid!r}; DHCP blocked until link verification")
                last_state = state
            if state == "COMPLETED" and status.get("ssid") == ssid:
                mac, frequency = status.get("bssid", "").lower(), status.get("freq", "")
                if re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", mac) and frequency.isdigit() and (point is None or mac == point.bssid):
                    live = AccessPoint(ssid, mac, int(frequency), point.signal if point else float("-inf"))
                    code, link = run("iw", "dev", adapter.name, "link")
                    report("Independent link verification", (code, link), log)
                    if code == 0 and link_matches(link, live):
                        success = True
                        log("Wi-Fi association verified against the selected AP; DHCP may now start")
                        return
            # Let nl80211 own association/retries; do not interrupt it with competing iw scans.
            if check + 1 < checks:
                wait(1)
        diagnostics(adapter, log, run)
        raise AssociationError("Wi-Fi association deadline reached; DHCP was not started and no firmware was transferred. "
                               "Restore the lamp's AP pairing mode, check antennas and reception, or select another adapter in the Web UI")
    finally:
        if not success:
            for message in (f"DISABLE_NETWORK {network}", f"REMOVE_NETWORK {network}"):
                try:
                    control.request(message)
                except OSError:
                    pass


def main():
    """Entry point called by the patched upstream connect script."""
    if len(sys.argv) != 3:
        raise AssociationError("Expected the approved Wi-Fi interface and selected SSID")
    name, ssid = sys.argv[1:]
    if name != os.environ.get("UNTUYAOS3_ALLOWED_IFACE") or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name):
        raise AssociationError("Unapproved Wi-Fi interface")
    phy = os.environ.get("UNTUYAOS3_ALLOWED_PHY", "")
    if not re.fullmatch(r"phy[0-9]+", phy):
        raise AssociationError("Missing approved radio identity")
    adapter = Adapter(name, phy, int(os.environ["UNTUYAOS3_ALLOWED_IFINDEX"]))
    path = os.environ.get("UNTUYAOS3_WPA_CONTROL")
    if not path:
        raise AssociationError("Missing private Wi-Fi controller")
    with Control(path) as control:
        associate(adapter, ssid, control=control, log=lambda text: print("[Wi-Fi] " + text, flush=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[Wi-Fi] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
