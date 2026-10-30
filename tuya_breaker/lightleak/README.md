# Bundled Lightleak assets

These are fixed payloads from [seb5594/lightleak](https://github.com/seb5594/lightleak), revision `9163a1219d8ae651c16d52159c7ad2f003531b8e`, originally developed by **Kuba Szczodrzyński / tuya-cloudcutter**. The fork's [payload workflow](https://github.com/seb5594/lightleak/actions/runs/40438135099) checks the complete set, stager CRCs and proper-payload encryption round trips against the compiler output. It uses GNU Arm Embedded 7-2017-q4 and ltchiptool 4.15.0.

`manifest.json` records the artifact ID, archive digest and individual file hashes. The archive digest and every original SHA256SUMS entry were verified before extracting these six binaries. The Docker build and runtime metadata loader verify all pinned hashes before use.

`profiles.json` is a snapshot of the 13 general `LIGHTLEAK` variants from [the official CloudCutter API](https://tuya-cloudcutter.github.io/api/profiles.json). These are chip/stager/address variants, not per-model firmware profiles or promises of compatibility. This snapshot was retrieved on 2026-10-30; its hash is pinned in the manifest. Refreshes require source review and a new build. The app cannot download arbitrary payloads or accept user-supplied addresses.

The native controller follows the wire formats in [Cloudcutter Android](https://github.com/tuya-cloudcutter/cloudcutter-android), including binary JSON escaping, datagram framing, callbacks, stager commands, CustomAP configuration and CRC-protected flash responses. Credit for the exploit and payload implementation belongs to the upstream authors. Physical-device validation of this new controller, especially the Linux AP alternative, is pending.

**Warning:** setup writes target flash. A successful readout is a private, post-exploit snapshot, not a pristine pre-exploit backup. Never share it publicly or treat it as an approved replacement firmware image.
