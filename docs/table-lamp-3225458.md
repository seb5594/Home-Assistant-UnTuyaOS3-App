# Reported table lamp incident: Action 3225458

**This is not a validated flashing recipe or a recommendation to flash this model. Flashing can brick a device. Use the app entirely at your own risk.**

The user identified an [LSC Smart Connect decorative table lamp, Action article 3225458](https://www.action.com/de-de/p/3225458/lsc-smart-connect-smarte-tischlampe/). The reported attempt used the T1 ESPHome Kickstart UG image and an Atheros AR9271 on HAOS kernel 6.18.52-haos. Its AP device-info and schema exchanges completed, and the LAN OTA transfer began.

The supplied log contains **423 data blocks**, covering **all 432,292 image bytes**, ending at offset **432,128** with **164 bytes**. The final device OTA-finish response is absent; the socket timed out. That proves transmission in the log, not that every byte was written correctly to flash or that the application booted successfully.

The user initially reported that the Web UI froze and the lamp no longer lit. The user subsequently found a **Kickstart Wi-Fi network**. This is evidence that a Kickstart firmware was booting; it is **not a confirmed permanent brick**. Working lamp outputs, board configuration and long-term operation have not been verified. Kickstart is a generic setup firmware, not the device-specific lighting configuration.

Two software issues were identified during investigation:

- The pinned upstream script updated its transfer-complete flag only when verbose logging was disabled. With verbose logging enabled, a timeout after all data was sent could incorrectly print an incomplete-transfer message. Other early error paths also returned exit code 0.
- The Web UI replaced and scrolled the entire text of both output panels for every event. A large verbose batch could stall rendering. This is a verified rendering problem; the available logs do not prove that it interrupted the backend or caused a device flash failure.

Version 1.0.0-beta.4 renders each log batch once per panel and tracks actual transmitted byte ranges independently of verbosity. A device-confirmed complete transfer returns 0; a complete transfer without final confirmation returns 3 and displays **unconfirmed**; partial transfers and connection failures return a failure status. No automatic reflash is attempted. Device confirmation still does not prove correct lamp configuration or successful boot.

If an existing Kickstart network is visible after a completed attempt, inspect its setup interface before attempting any further flash. The [Kickstart setup documentation](https://github.com/tuya-cloudcutter/tuya-cloudcutter/blob/main/custom-firmware/README.md#esphome-kickstart-by-libretiny) describes its AP and captive portal at 192.168.4.1. Do not blindly toggle unknown GPIOs or upload another image: identify the exact hardware and configuration first. Serial recovery, if ever needed, requires appropriate expertise and safe handling of a mains-powered device.

Private identifiers, keys and full protocol payloads from the user's logs are deliberately not included here.
