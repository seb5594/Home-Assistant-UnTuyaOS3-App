# Copy of shared/wifi.py, maintained by tools/sync_project.py. Edit the original.
"""Wi-Fi inspection helpers shared by both apps.

Discovery here only reads state (``iw``, ``ip``, sysfs, NetworkManager over busctl). The
only mutating function is :func:`cleanup`, which resets the one leased interface.
"""
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

NM = "org.freedesktop.NetworkManager"


class PreflightError(RuntimeError):
    """A safety check failed; nothing was changed on the host."""


def command(*args):
    """Run a fixed argument list (never a shell) with a timeout and return its stdout."""
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
    """Turn ``iw dev`` output into [{"name", "phy", "type"}, ...]; reject suspicious names."""
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
    """Interface modes (managed, AP, ...) advertised by ``iw phy <phy> info``."""
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
    """Require NetworkManager to have released the device (unmanaged and idle)."""
    path = bus("call", NM, "/org/freedesktop/NetworkManager", NM, "GetDeviceByIpIface", "s", name)
    iface = NM + ".Device"
    managed = bus("get-property", NM, path, iface, "Managed")
    state = bus("get-property", NM, path, iface, "State")
    active = bus("get-property", NM, path, iface, "ActiveConnection")
    if managed is not False or state != 10 or active != "/":
        raise PreflightError(f"{name}: NetworkManager owns/activates this device "
                             f"(managed={managed}, state={state}, active={active}). "
                             "Reserve a dedicated adapter as unmanaged on the host first.")


def radio_unblocked(phy, root=Path("/sys/class/rfkill")):
    """Fail unless the radio's rfkill entry exists and is neither soft- nor hard-blocked."""
    entries = []
    for entry in root.glob("rfkill*"):
        try:
            name = (entry / "name").read_text().strip()
        except FileNotFoundError:
            # A different radio can leave a stale class entry after moving
            # namespaces or unplugging. It says nothing about this radio.
            continue
        if name == phy:
            entries.append(entry)
    if not entries:
        raise PreflightError(f"{phy}: cannot verify rfkill state; refusing to change radio state")
    for entry in entries:
        try:
            states = [(entry / key).read_text().strip() for key in ("soft", "hard")]
        except OSError as exc:
            raise PreflightError(f"{phy}: selected radio's rfkill state became unavailable; refresh adapters") from exc
        if states != ["0", "0"]:
            raise PreflightError(f"{phy}: radio is soft/hard blocked or state unknown; check this adapter in Home Assistant")


@dataclass
class Adapter:
    """Identity of the leased radio. The ifindex lets us notice a replaced device."""
    name: str
    phy: str
    ifindex: int

    def as_dict(self):
        return asdict(self)


def inspect(candidate, all_interfaces, run=command, ownership=None, rfkill=None, allow_up=False):
    """Decide whether an interface is idle and dedicated enough to be handed to the app.

    Raises :class:`PreflightError` with a human-readable reason otherwise. The reasons are
    shown verbatim in the Web UI, so keep them understandable for non-developers.
    """
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
    """Pick the first eligible interface (``requested`` = a name, or "auto") and log why others fail."""
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
    """Guard against USB resets or re-plugs: the interface must still be the very same device."""
    interfaces = parse_interfaces(command("iw", "dev"))
    info = json.loads(command("ip", "-j", "link", "show", "dev", adapter.name))
    if not any(i["name"] == adapter.name and i["phy"] == adapter.phy for i in interfaces) or not info or info[0]["ifindex"] != adapter.ifindex:
        raise PreflightError("Adapter removed/replaced; refusing to touch another device")


def cleanup(adapter, log):
    """Disconnect the leased interface, flush its addresses and routes, then verify the result."""
    try:
        same_device(adapter)
    except (PreflightError, OSError, ValueError, KeyError) as exc:
        log("error", f"Cleanup refused: {exc}")
        return False
    ok = True
    for args in (("iw", "dev", adapter.name, "disconnect"),
                 ("ip", "link", "set", "dev", adapter.name, "down"),
                 ("ip", "-4", "address", "flush", "dev", adapter.name),
                 ("ip", "-6", "address", "flush", "dev", adapter.name),
                 ("ip", "-4", "route", "flush", "table", "all", "dev", adapter.name),
                 ("ip", "-6", "route", "flush", "table", "all", "dev", adapter.name)):
        try:
            same_device(adapter)
            command(*args)
            log("info", "Cleanup: " + " ".join(args))
        except (PreflightError, OSError, ValueError, KeyError) as exc:
            log("warning" if args[0] == "iw" else "error", str(exc))
            if args[0] != "iw":
                ok = False
    try:
        same_device(adapter)
        addresses = json.loads(command("ip", "-j", "address", "show", "dev", adapter.name))
        if len(addresses) != 1 or addresses[0].get("addr_info") or "UP" in addresses[0].get("flags", []):
            raise PreflightError("Cleanup verification found remaining addresses or an UP interface")
        for family in ("-4", "-6"):
            routes = json.loads(command("ip", family, "-j", "route", "show", "table", "all"))
            if any(route.get("dev") == adapter.name or any(hop.get("dev") == adapter.name for hop in route.get("nexthops", [])) for route in routes):
                raise PreflightError("Cleanup verification found remaining routes on the leased adapter")
        if command("iw", "dev", adapter.name, "link").strip() != "Not connected.":
            raise PreflightError("Cleanup verification could not confirm disconnection")
        log("info", "Cleanup verified: selected adapter down, disconnected, no IPv4/IPv6 addresses or dependent routes")
    except (PreflightError, OSError, ValueError, KeyError) as exc:
        log("error", f"Cleanup verification failed: {exc}")
        ok = False
    return ok
