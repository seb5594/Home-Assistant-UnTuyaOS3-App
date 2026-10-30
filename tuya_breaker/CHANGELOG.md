# Changelog

## 1.2.0-beta.1

- Add Lightleak between UnTuyaOS3 and Tuya-Cloudcutter in the shared Ingress workspace.
- Pin six verified payloads and 13 generic BK7231T/BK7231N variants from the fork and official API.
- Add a native controller with ESP CustomAP support and an explicitly experimental Linux AP alternative.
- Require separate target-flash-write acknowledgements; never automatically cycle variants or install replacement firmware.
- Add bounded, CRC-checked 2 MiB private backup readout, SHA-256 checksums, download and confirmed deletion; discard incomplete dumps.
- Keep the established radio isolation, process-group cancellation and cleanup. Add no container privileges.
- Add protocol, UDP readout, cancellation, backup and smartphone UI checks. Physical-device validation of Lightleak is pending.

## 1.1.0-beta.2

- Move project links to Home-Assistant-Anti-Tuya-Apps.
- Rename the shared companion to Anti Tuya WiFi Helper, preserving its installed slug and recovery data.
- Publish separate app descriptions and documentation in the Home Assistant Apps catalog.

## 1.1.0-beta.1

- First experimental Tuya Breaker app: UnTuyaOS3 and classic Tuya CloudCutter in one Ingress workspace.
- Reuse the existing authenticated Wi-Fi Helper, radio selection, PTY runner, logs and recovery.
- Add explicit official-device catalogue refresh, exact firmware profiles, Flash and Detach operations, and private local-credential download.
- Add a native, paginated OpenBeken/Elektroda hardware explorer with explicit database refresh, offline cache, chip/module/keyword filters, read-only pin-map references, source links and community credits. Hardware records never approve an exploit profile.
- Add dark mode, a light-blue default accent, a browser-local RGB picker, and dedicated Tuya Breaker branding.
- Use Python 3.13 for both tools with separate dependency environments; pin the reviewed CloudCutter fork revision.
- Verify real AP startup before exploiting, restrict services to the device radio/loopback, and block forwarding to the container uplink.
- Keep the original UnTuyaOS3 app available. No Lightleak integration.
- Software/container tests only; no hardware validation of the new CloudCutter integration yet.
