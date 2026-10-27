# Changelog

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
