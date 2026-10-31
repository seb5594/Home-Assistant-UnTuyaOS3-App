# Changelog

## 1.0.0 — standalone app

- Restore the UnTuyaOS3-only repository and requested 1.0.0 app version.
- Move the general WiFi Namespace Helper and Tuya Breaker into their own repositories and independent release cycles.
- Use a pinned, checksum-recorded helper SDK and generic private IPC directory, preserving protocol 3 and radio safety checks.
- Preserve the established interactive script, logs, firmware library, association/DHCP handling and cleanup.
- Document the explicit helper migration and Home Assistant's lack of automatic version downgrades.
- Preserve the historical v1.0.0 tag and release assets; use the current source/catalog for this standalone snapshot.
