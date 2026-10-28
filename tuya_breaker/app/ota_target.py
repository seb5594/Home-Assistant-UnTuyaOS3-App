# Generated base module from untuyaos3/app; do not edit.
"""A fresh, validated device endpoint for one session; never route OTA via Ethernet."""
import ipaddress
import json
import os
from pathlib import Path
import re
import stat

from wifi import Adapter, command, same_device

PRIVATE = tuple(ipaddress.IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
RUNTIME = Path("/run")


def validate_endpoint(address, target):
    """Check lease and target are a private /24../30 subnet and distinct usable addresses."""
    lease = ipaddress.IPv4Interface(address)
    remote = ipaddress.IPv4Address(target)
    network = lease.network
    if not 24 <= network.prefixlen <= 30 or not any(network.subnet_of(private) for private in PRIVATE):
        raise ValueError("Device lease must be a private IPv4 subnet with prefix /24 through /30")
    if lease.ip in (network.network_address, network.broadcast_address) or remote not in network:
        raise ValueError("Invalid lease address or off-link device target")
    if remote in (network.network_address, network.broadcast_address, lease.ip):
        raise ValueError("Device target must be a distinct usable address on the leased subnet")
    return lease, remote


def state_path(environment):
    """Path of this session's private target record; refuses anything but the session directory."""
    raw = environment.get("UNTUYAOS3_RUN_DIR", "")
    root = Path(raw)
    if not root.is_absolute() or root.parent != RUNTIME or not root.name.startswith("untuya-session-"):
        raise ValueError("Missing private session directory")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Unsafe session directory")
    if not re.fullmatch(r"[0-9a-f]{32}", environment.get("UNTUYAOS3_RUN_ID", "")):
        raise ValueError("Missing session identity")
    return root / "target.json"


def approved_adapter(environment):
    """The adapter identity the Runner exported to the script."""
    name, phy = environment.get("UNTUYAOS3_ALLOWED_IFACE", ""), environment.get("UNTUYAOS3_ALLOWED_PHY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name) or not re.fullmatch(r"phy[0-9]+", phy):
        raise ValueError("Missing approved adapter")
    return Adapter(name, phy, int(environment["UNTUYAOS3_ALLOWED_IFINDEX"]))


def store_target(environment, address, target):
    """Persist the validated OTA target for this session only (mode 0600, no symlinks)."""
    validate_endpoint(address, target)
    path = state_path(environment)
    record = {"run_id": environment["UNTUYAOS3_RUN_ID"], "interface": environment["interface"],
              "phy": environment["UNTUYAOS3_ALLOWED_PHY"], "ifindex": int(environment["UNTUYAOS3_ALLOWED_IFINDEX"]),
              "address": address, "target": target}
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(record, file)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_target(environment=None, run=command, guard=same_device):
    """Return the validated OTA target, re-checking address, route and session identity right now."""
    environment = os.environ if environment is None else environment
    path = state_path(environment)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Unsafe device target record")
    record = json.loads(path.read_text())
    adapter = approved_adapter(environment)
    expected = (environment["UNTUYAOS3_RUN_ID"], adapter.name, adapter.phy, adapter.ifindex)
    actual = tuple(record.get(key) for key in ("run_id", "interface", "phy", "ifindex"))
    if actual != expected:
        raise ValueError("Device target belongs to a different session or adapter")
    lease, target = validate_endpoint(record["address"], record["target"])
    guard(adapter)
    addresses = json.loads(run("ip", "-j", "address", "show", "dev", adapter.name))
    if not any(item.get("local") == str(lease.ip) and item.get("prefixlen") == lease.network.prefixlen
               for entry in addresses for item in entry.get("addr_info", [])):
        raise ValueError("DHCP address is no longer assigned to the approved adapter")
    routes = json.loads(run("ip", "-4", "-j", "route", "get", str(target)))
    if len(routes) != 1 or routes[0].get("dev") != adapter.name or routes[0].get("gateway"):
        raise ValueError("OTA target is not directly reachable through the approved Wi-Fi adapter")
    return str(target)


def expect_frame_type(frame, expected):
    """Stop with a readable message if the device answered with an unexpected protocol frame."""
    if frame.type != expected:
        raise RuntimeError(f"Device protocol response 0x{frame.type:02X}; expected 0x{expected:02X}. "
                           "Wi-Fi and DHCP completed, but this response does not establish UnTuyaOS3 compatibility. "
                           "Reset the device into AP pairing mode and check its firmware against upstream compatibility reports. "
                           "No later protocol stage was attempted")
