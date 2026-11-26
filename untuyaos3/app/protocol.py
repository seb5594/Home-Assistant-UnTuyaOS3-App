# Generated from the pinned WiFi Helper SDK; do not edit.
"""Local protocol between a client app and the WiFi helper app (protocol 4).

Two channels are used, each for what it can do:

* **HTTP** on the Home Assistant internal network. A client only needs the helper's host
  name (``4c7fee11-wifi-helper`` for the official repository). It lists adapters there and
  asks for a short-lived, single-use *ticket* for one operation on one interface.
* **Unix socket** in the shared ``/share`` mount. A radio is handed over by passing a network
  namespace descriptor (SCM_RIGHTS). That only works locally, it can never travel over HTTP.
  The client redeems its ticket on the socket before any descriptor is accepted.

There is no pairing secret. Whoever can reach the helper over HTTP *and* open its socket in
``/share`` is trusted, which is exactly the set of apps the user gave the ``share`` mount.
"""
import array
import json
import os
from pathlib import Path
import re
import socket
import stat

SOCKET = "/share/wifi-helper-private/wifi.sock"
CAPTURE_DIR = "/share/wifi-helper-private/captures"
MAX_PACKET = 65536
# Host name of the helper when it is installed from the official app repository.
DEFAULT_HOST = "4c7fee11-wifi-helper"
DEFAULT_PORT = 4817
TICKET_LENGTH = 64
OPERATIONS = ("lease", "return")
# Protocol compatibility is independent of app release versions. The SDK ships its own build_info.json.
BUILD_INFO = json.loads(Path(__file__).with_name("build_info.json").read_text())
PROTOCOL_VERSION = BUILD_INFO["protocol"]
APP_VERSION = BUILD_INFO["version"]


class HelperUnavailable(RuntimeError):
    """The helper cannot be reached (not started, wrong host name or its socket is missing)."""


class ProtocolMismatch(ValueError):
    """The two apps speak different protocol versions (one of them was not updated)."""


class HelperRejected(ValueError):
    """The helper refused the request (unknown ticket, busy radio, request from outside the app network)."""


def helper_address(options):
    """Return ``(host, port)`` from the ``wifi_helper_host`` option, which may carry ``:port``."""
    value = options.get("wifi_helper_host") or DEFAULT_HOST
    match = re.fullmatch(r"([A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::(\d{1,5}))?", str(value).strip())
    port = int(match[2]) if match and match[2] else DEFAULT_PORT
    if not match or not 1 <= port <= 65535:
        raise ValueError(f"Invalid WiFi Helper host {value!r}; use a host name such as {DEFAULT_HOST}")
    return match[1], port


def validate_interface(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name) or name == "auto":
        raise ValueError("Choose an eligible Wi-Fi adapter in the Web UI")
    return name


def valid_ticket(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % TICKET_LENGTH, value) is not None


def secure_directory(path=SOCKET):
    """Create (or verify) the private IPC directory; refuse symlinks and loose permissions."""
    directory = Path(path).parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("IPC directory must be a real directory owned by the app user with mode 0700.")
    return directory


def send(sock, message, fd=None):
    """Send one JSON packet, optionally with a single file descriptor attached."""
    data = json.dumps(message).encode()
    if len(data) > MAX_PACKET:
        raise ValueError("IPC packet too large")
    ancillary = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))]
    sock.sendmsg([data], ancillary)


def receive(sock):
    """Receive one JSON packet and any descriptors; the caller owns (and must close) the descriptors."""
    descriptors = []
    try:
        data, ancillary, flags, _ = sock.recvmsg(MAX_PACKET, socket.CMSG_SPACE(16*array.array("i").itemsize),
                                               getattr(socket, "MSG_CMSG_CLOEXEC", 0))
        for level, kind, raw in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds = array.array("i")
                fds.frombytes(raw[:len(raw) - len(raw) % fds.itemsize])
                descriptors.extend(fds)
        for fd in descriptors:
            os.set_inheritable(fd, False)
        if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
            raise ValueError("Truncated IPC request")
        if not data:
            raise ConnectionError("Wi-Fi helper disconnected")
        message = json.loads(data)
        if not isinstance(message, dict):
            raise ValueError("IPC request must be an object")
        return message, descriptors
    except BaseException:
        for fd in descriptors:
            os.close(fd)
        raise


def handshake_packet(sock):
    """Receive a handshake packet. Descriptors are rejected until the ticket has been redeemed."""
    packet, fds = receive(sock)
    for fd in fds:
        os.close(fd)
    if fds:
        raise ValueError("Namespace descriptors are not accepted before the ticket is redeemed")
    return packet


def client_handshake(sock, ticket):
    """Client side of the socket handshake: check the protocol, then redeem the HTTP-issued ticket."""
    packet = handshake_packet(sock)
    if packet.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolMismatch("Wi-Fi Helper protocol mismatch. Update both apps, then restart the helper and main app")
    send(sock, {"protocol": PROTOCOL_VERSION, "ticket": ticket})
    answer = handshake_packet(sock)
    if answer.get("event") != "authenticated":
        raise HelperRejected(answer.get("error", "Wi-Fi Helper did not accept the ticket"))


def server_handshake(sock, redeem):
    """Helper side of the socket handshake. ``redeem(ticket)`` returns ``(operation, interface)`` or raises."""
    send(sock, {"protocol": PROTOCOL_VERSION})
    request = handshake_packet(sock)
    if request.get("protocol") != PROTOCOL_VERSION or not valid_ticket(request.get("ticket")):
        raise ValueError("Protocol or ticket mismatch")
    operation, interface = redeem(request["ticket"])
    send(sock, {"event": "authenticated"})
    return operation, interface
