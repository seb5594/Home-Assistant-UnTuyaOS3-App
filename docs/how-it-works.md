# How it works

This is the long version of what the README only hints at: how the app picks a Wi-Fi adapter, how it talks to the device and what it cleans up afterwards. You do not need any of this to use the app. It is here for the moment something looks odd and you want to know what is going on, or when you want to check that nothing touches your network behind your back.

The big picture is in [architecture.md](architecture.md), the Wi-Fi hardware side in [wifi-compatibility.md](wifi-compatibility.md).

## Picking an adapter

Keep Home Assistant on Ethernet. The app wants a Wi-Fi radio that nobody else is using, because it takes that radio out of the host for the duration of a session. An adapter only shows up as selectable when all of this is true:

- It is not connected, has no IP address, no routes in any table and is not part of a bridge or bond.
- No other virtual interface lives on the same physical radio.
- The driver advertises both `AP` and `managed` mode.
- The radio is not blocked (rfkill) and NetworkManager reports it as *disconnected* or *unmanaged*.

Everything is checked once when you refresh the list and again right before the radio is handed over. If more than one adapter qualifies you choose one in the Web UI; with exactly one, it is selected for you. Your choice is remembered.

The helper marks only that one interface as unmanaged for NetworkManager and moves its radio into the main app's network namespace. It never disconnects a working connection to free an adapter, and a busy interface is simply refused.

When a session ends, fails or is cancelled, the main app gives the radio back and the helper restores what it changed. The adapter dropdown unlocks once that handshake is done, so you can start another session without restarting anything.

The Web UI stays usable when nothing qualifies. You then see the reason for each rejected adapter, which is usually all you need to fix the problem. Flashing is simply blocked until an adapter qualifies.

### USB adapters

USB detection and a working Wi-Fi interface are two different things, and the UI reports them separately: the device is on the USB bus, a driver is bound to it, and a WLAN interface exists. Take the Atheros AR9271 (`0cf3:9271`): an entry with `DRIVER: usb` only proves that the stick is plugged in. For an interface you need the host's `ath9k_htc` driver plus its HTC firmware.

