# UnTuyaOS3

> **Flashing can brick your device. Use this at your own risk.** A finished transfer does not promise that the device boots afterwards. Only flash devices you can afford to lose.

This app puts open firmware on **some** Tuya devices over Wi-Fi, using the [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3) exploit of the tuya-cloudcutter community. The exploit and the scripts are theirs, this app wraps them for Home Assistant. Not every device is affected: check the firmware version against the [compatibility list](https://github.com/seb5594/Home-Assistant-Anti-Tuya-Apps/blob/main/docs/compatibility.md) and upstream's wiki first.

## Setup

1. Install **Anti Tuya WiFi Helper** from the same repository. It is a separate app on purpose, because only it may touch the host network.
2. Enter the **same** pairing secret (at least 32 characters) in the Configuration tab of both apps. The Web UI can generate one for you.
3. Start the helper and wait for *Ready*, then start this app and open the Web UI. The helper card at the top tells you what is missing. This page finds the helper by itself as soon as it runs.

Keep Home Assistant on Ethernet and keep Protection mode and AppArmor on. The adapter you flash with is borrowed from the host and handed back afterwards.

## Using it

Choose a Wi-Fi adapter (a single eligible one is picked for you; press **Refresh adapters** after plugging in a USB stick), put the device into AP pairing mode, press **Start interactive session** and answer the script's numbered questions. Console and diagnostics update live, and your session keeps running if you close the page.

- **Unconfirmed** means all bytes were sent but the device never confirmed. Look for a Kickstart Wi-Fi network before retrying: Kickstart is a generic setup firmware, so a dark lamp can be perfectly alive.
- **Clear logs** wipes saved logs and both panels without stopping a session. **Download logs** exports them; each app starts with fresh logs, so download before restarting.
- Your own UG images can be uploaded in the Web UI (32 MiB each, 30 per platform). For devices sold by Action (LSC Smart, Battletron, Eurodomest) there is a [collection of prebuilt ESPHome firmware](https://gitea.seb5594.xyz/seb5594/Action_Battleton_Eurodomest_LSC-Smart-Custom-Firmware-Collection).
- Stop the app when you are done. The helper restores the adapter.

Something not working? Read the Log tab of both apps, then the [troubleshooting list](https://github.com/seb5594/Home-Assistant-Anti-Tuya-Apps#when-something-does-not-work) in the README. Tell us how your device went with **Report a device** at the bottom of the Web UI.
