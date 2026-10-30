# Anti Tuya WiFi Helper

Anti Tuya WiFi Helper assigns one unused, AP-capable host Wi-Fi radio to either UnTuyaOS3 or Tuya Breaker. It restores the adapter and original host settings after the session. This shared companion has no Web UI; only it receives host networking and D-Bus access.

Install this app from the [Home Assistant Apps catalog](https://github.com/seb5594/Home-Assistant-Apps). Read the [setup and usage guide](DOCS.md) and [changelog](CHANGELOG.md) before starting.

Keep Protection mode and AppArmor enabled. Configure the same private pairing secret in the companion and main app. Its installed slug remains `untuyaos3_wifi` so existing pairings and recovery data continue to work.
