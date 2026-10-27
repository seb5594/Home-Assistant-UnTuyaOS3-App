"""Read-only discovery; host ownership checks run only in the temporary provisioner."""
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

NM = "org.freedesktop.NetworkManager"


class PreflightError(RuntimeError):
    pass


def command(*args):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=8,
                                env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError(f"Cannot execute {args[0]}: {exc}") from exc
    if result.returncode:
        raise PreflightError(f"{' '.join(args)} failed ({result.returncode}): "
                             f"{result.stderr.strip()} {result.stdout.strip()}")
    return result.stdout


def parse_interfaces(output):
    result, phy, current = [], None, None
    for line in output.splitlines():
        match = re.fullmatch(r"phy#(\d+)", line.strip())
        if match:
            phy = "phy" + match[1]
        elif line.strip().startswith("Interface "):
            name = line.strip().split(maxsplit=1)[1]
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name) or not phy:
                raise PreflightError("Unexpected iw interface name or radio")
            current = {"name": name, "phy": phy, "type": "unknown"}
            result.append(current)
        elif line.strip().startswith("type ") and current:
            current["type"] = line.strip().split(maxsplit=1)[1]
    return result


def supported_modes(output):
    match = re.search(r"Supported interface modes:\n((?:[ \t]+\*[^\n]*\n?)+)", output)
    return {s.strip() for s in re.findall(r"\*\s+([^\n]+)", match[1])} if match else set()


def bus(*args):
    """Read one NetworkManager value; method arguments and properties have different JSON shapes."""
    operation = args[0] if args else ""
    if operation == "call" and len(args) >= 5:
        context, signature = args[4], "o"
    elif operation == "get-property" and len(args) == 5:
        context = args[-1]
        signature = {"Managed": "b", "State": "u", "ActiveConnection": "o"}.get(context)
    else:
        raise PreflightError(f"Unsupported busctl read operation: {operation}")
    if signature is None:
        raise PreflightError(f"Unsupported NetworkManager property: {context}")
    output = command("busctl", "--system", "--json=short", "--timeout=5",
                     "--auto-start=no", "--allow-interactive-authorization=no", *args)
    try:
        reply = json.loads(output)
    except json.JSONDecodeError as exc:
        raise PreflightError(f"busctl {context}: invalid JSON response ({exc.msg})") from exc
    if not isinstance(reply, dict) or reply.get("type") != signature or "data" not in reply:
        raise PreflightError(f"busctl {context}: expected a typed '{signature}' response with data")
    value = reply["data"]
    if operation == "call":
        if not isinstance(value, list) or len(value) != 1:
            raise PreflightError(f"busctl {context}: expected exactly one method return argument")
        value = value[0]
    expected = {"b": bool, "u": int, "o": str}[signature]
    if type(value) is not expected:
        raise PreflightError(f"busctl {context}: expected {expected.__name__}, received {type(value).__name__}")
    if signature == "u" and not 0 <= value <= 0xffffffff:
        raise PreflightError(f"busctl {context}: unsigned integer outside the D-Bus range")
    if signature == "o" and not re.fullmatch(r"/(?:[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*)?", value):
        raise PreflightError(f"busctl {context}: invalid D-Bus object path")
    return value


def nm_unmanaged(name):
    path = bus("call", NM, "/org/freedesktop/NetworkManager", NM, "GetDeviceByIpIface", "s", name)
    iface = NM + ".Device"
    managed = bus("get-property", NM, path, iface, "Managed")
    state = bus("get-property", NM, path, iface, "State")
    active = bus("get-property", NM, path, iface, "ActiveConnection")
    if managed is not False or state != 10 or active != "/":
        raise PreflightError(f"{name}: NetworkManager owns/activates this device "
                             f"(managed={managed}, state={state}, active={active}). "
                             "Reserve a dedicated adapter as unmanaged on the host first.")


def radio_unblocked(phy):
    entries = [p for p in Path("/sys/class/rfkill").glob("rfkill*")
               if (p / "name").read_text().strip() == phy]
    if not entries:
        raise PreflightError(f"{phy}: cannot verify rfkill state; refusing to change radio state")
    for entry in entries:
        if any((entry / key).read_text().strip() != "0" for key in ("soft", "hard")):
            raise PreflightError(f"{phy}: radio is soft/hard blocked; unblock only the dedicated radio on the host")


