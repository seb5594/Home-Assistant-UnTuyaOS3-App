"""Request a radio from the companion app without access to the host network."""
import os
import socket
import threading
from protocol import INVENTORY, SOCKET, client_authenticate, receive, send, validate_interface, validate_options


def connect(options, scope):
    _, token = validate_options(options)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    sock.settimeout(45)
    try:
        try:
            sock.connect(SOCKET)
        except OSError as exc:
            raise RuntimeError("Wi-Fi Helper unavailable. Start it first, then refresh adapters in this Web UI") from exc
        client_authenticate(sock, scope, token)
        return sock
    except BaseException:
        sock.close()
        raise


def inventory(options):
    with connect(options, INVENTORY) as sock:
        send(sock, {"operation": "inventory"})
        message, fds = receive(sock)
        for fd in fds:
            os.close(fd)
        if fds or not isinstance(message.get("adapters"), list) or not isinstance(message.get("usb_devices"), list):
            raise RuntimeError(message.get("error", "Invalid helper inventory response"))
        return message


class Lease:
    def __init__(self, options, journal, lost, interface):
        validate_interface(interface)
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
