"""Request a radio from the companion app without access to the host network."""
import os
import socket
import threading
from protocol import SOCKET, receive, send, validate_options


class Lease:
    def __init__(self, options, journal, lost):
        interface, token = validate_options(options)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.closed = threading.Event()
        try:
            self.sock.settimeout(45)
            self.sock.connect(SOCKET)
            fd = os.open("/proc/self/ns/net", os.O_RDONLY)
            try:
                send(self.sock, {"interface": interface, "token": token}, fd)
            finally:
                os.close(fd)
            while True:
                message, fds = receive(self.sock)
                for received in fds:
                    os.close(received)
                if message.get("event") == "log":
                    journal.emit(message["level"], message["text"], "helper")
                elif message.get("event") == "ready":
                    self.phy = message["phy"]
                    journal.emit("info", f"Dedicated radio {self.phy} assigned to this app's isolated network namespace")
                    break
                else:
                    raise RuntimeError(message.get("error", "Invalid helper response"))
        except BaseException:
            self.sock.close()
            raise
        self.sock.settimeout(None)
        self.thread = threading.Thread(target=self._watch, args=(journal, lost), daemon=True)
        self.thread.start()

    def _watch(self, journal, lost):
        try:
            if self.sock.recv(1) == b"" and not self.closed.is_set():
                journal.emit("critical", "Wi-Fi helper stopped; stopping the app to return its radio")
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
