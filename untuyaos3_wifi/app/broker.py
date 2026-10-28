"""Small host-network broker. No HTTP server, shell, Docker socket or host PID access."""
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

from journal import Journal
from protocol import (APP_VERSION, INVENTORY, PROTOCOL_VERSION, SOCKET, receive, secure_directory, send,
                      server_authenticate, validate_options)
from inventory import adapter_details, inventory, usb_devices
from wifi import NM, PreflightError, bus, command, inspect, nm_unmanaged, parse_interfaces, radio_unblocked

DATA = Path("/data")
stopping = threading.Event()


def nm_properties(name, log=None):
    """Read NetworkManager state of a device; refuse anything that is not idle. Returns whether it is managed."""
    path = bus("call", NM, "/org/freedesktop/NetworkManager", NM, "GetDeviceByIpIface", "s", name)
    iface = NM + ".Device"
    managed = bus("get-property", NM, path, iface, "Managed")
    state = bus("get-property", NM, path, iface, "State")
    active = bus("get-property", NM, path, iface, "ActiveConnection")
    if log:
        log("info", f"{name}: NetworkManager managed={managed}, state={state}, active={active}")
    # Fail closed for connected, connecting, unavailable and unknown states.
    if state not in (10, 30) or active != "/" or not isinstance(managed, bool):
        raise PreflightError(f"{name}: not idle (NetworkManager state={state}, active={active})")
    return managed


def nm_set(name, managed):
    """Switch NetworkManager's Managed flag of exactly one device."""
    path = bus("call", NM, "/org/freedesktop/NetworkManager", NM, "GetDeviceByIpIface", "s", name)
    command("busctl", "--system", "--timeout=5", "--allow-interactive-authorization=no",
            "set-property", NM, path, NM + ".Device", "Managed", "b", "true" if managed else "false")


def check_target(fd):
    """Accept only a network namespace descriptor that is not the host's own namespace."""
    import fcntl
    # NS_GET_NSTYPE: reject regular files, user namespaces and the host's own netns.
    if fcntl.ioctl(fd, 0xb703) != 0x40000000:
        raise ValueError("Expected a network namespace descriptor")
    host = os.stat("/proc/self/ns/net")
    target = os.fstat(fd)
    if (host.st_dev, host.st_ino) == (target.st_dev, target.st_ino):
        raise ValueError("Destination must be isolated from the host network")


def validate_host(name, log):
    """Run all host-side safety checks for one interface. Returns the adapter and a recovery snapshot."""
    interfaces = parse_interfaces(command("iw", "dev"))
    log("info", f"Host Wi-Fi inventory: {interfaces}")
    selected = next((i for i in interfaces if i["name"] == name), None)
    if not selected:
        raise PreflightError(f"Selected Wi-Fi {name!r} not found; refresh adapters in the main Web UI")
    managed = nm_properties(name, log)
    adapter = inspect(selected, interfaces, rfkill=radio_unblocked, allow_up=True)
    # iw's human-readable supported-command list is not a reliable namespace
    # capability API. Only the guarded handover's kernel result proves support.
    log("info", f"{name}/{adapter.phy}: namespace support will be verified during authenticated handover")
    link = json.loads(command("ip", "-j", "link", "show", "dev", name))[0]
    log("info", f"Host checks passed for {name}: idle, no addresses/routes, sole interface on AP-capable {adapter.phy}")
    power_save = None
    try:
        match = re.fullmatch(r"Power save: (on|off)", command("iw", "dev", name, "get", "power_save").strip())
        power_save = match[1] if match else None
    except PreflightError as exc:
        log("info", f"Power-saving state unavailable for {name}: {exc}")
    return adapter, {"name": name, "phy": adapter.phy, "mac": link["address"],
                     "up": "UP" in link.get("flags", []), "managed": managed,
                     "power_save": power_save, **adapter_details(name)}


