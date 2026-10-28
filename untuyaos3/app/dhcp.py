"""Configure only the guest namespace's leased IPv4 address. Never DNS/default route."""
import ipaddress
import json
import os
import sys
import re
from wifi import command
from ota_target import approved_adapter, state_path, store_target, validate_endpoint
from wifi import same_device


def validate_lease(environment, routes):
    return lease_details(environment, routes)[0]


def lease_details(environment, routes):
    name = environment.get("interface", "")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name) or name != environment.get("UNTUYAOS3_ALLOWED_IFACE"):
        raise ValueError("DHCP hook was called for an unapproved interface")
    network = ipaddress.IPv4Interface(environment["ip"] + "/" + environment["subnet"])
    candidates = set((environment.get("serverid", "") + " " + environment.get("router", "")).split())
    if not candidates:
        candidates = {"192.168.176.1"}  # Compatibility only for the original, matching subnet.
    if len(candidates) != 1:
        raise ValueError("DHCP server/router does not identify one unambiguous device target")
    target = str(ipaddress.IPv4Address(candidates.pop()))
    validate_endpoint(str(network), target)
    for route in routes:
        if route.get("dev") == environment["interface"] or route.get("dst") in (None, "default"):
            continue
        destination = ipaddress.ip_network(route["dst"], strict=False)
        if destination.version == 4 and destination.overlaps(network.network):
            raise ValueError("Device subnet overlaps the app's existing network; refusing lease")
    return str(network), target


def main():
    event = sys.argv[1]
    if event not in ("bound", "renew", "deconfig"):
        return
    if os.environ.get("interface") != os.environ.get("UNTUYAOS3_ALLOWED_IFACE"):
        raise ValueError("DHCP hook was called for an unapproved interface")
    state_path(os.environ).unlink(missing_ok=True)
    same_device(approved_adapter(os.environ))
    if event == "deconfig":
        command("ip", "-4", "address", "flush", "dev", os.environ["interface"])
        print("DHCP deconfig: cleared this session's address and OTA target", flush=True)
        return
    lease, target = lease_details(os.environ, json.loads(command("ip", "-4", "-j", "route", "show", "table", "all")))
    command("ip", "-4", "address", "replace", lease, "dev", os.environ["interface"])
    store_target(os.environ, lease, target)
    print(f"DHCP {event}: {os.environ['interface']} address={lease}; OTA target={target}; DNS and default route ignored", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DHCP rejected: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