@dataclass
class Adapter:
    name: str
    phy: str
    ifindex: int

    def as_dict(self):
        return asdict(self)


def inspect(candidate, all_interfaces, run=command, ownership=None, rfkill=None, allow_up=False):
    name, phy = candidate["name"], candidate["phy"]
    if sum(i["phy"] == phy for i in all_interfaces) != 1:
        raise PreflightError(f"{name}: shared radio {phy}; other virtual interfaces exist")
    if candidate["type"] != "managed":
        raise PreflightError(f"{name}: current interface type is {candidate['type']}, expected managed/client")
    modes = supported_modes(run("iw", "phy", phy, "info"))
    if not {"AP", "managed"} <= modes:
        raise PreflightError(f"{name}/{phy}: AP and managed modes required; advertised modes: {sorted(modes)}")
    info = json.loads(run("ip", "-j", "address", "show", "dev", name))
    if len(info) != 1:
        raise PreflightError(f"{name}: interface disappeared")
    link = info[0]
    if (not allow_up and "UP" in link.get("flags", [])) or link.get("addr_info") or link.get("master"):
        raise PreflightError(f"{name}: in use (administratively UP, has addresses, or part of bridge/bond)")
    for family in ("-4", "-6"):
        routes = json.loads(run("ip", family, "-j", "route", "show", "table", "all"))
        if any(r.get("dev") == name or any(n.get("dev") == name for n in r.get("nexthops", [])) for r in routes):
            raise PreflightError(f"{name}: routes depend on this interface")
    if run("iw", "dev", name, "link").strip() != "Not connected.":
        raise PreflightError(f"{name}: wireless link active or indeterminate")
    if ownership:
        ownership(name)
    if rfkill:
        rfkill(phy)
    return Adapter(name, phy, link["ifindex"])


def discover(requested, log, host=False):
    interfaces = parse_interfaces(command("iw", "dev"))
    if not interfaces:
        raise PreflightError("No assigned wireless interface visible. Start the Wi-Fi Helper first and inspect both apps' Home Assistant Log tabs.")
    log("info", f"Discovered {len(interfaces)} wireless interface(s): {interfaces}")
    if requested != "auto" and requested not in [i["name"] for i in interfaces]:
        raise PreflightError(f"Configured interface {requested!r} does not exist")
    eligible = []
    for candidate in interfaces:
        if requested != "auto" and candidate["name"] != requested:
            continue
        try:
            adapter = inspect(candidate, interfaces, ownership=nm_unmanaged if host else None,
                              rfkill=radio_unblocked if host else None)
            eligible.append(adapter)
            log("info", f"Eligible: {adapter.as_dict()}; AP advertised, unused")
        except (PreflightError, OSError, ValueError, KeyError) as exc:
            log("warning", f"Rejected {candidate['name']}/{candidate['phy']}: {exc}")
    if not eligible:
        raise PreflightError("No free AP-capable Wi-Fi adapter passed all checks. No networking was changed. "
                             "See rejections above; never use Home Assistant's management Wi-Fi.")
    selected = sorted(eligible, key=lambda a: a.name)[0]
    log("info", f"Selected {selected.name} ({selected.phy}); AP advertised by driver, not a hardware AP test")
    return selected


def same_device(adapter):
    interfaces = parse_interfaces(command("iw", "dev"))
    info = json.loads(command("ip", "-j", "link", "show", "dev", adapter.name))
    if not any(i["name"] == adapter.name and i["phy"] == adapter.phy for i in interfaces) or not info or info[0]["ifindex"] != adapter.ifindex:
        raise PreflightError("Adapter removed/replaced; refusing to touch another device")


def cleanup(adapter, log):
    try:
        same_device(adapter)
    except (PreflightError, OSError, ValueError, KeyError) as exc:
        log("error", f"Cleanup refused: {exc}")
        return False
    ok = True
    for args in (("iw", "dev", adapter.name, "disconnect"),
                 ("ip", "link", "set", "dev", adapter.name, "down"),
                 ("ip", "-4", "address", "flush", "dev", adapter.name)):
        try:
            command(*args)
            log("info", "Cleanup: " + " ".join(args))
        except PreflightError as exc:
            log("warning" if args[0] == "iw" else "error", str(exc))
            if args[0] != "iw":
                ok = False
    return ok