def restore(snapshot, log, wait=30):
    """Wait for the leased radio to reappear on the host (matched by MAC and device identity) and restore its settings."""
    deadline = time.monotonic() + wait
    while True:
        interfaces = parse_interfaces(command("iw", "dev"))
        matches = []
        for candidate in interfaces:
            try:
                address = json.loads(command("ip", "-j", "link", "show", "dev", candidate["name"]))[0]["address"]
                if address.lower() != snapshot["mac"].lower():
                    continue
                details = adapter_details(candidate["name"])
                if any(snapshot.get(key) and snapshot[key] != details.get(key)
                       for key in ("bus", "driver", "usb_path", "device_path")):
                    continue
                matches.append(candidate)
            except (OSError, ValueError, KeyError, IndexError, PreflightError):
                continue
        if len(matches) > 1:
            raise PreflightError("Ambiguous returned radio identity; recovery retained without changing networking")
        selected = matches[0] if matches else None
        if selected:
            name = selected["name"]
            if selected["phy"] != snapshot["phy"]:
                log("info", f"Recovered the same adapter under new radio identity {snapshot['phy']} -> {selected['phy']} (MAC and device identity verified)")
            inspect(selected, interfaces, allow_up=True)
            link = json.loads(command("ip", "-j", "address", "show", "dev", name))[0]
            if link["address"] != snapshot["mac"] or link.get("addr_info") or link.get("master"):
                raise PreflightError("Returned radio identity/state changed; refusing to restore a different or active adapter")
            if command("iw", "dev", name, "link").strip() != "Not connected.":
                raise PreflightError("Returned radio has an active link; refusing restoration")
            nm_properties(name, log)  # Also refuse a reconnect already in progress.
            # Only the dedicated radio is touched. Never restart network managers.
            if snapshot.get("power_save") in ("on", "off"):
                command("ip", "link", "set", "dev", name, "up")
                command("iw", "dev", name, "set", "power_save", snapshot["power_save"])
                log("info", f"Restored {name} power saving: {snapshot['power_save']}")
            command("ip", "link", "set", "dev", name, "up" if snapshot["up"] else "down")
            nm_set(name, snapshot["managed"])
            log("info", f"Restored dedicated radio {name}: up={snapshot['up']}, managed={snapshot['managed']}")
            (DATA / "recovery.json").unlink(missing_ok=True)
            return
        if time.monotonic() >= deadline:
            raise PreflightError("Assigned adapter has not returned as an idle, matching device. Stop the main app; "
                                 "reconnect a missing USB adapter and refresh. Recovery metadata retained; no other adapter was changed")
        time.sleep(0.5)


def try_restore(snapshot, log):
    """Single non-blocking restore attempt; remembers the error so it is logged only once."""
    try:
        restore(snapshot, log, wait=0)
        return True
    except (PreflightError, OSError, ValueError, KeyError) as exc:
        message = str(exc)
        if snapshot.get("recovery_error") != message:
            log("warning", "Recovery pending: " + message)
            snapshot["recovery_error"] = message
        return False


