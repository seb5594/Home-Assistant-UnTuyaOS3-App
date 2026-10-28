# UnTuyaOS3 Wi-Fi Helper

This is the small companion of the **UnTuyaOS3** app. It hands one idle Wi-Fi radio to that app and takes it back afterwards. It has no web page of its own: open the UnTuyaOS3 Web UI to pick an adapter and to see what the helper is doing.

## Setup

1. Enter a private pairing secret of at least 32 characters in the Configuration tab. The same value has to go into the UnTuyaOS3 app. Its Web UI has a button that generates a good one.
2. Start the helper and wait for *Ready* in the Log tab, then start UnTuyaOS3. Order does not matter much: the main app notices the helper when it appears.
3. Update both apps together. Mixed versions are reported in the Web UI, mixed protocols are refused.

If there is no Wi-Fi interface on the host at all, the helper stops right away and writes USB diagnostics to its log. Plug the adapter in or check its driver, then start it again.

## What it does and does not do

It needs the host network and D-Bus, because moving a radio between network namespaces cannot be done any other way. That is why it is a separate app: the web UI and the upstream scripts never get these rights. It has no web server, no shell and no access to your Home Assistant configuration. See the [architecture notes](https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App/blob/main/docs/architecture.md) for the details. Keep Protection mode and AppArmor on.

Use Ethernet for Home Assistant itself. Busy, blocked or unsupported adapters are refused with a reason, and a working connection is never disconnected to free one.

After each session, or when the main app stops, the helper puts the radio back as it found it (NetworkManager, up/down state, power saving). It recognises a returned USB adapter by MAC address and device attributes, even if its PHY number changed, and keeps retrying while it runs. Each start removes the old log files but keeps recovery data. Drivers and firmware cannot be installed by these apps.
