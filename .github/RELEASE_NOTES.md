Experimental Home Assistant apps for UnTuyaOS3. Both apps remain marked `stage: experimental`.

- An Ingress interface with the original interactive menus, verbose console output, live diagnostics and log downloads.
- A dedicated Wi-Fi helper that checks the configured interface and assigns its radio to the main app's isolated network namespace.
- Integrated and USB Wi-Fi support when the Linux driver advertises AP mode and network-namespace reassignment.
- UG firmware uploads with platform signature checks and a persistent firmware library.
- Setup through the Home Assistant app configuration, without end-user terminal commands.

Install **UnTuyaOS3** and **UnTuyaOS3 Wi-Fi Helper** from this repository in the Home Assistant app store. Start the helper first. The apps are built locally by Home Assistant; this release does not publish prebuilt container images.

Publication requires the test suite, both container builds and AppArmor smoke tests to pass on native amd64 and aarch64 GitHub runners. These software checks do not establish compatibility with a particular Wi-Fi driver or Tuya device. Actual Home Assistant OS radio handover and flashing still need hardware validation.

The helper needs host-network `NET_ADMIN` and host D-Bus access. The main app has no host network, Docker socket or blanket USB access. Read the README for the permission boundaries and recovery behaviour before using these experimental apps.

The attached source ZIP includes both apps. `SHA256SUMS.txt` contains its checksum.
