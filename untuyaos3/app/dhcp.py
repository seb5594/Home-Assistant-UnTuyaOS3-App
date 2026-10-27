"""Configure only the guest namespace's leased IPv4 address. Never DNS/default route."""
import ipaddress
import json
import os
import sys
from wifi import command


def validate_lease(environment, routes):
    if environment.get("interface") != environment.get("UNTUYAOS3_ALLOWED_IFACE"):
        raise ValueError("DHCP hook was called for an unapproved interface")
    network = ipaddress.IPv4Interface(environment["ip"] + "/" + environment["subnet"])
    if network.network.prefixlen < 24 or network.ip in (network.network.network_address, network.network.broadcast_address, ipaddress.IPv4Address("192.168.176.1")) or network.ip.is_loopback or network.ip.is_multicast or network.ip.is_unspecified:
        raise ValueError("Invalid DHCP address")
    # Upstream's OTA target is fixed; do not route it through the Supervisor bridge.
    if ipaddress.IPv4Address("192.168.176.1") not in network.network:
        raise ValueError("Lease does not reach UnTuyaOS3's 192.168.176.1 target")
    for route in routes:
        if route.get("dev") == environment["interface"] or route.get("dst") in (None, "default"):
            continue
        destination = ipaddress.ip_network(route["dst"], strict=False)
        if destination.version == 4 and destination.overlaps(network.network):
            raise ValueError("Device subnet overlaps the app's existing network; refusing lease")
    return str(network)


def main():
    event = sys.argv[1]
    if event not in ("bound", "renew"):
        return
    lease = validate_lease(os.environ, json.loads(command("ip", "-4", "-j", "route", "show", "table", "all")))
    print(f"DHCP {event}: {os.environ['interface']} address={lease}; DNS and default route ignored", flush=True)
    command("ip", "-4", "address", "replace", lease, "dev", os.environ["interface"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DHCP rejected: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
