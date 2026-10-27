# Changelog

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
