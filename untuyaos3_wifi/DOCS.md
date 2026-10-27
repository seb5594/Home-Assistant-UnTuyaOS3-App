# Wi-Fi Helper

This app assigns one checked idle Wi-Fi radio to the isolated **UnTuyaOS3** app. It has no web server.

1. Find the dedicated Wi-Fi name in **Settings → System → Network**, or start with initial options and inspect this app's Log tab for detected wireless names.
2. Enter the exact name and a private pairing secret of at least 32 characters in Configuration. Use the same values in the main app.
3. Start this helper and wait for **Ready**, then start the main app.

Use Ethernet for Home Assistant management. Integrated and USB adapters require AP and network-namespace support. Busy, blocked and unsupported devices are rejected with detailed logs.

Keep Protection mode and AppArmor enabled. This helper needs host-network NET_ADMIN and host D-Bus; the main app does not receive these host privileges.

After the main app stops, the helper restores the radio and exits. If recovery is pending, stop the main app and restart this helper in Home Assistant. No terminal commands are required.
