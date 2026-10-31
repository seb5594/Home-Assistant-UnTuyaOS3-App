# Contributing to standalone UnTuyaOS3

This repository contains one app, `untuyaos3/`. Its version and build pins live in `project.json`; `tools/sync_project.py` renders the committed config, Dockerfile, translations, build metadata and pinned SDK copies. Edit owned code in `untuyaos3/app/`, the Dockerfile layout in `templates/`, and logging in `shared/journal.py`. Never edit generated copies.

The independent WiFi App Helper owns the radio API and SDK. `vendor/wifi_helper/UPSTREAM.json` records a reviewed helper commit and file checksums. Update from that exact upstream source, review the security diff and regenerate. Do not modify a vendored API in place or treat matching app versions as compatibility: wire protocol 3 is the contract.

## Checks

Developer tools are Python 3.11+ with PyYAML, Node.js and Docker. Run `python tools/sync_project.py --check`, `python -m unittest discover -s tests -v` and `node tests/test_webui.cjs`. The project CI also validates AppArmor and runs the real patched upstream inside the built image with stub network commands. Build only `untuyaos3/`; there is no helper or Breaker build context here.

PTY/descriptor tests require Linux. Host Wi-Fi operations and target writes are mocked. Hardware behavior is a separate validation step: keep Protection mode and AppArmor enabled, verify explicit adapter selection, USB loss, helper loss, cancellation, DHCP/association boundaries, clean return and unchanged host Ethernet/routes. Review changes near privileges or radio ownership before merging; never add host networking as fallback.

## Branches and releases

`dev` is the default development branch and publishes through the pinned hass-workflows caller after validation. Pull requests never publish. `.github/apps.json` declares this one app. New versions are independent of both companion repositories. The requested 1.0.0 reset does not move the historical `v1.0.0` tag or overwrite its published images/assets; current source/catalog and the migration guide describe the standalone snapshot. Future version bumps create new releases normally.

Use the engine's managed-file generator to update CI, dependency settings and generated README sections. Keep `.github/checks/check_apps.py` and `.github/tests/runtime.sh` as this project's checks. Do not substitute a separate release pipeline.

## Following upstream

`tools/follow_upstream.py` and the scheduled upstream-release workflow check the pinned UnTuyaOS3 revision, create a reviewable version update and verify exact-snippet patches. Only this app's version/changelog changes. Before merging, read upstream shell/network changes, repeat the privilege review, build both architectures and test a known-compatible device on real hardware.

The WiFi Helper and Tuya Breaker repositories contain their own development docs and release histories. End-user setup belongs in the Home Assistant UI and must never require host shell commands.
