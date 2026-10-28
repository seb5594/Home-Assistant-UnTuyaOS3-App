# Changelog

## 1.1.0-beta.1

- Add per-attempt flashing-risk acknowledgement, protect menu submissions against double taps, and keep upload controls locked during cleanup.
- Improve phone-sized controls and make the optional firmware library collapsible.
- Share the existing runner and UI with the new experimental Tuya Breaker app; keep the established UnTuyaOS3 command and Wi-Fi lease path.
- Clean up a supplicant whose initial startup fails.

## 1.0.0

First stable release. The flashing path is unchanged since 1.0.0-beta.4; what is new is around it.

- Add a Wi-Fi Helper card to the Web UI. It tells you whether the helper is missing, not running, paired with a different secret or on another version, and links to the helper's page.
- Pick up the helper automatically when it starts (and notice when it stops); no more refreshing by hand.
- Generate a pairing secret in the Web UI. The app now starts without a secret and explains the setup instead of stopping.
- Show the helper version and warn when it differs from the app.
- Credit and link the upstream project and its authors in the Web UI. Show the pinned upstream revision.
- Add a "Report a device" button that opens the compatibility form on GitHub with app version, adapter and kernel filled in.
- New icon and logo.
- Remove the experimental stage. README rewritten (English and German); technical details moved to docs/.
- Code: named constants and docstrings throughout, a clearer runner, tests for the new parts.

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

- Fix the selected open AP being reported as invisible: accept fractional frequencies (`2412.0`) printed by newer `iw` versions.
- Fall back to a directed scan when the kernel scan cache no longer holds the selected AP.

## 0.1.1-beta.4

- Verify the live BSSID, SSID and frequency before DHCP; an exit-zero `iw connect -w` timeout no longer counts as a connection.
- Retry association up to three times against the selected open SSID, using explicit BSSID/frequency and target-channel rescans.
- Log signal strength, kernel, driver, connect events, link checks and read-only power-saving/regulatory diagnostics.
- Stop with an association-specific error if the device AP disappears or all attempts fail; no firmware upload is attempted.
- Pass the approved PHY and interface index to connection checks and recheck adapter identity during retries.

## 0.1.1-beta.3

- Fix interactive session startup through Home Assistant's streaming Ingress proxy by accepting chunked POST bodies.
- Support streamed menu input, cancellation and firmware uploads while enforcing the 2 KiB control and 32 MiB upload limits.
- Reject malformed or ambiguous request framing with specific HTTP errors and persistent diagnostics.
- Log accepted UI operations without including request tokens, query strings or payload contents.

## 0.1.1-beta.2

- Fix busctl JSON parsing for scalar NetworkManager properties and preserve full connection object paths.
- Reject malformed D-Bus replies with contextual diagnostics and retain the adapter safety checks.

## 0.1.1-beta.1

- Build and publish both apps through the central hass-workflows pipeline.
- Publish architecture-specific images and multi-architecture manifests together in one experimental prerelease.
- Keep the isolated Wi-Fi design, live logs and Home Assistant configuration unchanged.

## 0.1.0

- Initial experimental app: isolated Wi-Fi, Ingress console, verbose logs and firmware uploads.
