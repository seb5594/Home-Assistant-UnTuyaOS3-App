# Tuya Breaker (Experimental)

Tuya Breaker combines UnTuyaOS3, Lightleak and Tuya-Cloudcutter in one experimental Home Assistant Ingress workspace. Choose a tool, review its requirements and use the shared Anti Tuya WiFi Helper to isolate one dedicated adapter. Includes the community hardware explorer, private firmware library and bounded Lightleak flash readout. The Lightleak controller is experimental and awaits physical-device validation.

> **Experimental firmware tooling can permanently brick a device. Use at your own risk. No successful transfer guarantees that the device will boot.**

Install this app from the [Home Assistant Apps catalog](https://github.com/seb5594/Home-Assistant-Apps). Read the [setup and usage guide](DOCS.md) and [changelog](CHANGELOG.md) before starting.

Keep Protection mode and AppArmor enabled. Install the helper once, configure the same pairing secret, and run only one main app at a time. Adapter selection and all interactive steps happen in the Web UI.

Lightleak uses generic chip variants, an ESP CustomAP companion or an experimental Linux AP, and a separate acknowledgement before payload-sector writes. Its complete 2 MiB dumps contain private device secrets and payload modifications. Read the [Lightleak guide](DOCS.md#lightleak-generic-variants-and-private-flash-dumps) before use.
