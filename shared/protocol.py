"""Authenticated local IPC between the main app and the Wi-Fi helper.

The two apps talk over a Unix socket in the shared ``/share`` mount. A radio is handed
over by passing a network namespace descriptor (SCM_RIGHTS), which only works locally:
it can never travel over TCP or HTTP. Before any descriptor is accepted, both sides
prove they know the pairing secret with a nonce-based HMAC challenge. The secret itself
is never sent over the socket.
"""
import array
import json
import hashlib
import hmac
import secrets
import os
from pathlib import Path
import re
import socket
import stat

SOCKET = "/share/untuyaos3-private/wifi.sock"
MAX_PACKET = 65536
MIN_SECRET_LENGTH = 32
# Written by tools/sync_project.py from project.json, so both apps always agree on it.
BUILD_INFO = json.loads(Path(__file__).with_name("build_info.json").read_text())
PROTOCOL_VERSION = BUILD_INFO["protocol"]
APP_VERSION = BUILD_INFO["version"]
# Pseudo interface name that scopes a connection to "list adapters" instead of a lease.
INVENTORY = "@inventory"


class ProtocolMismatch(ValueError):
    """The two apps speak different protocol versions (one of them was not updated)."""


class SecretNotSet(ValueError):
    """No usable pairing secret is configured yet (first start after installing)."""


class PairingFailed(ValueError):
    """The proof of the pairing secret did not match (different secrets in the two apps)."""


def validate_options(options):
    token = options.get("pairing_token", "")
    if not isinstance(token, str) or len(token) < MIN_SECRET_LENGTH:
        raise SecretNotSet(f"Set the same pairing_token (at least {MIN_SECRET_LENGTH} characters) in both apps.")
    # Legacy interface options are deliberately ignored. Selection belongs to
    # the authenticated Web UI; the broker rechecks eligibility on every lease.
    return "auto", token


def validate_interface(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name) or name == "auto":
        raise ValueError("Choose an eligible Wi-Fi adapter in the Web UI")
    return name


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


def auth_packet(sock):
    """Receive a handshake packet. Descriptors are rejected until both sides are authenticated."""
    packet, fds = receive(sock)
    for fd in fds:
        os.close(fd)
    if fds:
        raise ValueError("Namespace descriptors are not accepted before mutual authentication")
    return packet


def proof(secret, direction, challenge, nonce, interface):
    """HMAC over protocol version, direction, both nonces and the requested scope."""
    message = json.dumps([PROTOCOL_VERSION, direction, challenge, nonce, interface], separators=(",", ":")).encode()
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def valid_nonce(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def client_authenticate(sock, interface, secret):
    """Main-app side of the handshake: answer the helper's challenge, then verify its proof."""
    packet = auth_packet(sock)
    if packet.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolMismatch("Wi-Fi Helper protocol mismatch. Update both apps, then restart the helper and main app")
    challenge = packet.get("challenge")
    if not valid_nonce(challenge):
        raise ValueError("Invalid Wi-Fi Helper authentication challenge")
    nonce = secrets.token_hex(32)
    send(sock, {"protocol": PROTOCOL_VERSION, "interface": interface, "nonce": nonce,
                "proof": proof(secret, "client", challenge, nonce, interface)})
    response = auth_packet(sock).get("proof", "")
    expected = proof(secret, "server", challenge, nonce, interface)
    if not isinstance(response, str) or not hmac.compare_digest(response.encode(), expected.encode()):
        raise PairingFailed("Wi-Fi Helper authentication failed; check the pairing secret in both apps")


def server_authenticate(sock, interface, secret):
    """Helper side of the handshake. Returns the scope the client proved it may use."""
    challenge = secrets.token_hex(32)
    send(sock, {"protocol": PROTOCOL_VERSION, "challenge": challenge})
    request = auth_packet(sock)
    nonce = request.get("nonce")
    response = request.get("proof", "")
    selected = request.get("interface")
    if request.get("protocol") != PROTOCOL_VERSION or (interface is not None and selected != interface) or not valid_nonce(nonce) or not isinstance(response, str):
        raise ValueError("Pairing secret, protocol or requested operation mismatch")
    if selected != INVENTORY:
        validate_interface(selected)
    interface = selected
    expected = proof(secret, "client", challenge, nonce, interface)
    if not hmac.compare_digest(response.encode(), expected.encode()):
        raise ValueError("Pairing secret or configured interface mismatch")
    send(sock, {"proof": proof(secret, "server", challenge, nonce, interface)})
    return interface
