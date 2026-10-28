# Wi-Fi Helper

This app assigns one checked idle Wi-Fi radio to the isolated **UnTuyaOS3** app. It has no web server.

1. Enter a private pairing secret of at least 32 characters in Configuration. Use the same secret in the main app. No interface name is required.
2. Start this helper and wait for **Ready**, then start the main app.
3. Select an adapter in the main Web UI. A single eligible adapter is selected automatically. Refresh after plugging in USB hardware. USB detection distinguishes enumeration, driver binding and a usable WLAN interface.

No internal hostname needs to be entered. Container names do not authenticate a caller; both apps use an authenticated local Unix socket to pass the network namespace descriptor. Keep the same pairing secret in both configurations.

Use Ethernet for Home Assistant management. Integrated and USB adapters require AP and network-namespace support. Busy, blocked and unsupported devices are rejected with detailed logs.

Keep Protection mode and AppArmor enabled. This helper needs host-network NET_ADMIN and host D-Bus; the main app does not receive these host privileges.

After each session or when the main app stops, the helper restores the radio's original NetworkManager, up/down and power-saving settings and stays ready. Recovery identifies the adapter by MAC and available physical-device attributes even if its PHY number changes. Pending recovery remains available through the main Web UI and is retried while this helper runs. Reconnect missing USB hardware and refresh. If no WLAN interface is detected at helper startup, it exits immediately with USB diagnostics; reconnect hardware before starting it again. Each helper start removes old app log files while preserving recovery metadata. Update both apps together for protocol v3. Host drivers and firmware cannot be installed by these apps. No terminal commands are required.
