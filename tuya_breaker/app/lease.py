# Generated base module from untuyaos3/app; do not edit.
"""Request a radio from the Wi-Fi helper app without any access to the host network.

The helper owns the host side of the handover (see untuyaos3_wifi/app/broker.py). This
module is the client: it lists adapters, asks for one radio to be moved into this app's
network namespace and gives it back when the session is over.
"""
import os
import socket
import threading
import subprocess
import json
from wifi import same_device, PreflightError, command
from protocol import (INVENTORY, SOCKET, PairingFailed, ProtocolMismatch, SecretNotSet,
                      client_authenticate, receive, send, validate_interface, validate_options)


class HelperUnavailable(RuntimeError):
    """The helper's socket is missing or refuses connections (helper not running)."""


def helper_state(error):
    """Map a failed helper call to the state name the Web UI uses for its setup card."""
    for kind, state in ((SecretNotSet, "not_configured"), (HelperUnavailable, "unreachable"),
                        (PairingFailed, "pairing"), (ProtocolMismatch, "protocol")):
        if isinstance(error, kind):
            return state
    return "error"


def connect(options, scope):
    """Open an authenticated connection to the helper for one scope (an interface or INVENTORY)."""
    _, token = validate_options(options)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    sock.settimeout(45)
    try:
        try:
            sock.connect(SOCKET)
        except OSError as exc:
            raise HelperUnavailable("Wi-Fi Helper unavailable. Start it first, then refresh adapters in this Web UI") from exc
        client_authenticate(sock, scope, token)
        return sock
    except BaseException:
        sock.close()
        raise


def inventory(options):
    """Ask the helper which adapters and USB devices it can see on the host."""
    with connect(options, INVENTORY) as sock:
        send(sock, {"operation": "inventory"})
        message, fds = receive(sock)
        for fd in fds:
            os.close(fd)
        if fds or not isinstance(message.get("adapters"), list) or not isinstance(message.get("usb_devices"), list):
            raise RuntimeError(message.get("error", "Invalid helper inventory response"))
        return message


class Lease:
    """One radio on loan from the helper, for the duration of a session.

    Creating a Lease performs the handover. The connection stays open while the radio is
    ours: if the helper dies, the watcher thread flags it so the app can shut down safely.
    """

    def __init__(self, options, journal, lost, interface):
        validate_interface(interface)
        self.options, self.interface, self.journal = options, interface, journal
        self.sock = connect(options, interface)
        self.closed = threading.Event()
        assignment_unknown = False
        try:
            fd = os.open("/proc/self/ns/net", os.O_RDONLY)
            try:
                assignment_unknown = True
                send(self.sock, {"operation": "lease", "interface": interface}, fd)
            finally:
                os.close(fd)
            while True:
                message, fds = receive(self.sock)
                for received in fds:
                    os.close(received)
                if fds:
                    raise RuntimeError("Unexpected descriptors in helper response")
                if message.get("event") == "log":
                    journal.emit(message["level"], message["text"], "helper")
                elif message.get("event") == "ready":
                    self.phy = message["phy"]
                    self.mac = message["mac"]
                    self.power_save = message.get("power_save")
                    journal.emit("info", f"Dedicated radio {self.phy} assigned to this app's isolated network namespace")
                    break
                else:
                    if "error" in message:
                        assignment_unknown = message.get("restart_required", True)
                    raise RuntimeError(message.get("error", "Invalid helper response"))
        except BaseException:
            self.sock.close()
            if assignment_unknown:
                journal.emit("critical", "Assignment outcome uncertain; stopping the app so any assigned radio can return safely")
                lost.set()
            raise
        self.sock.settimeout(None)
        self.thread = threading.Thread(target=self._watch, args=(journal, lost), daemon=True)
        self.thread.start()

    def _watch(self, journal, lost):
        try:
            self.sock.recv(1)
            if not self.closed.is_set():
                journal.emit("critical", "Wi-Fi helper lease ended unexpectedly; stopping the app to return its radio")
                lost.set()
        except OSError:
            if not self.closed.is_set():
                lost.set()

    def close(self):
        self.closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def release(self, adapter):
        """Return only our idle PHY without joining or executing in host netns."""
        import fcntl
        self.closed.set()  # Intentional helper close must not shut down Ingress.
        try:
            with connect(self.options, self.interface) as control:
                send(control, {"operation": "return"})
                message, fds = receive(control)
                try:
                    if message.get("event") != "return_target" or message.get("phy") != self.phy or len(fds) != 1:
                        raise RuntimeError(message.get("error", "Invalid authenticated return target"))
                    if fcntl.ioctl(fds[0], 0xb703) != 0x40000000:
                        raise RuntimeError("Return target is not a network namespace")
                    try:
                        same_device(adapter)
                    except PreflightError:
                        self.journal.emit("warning", "Assigned radio disappeared; asking helper to recover the same device on the host")
                    else:
                        link = json.loads(command("ip", "-j", "link", "show", "dev", adapter.name))
                        if not link or link[0].get("address", "").lower() != self.mac.lower():
                            raise RuntimeError("Radio MAC changed; refusing to return a different device")
                        result = subprocess.run(["iw", "phy", adapter.phy, "set", "netns", "name", f"/proc/self/fd/{fds[0]}"],
                                                pass_fds=(fds[0],), capture_output=True, text=True, timeout=10)
                        if result.returncode:
                            raise RuntimeError(f"Radio return failed: {result.stderr.strip()}")
                finally:
                    for fd in fds:
                        os.close(fd)
                send(control, {"operation": "returned"})
                message, extra = receive(control)
                for fd in extra:
                    os.close(fd)
                if extra or message.get("event") != "released":
                    raise RuntimeError(message.get("error", "Radio restoration was not confirmed"))
                self.journal.emit("info", "Adapter returned and original host settings restored; selection unlocked")
        finally:
            self.close()
