"""Read-only host adapter and USB discovery; never load modules or claim USB devices."""
from pathlib import Path
import re
import platform

from wifi import command, parse_interfaces

# Discovery hints, not an eligibility allowlist. Every iw interface still goes
# through the same live safety checks regardless of its driver or USB vendor.
WIFI_DRIVER = re.compile(r"^(?:ath|rtw|rtl|brcm|mt76|mt79|rt2500|rt73|rt2800|rt2x00|mwifiex|usb8|carl9170|zd1211|p54|iwl|b43|bcm43)")


def host_drivers(root=Path("/sys/module")):
    return {"kernel": platform.release(),
            "loaded_wifi_modules": sorted(p.name for p in root.iterdir() if WIFI_DRIVER.match(p.name)) if root.exists() else []}


def driver_name(device):
    driver = device / "driver"
    try:
        return driver.resolve().name if driver.exists() else None
    except OSError:
        return None


def adapter_details(name, sys_net=Path("/sys/class/net")):
    device = sys_net / name / "device"
    path = device.resolve().as_posix()
    return {"driver": driver_name(device), "bus": "USB" if "/usb" in path else "PCI/internal",
            "device_path": path if device.exists() else None,
            "usb_path": device.resolve().name.split(":", 1)[0] if "/usb" in path else None}


def usb_devices(root=Path("/sys/bus/usb/devices"), leased=None):
    devices = []
    for device in sorted(root.iterdir()) if root.exists() else []:
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product_id = (device / "idProduct").read_text().strip().lower()
            if not re.fullmatch(r"[0-9a-f]{4}", vendor) or not re.fullmatch(r"[0-9a-f]{4}", product_id):
                continue
            product = (device / "product").read_text().strip()[:120] if (device / "product").exists() else "USB device"
            interfaces = list(root.glob(device.name + ":*"))
            drivers = sorted({name for child in interfaces if (name := driver_name(child))})
            names = sorted({net.name for child in interfaces for net in (child / "net").glob("*")})
            ar9271 = (vendor, product_id) == ("0cf3", "9271")
            assigned = bool(leased and leased.get("bus") == "USB" and leased.get("usb_path") == device.name)
            if assigned or ar9271 or any(name.startswith("wl") for name in names) or any(WIFI_DRIVER.match(driver) for driver in drivers):
                devices.append({"path": device.name, "id": vendor + ":" + product_id,
                                "product": product, "drivers": drivers, "interfaces": names,
                                "assigned_interface": leased["name"] if assigned else None,
                                "hint": ("Assigned to the main app's isolated network; absence from the host interface list is expected.") if assigned else ("AR9271 requires the host's ath9k_htc driver and HTC firmware. "
                                         "USB enumeration alone does not provide a Wi-Fi interface.") if ar9271 and not names else ""})
        except OSError:
            continue  # Hot-unplug during a read must not break the rest of the inventory.
    return devices[:32]


def inventory(validate, log, leased=None):
    adapters = []
    for interface in parse_interfaces(command("iw", "dev"))[:16]:
        entry = {**interface, **adapter_details(interface["name"]), "eligible": False, "reason": ""}
        try:
            validate(interface["name"], log)
            entry["eligible"] = True
        except (RuntimeError, OSError, ValueError, KeyError) as exc:
            entry["reason"] = str(exc)
        adapters.append(entry)
    if leased:
        adapters.append({key: leased.get(key) for key in ("name", "phy", "driver", "bus", "usb_path")}
                        | {"eligible": False, "leased": True, "reason": "Assigned to the main app; restart it to release this radio"})
    return {"adapters": adapters, "usb_devices": usb_devices(leased=leased), "host": host_drivers()}
