# Changelog

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
