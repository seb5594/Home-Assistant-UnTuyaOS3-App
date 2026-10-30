# Changelog

## 1.2.0-beta.1

- Shared bundle release with Lightleak added to Tuya Breaker; original UnTuyaOS3 and helper behavior preserved.

## 1.1.0-beta.2

- Move project links to Home-Assistant-Anti-Tuya-Apps.
- Rename the shared companion to Anti Tuya WiFi Helper, preserving its installed slug and recovery data.
- Publish separate app descriptions and documentation in the Home Assistant Apps catalog.

## 1.1.0-beta.1

- Bundle the existing helper with Tuya Breaker as well as UnTuyaOS3. Both clients use the same authenticated protocol and the helper still permits only one active radio lease.
- No host permissions added.

## 1.0.0

First stable release; released together with the main app.

- Report the helper's version to the main app so a mismatch is shown in the Web UI.
- New icon and logo.
- Remove the experimental stage; documentation updated.

## 1.0.0-beta.4

- Add a prominent README danger warning about bricking, lack of warranty and user responsibility.
- Document the table lamp report accurately: full transmission without final confirmation, followed by user-observed Kickstart Wi-Fi.
- Fix verbose OTA result tracking; distinguish device-confirmed completion, unconfirmed full transmission, partial transfer and connection failure.
- Propagate OTA failure and unconfirmed exit codes instead of reporting successful completion on error paths.
- Render verbose log batches once per output panel to avoid per-event DOM replacement and scrolling.
- Add coverage for the reported image size, partial/repeated byte ranges, both verbosity modes and a 4,000-event UI batch.

## 1.0.0-beta.3

- Accept validated private DHCP subnets such as 192.168.175.0/24 and use their server/router as the OTA endpoint.
- Replace the upstream fixed .176.1 TCP target with a fresh session record, live address/route validation and binding to the selected Wi-Fi adapter.
- Reject ambiguous, off-link or overlapping targets; keep device DNS and default routes ignored.
- Clear DHCP target records on deconfiguration and remove all private session files after a run.
- Flush and verify only the selected adapter's IPv4/IPv6 addresses and dependent routes during cleanup.
- Report expected/actual AP protocol responses instead of a bare frame-type assertion; no unsupported-device bypass is added.
- Add DHCP-to-OTA, stale-session, cleanup and patched-upstream runtime regression tests.

## 1.0.0-beta.2

- Recover the same USB device by MAC and physical-device identity after PHY renumbering, without touching a different or active adapter.
- Keep helper discovery available during pending recovery; retain recovery metadata and retry without a restart loop.
- Exit helper startup immediately with explicit USB diagnostics when no WLAN interface exists.
- Return the dedicated radio after each run through authenticated protocol v3 and unlock adapter selection after restoration.
- Bound initial AP discovery to 90 seconds and abort promptly if the selected interface disappears.
- Preserve Ingress after device loss and expose pending recovery instead of a generic connection-loss message.
- Set received namespace descriptors non-inheritable; no new capabilities or host-network mode for the main app.

## 1.0.0-beta.1

- Preserve the user-confirmed AR9271 flashing path and isolated two-app design.
- Ignore stale rfkill entries from unrelated radios while still requiring readable, unblocked state for the selected radio.
- Label leased USB interfaces as assigned instead of incorrectly suggesting missing firmware.
- Expand USB diagnostic driver recognition and expose the running host kernel and loaded Wi-Fi modules.
- Document the confirmed LSC Smart Floor Lamp / T1 flash, upstream scope and HAOS driver evidence.
- Keep the release experimental; additional driver families are not claimed as hardware-validated.

## 0.2.0-beta.2

- Fix all adapters being disabled when iw omits set_wiphy_netns from its human-readable capabilities.
- Verify namespace support through the actual authenticated radio handover; retain idle/AP checks and restoration on kernel rejection.
- Add regression coverage for integrated Realtek and USB Atheros interface discovery without that text.

## 0.2.0-beta.1

- Select Wi-Fi in the main Web UI; automatically select the only eligible adapter and explain rejected/USB-only devices.
- Keep the authenticated helper available for discovery and subsequent main-app sessions; update both apps together (protocol v2).
- Use a private nl80211 wpa_supplicant with bounded association retries and independent link verification before DHCP.
- Temporarily disable power saving only on the selected radio and restore its original setting.
- Add Clear logs; start with fresh app logs and retain at most 6 MiB per app.
- Generate configs, Dockerfiles, metadata and translations from project.json; maintain common Python sources in shared/.
- Build on the pinned official Home Assistant Python 3.13 / Alpine 3.24 base image.

## 0.1.1-beta.6

- Relicense the project under the MIT License.

## 0.1.1-beta.5

- Keep the helper aligned with the app bundle's fix for open APs being reported as invisible after a scan.

## 0.1.1-beta.4

- Keep the helper aligned with the app bundle's verified Wi-Fi association and diagnostic improvements.
- Retain the existing scoped radio handover and restoration permissions.

## 0.1.1-beta.3

- Keep the helper version aligned with the app bundle's Ingress compatibility fix.
- Document why container hostnames cannot replace authenticated local namespace-descriptor transport.

## 0.1.1-beta.2

- Fix the startup crash when reading NetworkManager's Boolean Managed property.
- Correctly parse numeric states and full ActiveConnection paths, with regression coverage.
- Log the inspected NetworkManager state before checking whether the configured adapter is idle.

## 0.1.1-beta.1

- Build and publish the Wi-Fi helper with the main app through hass-workflows.
- Add the shared pipeline's versioned image metadata and service startup script.

## 0.1.0

- Initial dedicated-radio helper: safety checks, authenticated namespace assignment and recovery.
