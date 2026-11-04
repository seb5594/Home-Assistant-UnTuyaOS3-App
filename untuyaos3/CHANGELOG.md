# Changelog

## 1.0.4

- Update UnTuyaOS3 to v1.0.2 (`14b56c3`). [Upstream changes](https://github.com/tuya-cloudcutter/UnTuyaOS3/compare/2111458...14b56c3).

## 1.0.3

- Add the centered developer credit, app catalog link and support footer.

## 1.0.2

- Update the pinned Home Assistant Python base image to Python 3.14 and regenerate the build context from project.json.

## 1.0.1

- Publish the standalone UnTuyaOS3 app as a new release without changing the historical 1.0.0 tag.
- Update setup instructions and the Web UI to the companion app's new name, WiFi App Helper.
- Preserve the existing radio isolation, pairing configuration, protocol 3 and flashing workflow.

## 1.0.0 — standalone app

- Restore the UnTuyaOS3-only repository and requested 1.0.0 app version.
- Move the general WiFi App Helper and Tuya Breaker into their own repositories and independent release cycles.
- Use a pinned, checksum-recorded helper SDK and generic private IPC directory, preserving protocol 3 and radio safety checks.
- Preserve the established interactive script, logs, firmware library, association/DHCP handling and cleanup.
- Document the explicit helper migration and Home Assistant's lack of automatic version downgrades.
- Preserve the historical v1.0.0 tag and release assets; use the current source/catalog for this standalone snapshot.