If no interface appears, plug the adapter directly into a USB port (not through a cheap hub), press **Refresh adapters** and look at the host logs for `ath9k_htc` or firmware errors. The apps cannot install drivers or firmware: they run in containers, and a container cannot fix the host kernel. Updating Home Assistant OS is the only fix on that side. The [kernel documentation](https://wireless.docs.kernel.org/en/latest/en/users/drivers/ath9k_htc.html) has details for that driver.

## Connecting to the device

UnTuyaOS3 joins the device's open access point as a Wi-Fi *client*. The app does not create an access point on your host.

A private `wpa_supplicant` (nl80211) runs inside the app's namespace and owns the radio. It only connects to the one open SSID selected by the upstream script, pins the BSSID when it sees it, and keeps retrying inside a deadline instead of giving up after a single missed scan. DHCP starts only after the supplicant reports a completed association *and* an independent `iw link` check agrees on SSID, BSSID and frequency. The [`iw connect` code](https://kernel.googlesource.com/pub/scm/linux/kernel/git/jberg/iw/+/refs/heads/master/connect.c) can return success after a failed association, which is why the second check exists.

The first scan for the device's AP stops after 90 seconds. If the AP is not there by then, the run ends before DHCP and nothing was sent.

Power saving is switched off on the radio for the session if the original state could be read, and put back afterwards. Regulatory settings and global driver parameters are never touched.

A signal around −97 dBm is very weak, even if the lamp sits right next to the antenna. Check the adapter's antenna, put the device back into pairing mode or try another adapter. The retries cannot fix a reception or driver problem.

### DHCP and the OTA target

Devices hand out addresses from `192.168.176.x`, but some use another private subnet such as `192.168.175.x`. The DHCP hook accepts one unambiguous on-link DHCP server or router as the device endpoint, rejects networks that overlap with the app's own, and writes a private record for the current session. Before every OTA connection the app re-checks that record, the live address and the direct route, and binds the socket to the approved adapter. No default route and no DNS setting from the device is ever installed. The old `.176.1` fallback only applies if DHCP does not name an endpoint at all and the lease actually covers that address.

Getting an address does not mean the exploit will work. If the device answers the device-info request (`0x16`) with something else, for example `0x0C`, the expected AP protocol response did not arrive. The app stops right there and prints what it expected and what it got. A chip name, a shop name or a manufacturing year does not tell you whether a given firmware version is affected. Put the device back into pairing mode and look at the upstream [device compatibility wiki](https://github.com/tuya-cloudcutter/UnTuyaOS3/wiki/Device-Compatibility).

## The firmware library

The firmware images that ship with UnTuyaOS3 (ESPHome Kickstart) are copied to private storage on first start, so uploads and bundled images live side by side and survive restarts. You can add your own UG images in the Web UI: 32 MiB per file, 30 files per platform, existing names are never overwritten and uploads are blocked while a session runs.

| Platform | Required UG signature |
| --- | --- |
| T1 | `4D 4D 4D 00` at offset 0 |
| BK7231N | `55 AA 55 AA` at offset 0 |
| RTL8720CF | `68 51 3E F8 3E 39 6B 12 BA 05 9A 90 0F 36 B6 D3` at offset 32 |

The signature check only tells you that the file has the right *format*. It says nothing about who built it or whether it suits your device.

## What the results mean

A session ends in one of these states:

| State | Meaning |
| --- | --- |
| finished | The device confirmed the OTA. That is still not proof that it booted or that its outputs are configured. |
| unconfirmed | Every byte was sent, but the device never confirmed. Look for the Kickstart Wi-Fi network before you do anything else. |
| cancelled | You stopped it. Interrupting an upload can leave a device unusable. |
| failed | Something went wrong before or during the transfer. The log says where. |

*Unconfirmed* is not the same as *failed*. The table lamp report in [table-lamp-3225458.md](table-lamp-3225458.md) shows why: the lamp stopped lighting, yet it was running Kickstart. A dark lamp may just be waiting for its device-specific configuration.

## Logs and recovery

The console shows the live terminal output. The activity panel next to it adds timestamped diagnostics, driver events and everything the script prints. While a session waits for input, an AP or a protocol answer you get a heartbeat line every ten seconds.

Each app starts with fresh logs and deletes only its own previous `app.log` files. Logs live in `/data/logs`, three files of 2 MiB each (6 MiB per app), and the live replay for a reconnecting browser is capped at 2 MiB or 4,000 events. **Clear logs** wipes the saved logs and both panels, also in other open browser tabs, without stopping a session. **Download logs** gives you the retained logs as a ZIP: do that before restarting. Look through verbose logs before sharing them, they can contain device identifiers and protocol material. Home Assistant's own log history is separate and not touched.

After a run the main app disconnects and resets only the leased interface and returns the radio through an authenticated handshake. The helper identifies the returned device by MAC address plus bus, driver, USB path and device path, which lets it recognise a USB adapter even if a USB reset gave it a new PHY number. It never disconnects an active or different adapter for recovery.

The helper writes recovery metadata *before* it changes anything on the host and keeps it until restoration worked. Pending recovery stays visible in the Web UI. Reconnect a missing USB adapter and refresh; the helper keeps retrying while it runs. If the main app dies unexpectedly, destroying its namespace returns any surviving radio to the host anyway.

If startup fails, read the **Log** tab of both apps. If the helper is not reachable, start it: the Web UI notices on its own within a few seconds.

## Cleanup

At the end of every session, successful or not, the app:

- stops the session's processes and its private supplicant,
- restores power saving,
- removes only the selected adapter's IPv4 and IPv6 addresses and the routes that depend on them,
- verifies the adapter is down and disconnected with no leftover addresses or routes,
- deletes the session directory, including the DHCP-derived OTA target. The next session gets a new private directory and a new identity, so an old target can never be reused.
