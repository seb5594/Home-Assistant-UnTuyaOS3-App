"""Authenticated local IPC: namespace descriptors travel over SCM_RIGHTS, never TCP."""
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
MAX_PACKET = 16384


def validate_options(options):
    interface = options.get("interface", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", interface) or interface == "auto":
        raise ValueError("Set interface to the exact dedicated Wi-Fi name in both apps' Configuration tabs.")
    token = options.get("pairing_token", "")
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("Set the same pairing_token (at least 32 characters) in both apps.")
    return interface, token


def secure_directory(path=SOCKET):
    directory = Path(path).parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("IPC directory must be a real directory owned by the app user with mode 0700.")
    return directory


def send(sock, message, fd=None):
    data = json.dumps(message).encode()
    if len(data) > MAX_PACKET:
        raise ValueError("IPC packet too large")
    ancillary = [] if fd is None else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))]
    sock.sendmsg([data], ancillary)


def receive(sock):
    descriptors = []
    try:
        data, ancillary, flags, _ = sock.recvmsg(MAX_PACKET, socket.CMSG_SPACE(16*array.array("i").itemsize))
        for level, kind, raw in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds = array.array("i")
                fds.frombytes(raw[:len(raw) - len(raw) % fds.itemsize])
                descriptors.extend(fds)
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
    packet, fds = receive(sock)
    for fd in fds:
        os.close(fd)
    if fds:
        raise ValueError("Namespace descriptors are not accepted before mutual authentication")
    return packet


def proof(secret, direction, challenge, nonce, interface):
    message = json.dumps([direction, challenge, nonce, interface], separators=(",", ":")).encode()
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def valid_nonce(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def client_authenticate(sock, interface, secret):
    challenge = auth_packet(sock).get("challenge")
    if not valid_nonce(challenge):
        raise ValueError("Invalid Wi-Fi Helper authentication challenge")
    nonce = secrets.token_hex(32)
    send(sock, {"interface": interface, "nonce": nonce,
                "proof": proof(secret, "client", challenge, nonce, interface)})
    response = auth_packet(sock).get("proof", "")
    expected = proof(secret, "server", challenge, nonce, interface)
    if not isinstance(response, str) or not hmac.compare_digest(response.encode(), expected.encode()):
        raise ValueError("Wi-Fi Helper authentication failed; check the pairing secret and interface in both apps")


def server_authenticate(sock, interface, secret):
    challenge = secrets.token_hex(32)
    send(sock, {"challenge": challenge})
    request = auth_packet(sock)
    nonce = request.get("nonce")
    response = request.get("proof", "")
    if request.get("interface") != interface or not valid_nonce(nonce) or not isinstance(response, str):
        raise ValueError("Pairing secret or configured interface mismatch")
    expected = proof(secret, "client", challenge, nonce, interface)
    if not hmac.compare_digest(response.encode(), expected.encode()):
        raise ValueError("Pairing secret or configured interface mismatch")
    send(sock, {"proof": proof(secret, "server", challenge, nonce, interface)})
