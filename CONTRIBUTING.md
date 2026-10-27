# Development

Use Python 3.10+ for portable tests; runtime images use Python 3.13. Install PyYAML in a development environment, then run:

```text
python -m unittest discover -s tests -v
node --check untuyaos3/app/static/app.js
docker build -t untuyaos3:dev untuyaos3
docker build -t untuyaos3-wifi:dev untuyaos3_wifi
```

PTY and SCM_RIGHTS tests require Linux. Windows runs portable tests. Wireless commands are mocked: no automated test flashes hardware or disconnects a network.

The helper copies of wifi.py, protocol.py and journal.py must match the main app. This keeps both Home Assistant image build contexts self-contained; packaging tests enforce equality.

Upstream patches match exact context and fail the image build on drift. Changing the pinned revision requires reviewing upstream shell commands and repeating the privilege review. Do not add a host-network fallback.

## Hardware acceptance

Keep both apps experimental until these checks pass on real Home Assistant OS:

- Install both apps with Protection mode and custom AppArmor enabled; exercise features and check audit denials.
- Missing configuration lists wireless names without modifying networking.
- Missing/busy/blocked adapters, IP addresses, routes, shared PHY, missing AP, D-Bus and namespace support all stop startup before assignment.
- With Ethernet management, test an integrated adapter and a USB adapter. Verify host Ethernet, DNS and default route are unchanged.
- Inspect the main app namespace: only the container network and assigned radio are visible.
- Exercise numbered prompts, invalid choices, verbose output, browser reconnect, firmware upload and log download.
- Flash a known-compatible device with verified UG firmware and verify the resulting firmware.
- Test cancellation, timeout, USB removal, stopping either app first, restarting both apps and reboot recovery.
- Verify AppArmor blocks unrelated /share files and the broker rejects requests without the pairing secret.

CI validates software and profile syntax, not these hardware outcomes.

## Build pipeline

The template's pinned shared engine expects exactly one app and cannot discover this two-app repository. Its caller is replaced by a repository-local CI workflow that validates and builds both apps. Funding, Dependabot, Renovate and the original license are retained. The shared engine repository is not modified.

Version tags in the form `vX.Y.Z` also publish an experimental GitHub prerelease after both native architecture jobs pass. The tag must match the version in both app configurations, and both must retain `stage: experimental`. The release attaches a source ZIP and its SHA-256 checksum; Home Assistant continues to build the apps locally. Branch pushes and manual validation runs do not publish releases.