def handover(fd, interface, log):
    """Move the selected radio into the app's namespace. A recovery record is written first and restored on failure."""
    check_target(fd)
    adapter, snapshot = validate_host(interface, log)
    # Durable recovery data before changing host state.
    recovery = DATA / "recovery.json"
    temporary = DATA / "recovery.json.tmp"
    with temporary.open("w") as file:
        file.write(json.dumps(snapshot))
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(recovery)
    try:
        if snapshot["managed"]:
            log("info", f"Temporarily reserving only {interface} from NetworkManager")
            nm_set(interface, False)
        command("ip", "link", "set", "dev", interface, "down")
        # Recheck after the ownership transition to detect a connection/route race.
        interfaces = parse_interfaces(command("iw", "dev"))
        selected = next(i for i in interfaces if i["name"] == interface)
        inspect(selected, interfaces, ownership=nm_unmanaged, rfkill=radio_unblocked)
        log("info", f"Moving only {adapter.phy} into the authenticated app network namespace")
        result = subprocess.run(["iw", "phy", adapter.phy, "set", "netns", "name", f"/proc/self/fd/{fd}"],
                                pass_fds=(fd,), capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise PreflightError(f"Namespace handover failed ({result.returncode}): {result.stderr.strip()} "
                                 "The driver/kernel may not support moving this integrated radio.")
        log("info", f"Radio {adapter.phy} moved successfully; host Ethernet and other radios untouched")
        return adapter, snapshot
    except BaseException:
        restore(snapshot, log, wait=2)
        raise


def main():
    """Run the broker: serve inventory, lease and return requests until stopped."""
    DATA.mkdir(exist_ok=True)
    journal = Journal(DATA / "logs")
    snapshot, server, peer = None, None, None
    socket_owned = False
    try:
        options = json.loads((DATA / "options.json").read_text())
        available = parse_interfaces(command("iw", "dev"))
        journal.emit("info", f"Available host wireless interfaces: {available}")
        if not available:
            journal.emit("error", "USB diagnostics: " + json.dumps(usb_devices()))
            raise PreflightError("No wireless network interface detected. Helper exits immediately. Reconnect the adapter or check its HAOS driver, then start the helper in Home Assistant. Existing recovery metadata is retained")
        _, token = validate_options(options)
        journal.emit("info", "Wi-Fi Helper starting; adapter selection is available in the main Web UI; no HTTP listener")
        if (DATA / "recovery.json").exists():
            journal.emit("warning", "Recovering an interrupted previous assignment")
            snapshot = json.loads((DATA / "recovery.json").read_text())
            if try_restore(snapshot, journal.emit):
                snapshot = None
        journal.emit("info", "Initial inventory: " + json.dumps(inventory(validate_host, journal.emit)))
        secure_directory()
        path = Path(SOCKET)
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("Unsafe IPC socket path")
            # A live helper must never be replaced by another instance.
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                probe.connect(SOCKET)
            except ConnectionRefusedError:
                path.unlink()
            else:
                raise ValueError("Another Wi-Fi Helper already owns the IPC socket")
            finally:
                probe.close()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        server.bind(SOCKET)
        socket_owned = True
        os.chmod(SOCKET, 0o600)
        server.listen(4)
        server.settimeout(1)
        journal.emit("info", "Ready. Start the UnTuyaOS3 app in Home Assistant.")
        next_recovery = 0
        while not stopping.is_set():
            if snapshot is not None and peer is None and time.monotonic() >= next_recovery:
                if try_restore(snapshot, journal.emit):
                    snapshot = None
                    journal.emit("info", "Radio recovery completed; ready for a new assignment")
                next_recovery = time.monotonic() + 5
            readable, _, _ = select.select([server] + ([peer] if peer else []), [], [], 1)
            if peer and peer in readable:
                if peer.recv(1):
                    raise ValueError("Unexpected data on active lease")
                peer.close()
                peer = None
                journal.emit("info", "Lease ended; recovering the adapter by device identity")
                next_recovery = 0
            if server not in readable:
                continue
            client, _ = server.accept()
            client.settimeout(5)
            fds = []
            try:
                interface = server_authenticate(client, None, token)
                request, fds = receive(client)
                if interface == INVENTORY:
                    if request.get("operation") != "inventory" or fds:
                        raise ValueError("Inventory requests must not contain namespace descriptors")
                    result = inventory(validate_host, journal.emit, snapshot if peer else None)
                    result["helper"] = {"version": APP_VERSION, "protocol": PROTOCOL_VERSION}
                    result["recovery_pending"] = snapshot.get("recovery_error", "Waiting for radio return") if snapshot and peer is None else ""
                    send(client, result)
                    continue
                if request.get("operation") == "return":
                    client.settimeout(15)
                    if fds or snapshot is None or peer is None or interface != snapshot["name"]:
                        raise ValueError("No matching active lease for return")
                    host_fd = os.open("/proc/self/ns/net", os.O_RDONLY)
                    try:
                        send(client, {"event": "return_target", "phy": snapshot["phy"]}, host_fd)
                    finally:
                        os.close(host_fd)
                    returned, extra = receive(client)
                    for descriptor in extra:
                        os.close(descriptor)
                    if extra or returned.get("operation") != "returned":
                        raise ValueError("Invalid radio return acknowledgement")
                    peer.close()
                    peer = None
                    if try_restore(snapshot, journal.emit):
                        snapshot = None
                        send(client, {"event": "released"})
                    else:
                        send(client, {"error": snapshot["recovery_error"], "recovery_pending": True})
                    continue
                if snapshot is not None:
                    raise ValueError("Previous radio recovery is pending. Review helper diagnostics before another assignment")
                if request.get("operation") != "lease":
                    raise ValueError("Unknown helper operation")
                if request.get("interface") != interface:
                    raise ValueError("Authenticated interface mismatch")
                if len(fds) != 1:
                    raise ValueError("Exactly one network namespace descriptor is required")

                def log(level, text):
                    journal.emit(level, text)
                    try:
                        send(client, {"event": "log", "level": level, "text": text})
                    except OSError:
                        pass  # Preserve host recovery even if the client disconnects mid-handover.

                adapter, snapshot = handover(fds[0], interface, log)
                peer, client = client, None
                send(peer, {"event": "ready", "phy": adapter.phy, "mac": snapshot["mac"], "power_save": snapshot["power_save"]})
                journal.emit("info", "Lease active. Discovery remains available; the radio returns when the main app stops")
            except Exception as exc:
                journal.emit("error", f"Helper request rejected: {exc}")
                if snapshot is None and (DATA / "recovery.json").exists():
                    snapshot = json.loads((DATA / "recovery.json").read_text())
                try:
                    send(client or peer, {"error": str(exc), "restart_required": snapshot is not None or (DATA / "recovery.json").exists()})
                except OSError:
                    pass
                if snapshot is not None and client is None:
                    raise
            finally:
                # Do not pin the client's netns: kernel must return its radio on app stop.
                for fd in fds:
                    os.close(fd)
                if client:
                    client.close()
    except Exception as exc:
        journal.emit("critical", f"Wi-Fi Helper stopped: {type(exc).__name__}: {exc}")
        return_code = 1
    else:
        return_code = 0
    finally:
        if peer:
            peer.close()  # Main app notices and shuts down if the helper is stopped first.
        if server:
            server.close()
        if snapshot:
            try:
                restore(snapshot, journal.emit, wait=2)
            except Exception as exc:
                journal.emit("critical", f"Radio restoration failed: {exc}")
                return_code = 1
        try:
            if socket_owned:
                Path(SOCKET).unlink(missing_ok=True)
        except OSError:
            pass
        journal.emit("info", "Wi-Fi Helper exiting")
        journal.close()
    return return_code


if __name__ == "__main__":
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    sys.exit(main())
