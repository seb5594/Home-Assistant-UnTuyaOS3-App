"""Small host-network broker. No HTTP server, shell, Docker socket or host PID access."""
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

from journal import Journal
from protocol import SOCKET, receive, secure_directory, send, server_authenticate, validate_options
from wifi import NM, PreflightError, bus, command, inspect, nm_unmanaged, parse_interfaces, radio_unblocked

DATA = Path("/data")
stopping = threading.Event()


def nm_properties(name, log=None):
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
    path = bus("call", NM, "/org/freedesktop/NetworkManager", NM, "GetDeviceByIpIface", "s", name)
    command("busctl", "--system", "--timeout=5", "--allow-interactive-authorization=no",
            "set-property", NM, path, NM + ".Device", "Managed", "b", "true" if managed else "false")


def check_target(fd):
    import fcntl
    # NS_GET_NSTYPE: reject regular files, user namespaces and the host's own netns.
    if fcntl.ioctl(fd, 0xb703) != 0x40000000:
        raise ValueError("Expected a network namespace descriptor")
    host = os.stat("/proc/self/ns/net")
    target = os.fstat(fd)
    if (host.st_dev, host.st_ino) == (target.st_dev, target.st_ino):
        raise ValueError("Destination must be isolated from the host network")


def validate_host(name, log):
    interfaces = parse_interfaces(command("iw", "dev"))
    log("info", f"Host Wi-Fi inventory: {interfaces}")
    selected = next((i for i in interfaces if i["name"] == name), None)
    if not selected:
        raise PreflightError(f"Configured Wi-Fi {name!r} not found; choose its exact name in both app configurations")
    managed = nm_properties(name, log)
    adapter = inspect(selected, interfaces, rfkill=radio_unblocked, allow_up=True)
    if "set_wiphy_netns" not in command("iw", "phy", adapter.phy, "info"):
        raise PreflightError(f"{name}/{adapter.phy}: driver does not advertise set_wiphy_netns; isolation unavailable")
    link = json.loads(command("ip", "-j", "link", "show", "dev", name))[0]
    log("info", f"Host checks passed for {name}: idle, no addresses/routes, sole interface on AP-capable {adapter.phy}")
    return adapter, {"name": name, "phy": adapter.phy, "mac": link["address"],
                     "up": "UP" in link.get("flags", []), "managed": managed}


def restore(snapshot, log, wait=30):
    deadline = time.monotonic() + wait
    while True:
        interfaces = parse_interfaces(command("iw", "dev"))
        selected = next((i for i in interfaces if i["phy"] == snapshot["phy"]), None)
        if selected:
            name = selected["name"]
            inspect(selected, interfaces, allow_up=True)
            link = json.loads(command("ip", "-j", "address", "show", "dev", name))[0]
            if link["address"] != snapshot["mac"] or link.get("addr_info") or link.get("master"):
                raise PreflightError("Returned radio identity/state changed; refusing to restore a different or active adapter")
            if command("iw", "dev", name, "link").strip() != "Not connected.":
                raise PreflightError("Returned radio has an active link; refusing restoration")
            # Only the dedicated radio is touched. Never restart network managers.
            command("ip", "link", "set", "dev", name, "up" if snapshot["up"] else "down")
            nm_set(name, snapshot["managed"])
            log("info", f"Restored dedicated radio {name}: up={snapshot['up']}, managed={snapshot['managed']}")
            (DATA / "recovery.json").unlink(missing_ok=True)
            return
        if time.monotonic() >= deadline:
            raise PreflightError("Radio has not returned to the host. Stop UnTuyaOS3 in Home Assistant, "
                                 "then restart the Wi-Fi Helper to retry restoration. Recovery metadata retained.")
        time.sleep(0.5)


def handover(fd, interface, log):
    check_target(fd)
    adapter, snapshot = validate_host(interface, log)
    # Durable recovery data before changing host state.
    recovery = DATA / "recovery.json"
    recovery.write_text(json.dumps(snapshot))
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
    DATA.mkdir(exist_ok=True)
    journal = Journal(DATA / "logs")
    snapshot, server, peer = None, None, None
    socket_owned = False
    try:
        options = json.loads((DATA / "options.json").read_text())
        journal.emit("info", f"Available host wireless interfaces: {parse_interfaces(command('iw', 'dev'))}")
        interface, token = validate_options(options)
        journal.emit("info", f"Wi-Fi Helper starting for configured interface {interface}; no HTTP listener")
        if (DATA / "recovery.json").exists():
            journal.emit("warning", "Recovering an interrupted previous assignment")
            restore(json.loads((DATA / "recovery.json").read_text()), journal.emit)
        # Validate on startup, so unsupported AP hardware stops the helper immediately.
        validate_host(interface, journal.emit)
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
        while not stopping.is_set() and snapshot is None:
            try:
                peer, _ = server.accept()
            except socket.timeout:
                continue
            peer.settimeout(5)
            fds = []
            authenticated = False
            try:
                server_authenticate(peer, interface, token)
                authenticated = True
                request, fds = receive(peer)
                if request.get("interface") != interface:
                    raise ValueError("Configured interface mismatch")
                if len(fds) != 1:
                    raise ValueError("Exactly one network namespace descriptor is required")

                def log(level, text):
                    journal.emit(level, text)
                    try:
                        send(peer, {"event": "log", "level": level, "text": text})
                    except OSError:
                        pass  # Preserve host recovery even if the client disconnects mid-handover.

                adapter, snapshot = handover(fds[0], interface, log)
                send(peer, {"event": "ready", "phy": adapter.phy})
            except Exception as exc:
                journal.emit("error", f"Assignment rejected: {exc}")
                try:
                    send(peer, {"error": str(exc)})
                except OSError:
                    pass
                peer.close()
                peer = None
                if authenticated:
                    raise
            finally:
                # Do not pin the client's netns: kernel must return its radio on app stop.
                for fd in fds:
                    os.close(fd)
        if snapshot:
            server.close()
            server = None
            journal.emit("info", "Lease active; waiting for UnTuyaOS3 to stop before restoring the radio")
            peer.settimeout(1)
            while not stopping.is_set():
                try:
                    if not peer.recv(1):
                        break
                except socket.timeout:
                    continue
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
                restore(snapshot, journal.emit)
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
