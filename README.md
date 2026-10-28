<!-- header:begin (generated from project metadata) -->
<h1 align="center">UnTuyaOS3</h1>

<p align="center">
  <img src="https://raw.githubusercontent.com/seb5594/Home-Assistant-UnTuyaOS3-App/dev/untuyaos3/logo.png" alt="UnTuyaOS3" width="160" height="160">
</p>

---

<p align="center">
  <a href="https://paypal.me/seb5594"><img src="https://img.shields.io/static/v1?label=Support&amp;message=PayPal&amp;color=0070BA&amp;logo=paypal&amp;logoColor=white&amp;style=for-the-badge" alt="PayPal" height="40"></a>
  <a href="https://buymeacoffee.com/seb5594"><img src="https://img.shields.io/static/v1?label=Support&amp;message=Buy%20Me%20a%20Coffee&amp;color=FFDD00&amp;logo=buy-me-a-coffee&amp;logoColor=black&amp;style=for-the-badge" alt="Buy Me a Coffee" height="40"></a><br>
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fseb5594%2FHome-Assistant-Apps"><img src="https://img.shields.io/static/v1?label=Home%20Assistant&amp;message=Add%20app%20repository&amp;color=18BCF2&amp;logo=homeassistant&amp;logoColor=white&amp;style=for-the-badge" alt="Home Assistant" height="28"></a>
  <a href="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App/releases/tag/v1.0.0-beta.2"><img src="https://img.shields.io/static/v1?label=version&amp;message=Beta%202&amp;color=1877A5&amp;style=for-the-badge" alt="version" height="28"></a>
  <img src="https://img.shields.io/static/v1?label=image%20pulls&amp;message=45&amp;color=1877A5&amp;style=for-the-badge" alt="image pulls" height="28"><br>
  <img src="https://img.shields.io/static/v1?label=arch%20%26%20size&amp;message=amd64%20151.2%20%C2%B7%20aarch64%20165.6%20MiB&amp;color=157F71&amp;style=flat" alt="arch &amp; size" height="20">
  <img src="https://img.shields.io/static/v1?label=stage&amp;message=experimental&amp;color=2F855A&amp;style=flat" alt="stage" height="20">
  <img src="https://img.shields.io/static/v1?label=ingress&amp;message=enabled&amp;color=7C3AED&amp;style=flat" alt="ingress" height="20">
  <img src="https://img.shields.io/static/v1?label=mounts%20%28read-write%29&amp;message=share&amp;color=B45309&amp;style=flat" alt="mounts (read-write)" height="20">
  <img src="https://img.shields.io/static/v1?label=privileged&amp;message=NET_ADMIN%2C%20NET_RAW&amp;color=B45309&amp;style=flat" alt="privileged" height="20"><br>
  <a href="https://github.com/seb5594/Home-Assistant-Apps/issues"><img src="https://img.shields.io/github/issues/seb5594/Home-Assistant-UnTuyaOS3-App?label=issues&amp;style=flat" alt="issues" height="20"></a>
  <img src="https://img.shields.io/static/v1?label=runtime%20tests&amp;message=4%20passed&amp;color=2F855A&amp;style=flat" alt="runtime tests" height="20">
  <a href="https://github.com/seb5594/Home-Assistant-UnTuyaOS3-App/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/seb5594/Home-Assistant-UnTuyaOS3-App/ci.yml?branch=dev&amp;label=checks&amp;style=flat" alt="checks" height="20"></a>
  <a href="https://github.com/seb5594/Home-Assistant-Apps#license"><img src="https://img.shields.io/github/license/seb5594/Home-Assistant-UnTuyaOS3-App?label=license&amp;style=flat" alt="license" height="20"></a>
</p>
<!-- header:end -->

An interactive Home Assistant app for [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3), with an Ingress console, verbose live logs, firmware uploads and a dedicated Wi-Fi radio.

**Experimental.** Supports amd64 and aarch64 Home Assistant OS hosts. Integrated and USB Wi-Fi require a working host driver, AP mode and network-namespace reassignment. Hardware/Supervisor validation is still required.

## Confirmed user result

On 27 October 2026, seb5594 successfully flashed an **LSC Smart Floor Lamp (Action, Tuya T1)** using this app's **0.2.0-beta.2** release on bare-metal Home Assistant OS, kernel **6.18.52-haos**. The adapter was an **Atheros AR9271 / UB91**, USB ID **0cf3:9271**, using **ath9k_htc**. The selected image was the bundled T1 ESPHome Kickstart UG image. The supplied log shows association, a DHCP lease, completed OTA transfer and exit status 0; the user confirmed that flashing worked.

This is one confirmed device/adapter combination, not a guarantee for every lamp revision. The adapter is AR9271 according to its USB identification (sometimes mistyped as AR7271). No private device keys or full protocol logs are published here.

## What the upstream project supports

[UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3) installs custom firmware on **some TuyaOS 3 devices**. A product name or Tuya branding alone does not establish compatibility; firmware versions and community reports matter. Its selectable platforms are **T1, BK7231N and RTL8720CF**, with platform-specific **UG images**. It bundles [ESPHome Kickstart](https://github.com/libretiny-eu/esphome-kickstart/releases) firmware and uses the device's AP pairing mode, usually indicated by a slow blink.

The upstream sequence selects a platform and firmware, joins the device AP, sends the AP/LAN protocol commands and uploads firmware. This app preserves that sequence and the numbered menus, adds Home Assistant Ingress, and prepares dependencies at image-build time. Verbose mode exposes the per-frame TX/RX output. Firmware signatures validate format, not suitability for a particular device. An interrupted or incompatible flash can require serial recovery.

Consult the upstream [FAQ](https://github.com/tuya-cloudcutter/UnTuyaOS3/wiki/FAQ) and [Device Compatibility wiki](https://github.com/tuya-cloudcutter/UnTuyaOS3/wiki/Device-Compatibility) before flashing. These are community resources, not an exhaustive supported-device list. This summary follows the [pinned upstream README](https://github.com/tuya-cloudcutter/UnTuyaOS3/blob/2111458225c269ddddf5353bf09a1e8f1096d959/README.md); the original exploit is credited there to [kuba2k2](https://github.com/kuba2k2) of [LibreTiny](https://github.com/libretiny-eu/libretiny).

## Install using Home Assistant

1. Open **Settings → Apps → App store** (**Add-ons** on older versions), then **Repositories** in the store menu. Add this repository's GitHub URL.
2. Install **UnTuyaOS3 Wi-Fi Helper** and **UnTuyaOS3**.
3. Enter the same private **Pairing secret** of at least 32 characters in both apps' **Configuration** tabs. A password manager can generate one. No interface name or hostname is required.
4. Keep **Protection mode and AppArmor enabled**. Start the helper and wait for **Ready** in its Log tab.
5. Start the main app and select **Open Web UI**. The only eligible adapter is selected automatically. If several are available, select one from **Wi-Fi adapter**. The list includes the driver and USB/internal connection. An explicit selection is remembered.
6. After plugging in a USB adapter, select **Refresh adapters**. **USB detection** distinguishes USB enumeration, driver binding and a usable network interface.

**Updating to 1.0.0-beta.2:** stop the main app first, update both apps to this release, then start the helper and main app. The helper protocol is now v3; update both apps together. Mixed protocols are rejected. Existing pairing secrets remain valid. Legacy interface options are ignored in favor of the Web UI.

If the helper starts with **zero wireless network interfaces**, it immediately exits with USB diagnostics and an explicit error. Reconnect the adapter or check its host driver, then start the helper again through Home Assistant. Busy adapters still count as detected, and a radio already leased to the main app is tracked separately.

Both apps start manually. Multiple flashing sessions can run within one main-app session. The helper remains ready after returning a radio. Do not enable an automatic restart watchdog during flashing. No VM, host terminal or end-user shell commands are required.

## Adapter selection and USB detection

Use Ethernet for Home Assistant management. An eligible Wi-Fi adapter must have:

- No current association, IP addresses, routes in any table or bridge/bond membership.
- No other virtual interface on the same physical radio.
- Advertised `AP` and `managed` modes. Namespace reassignment is verified by the kernel during handover, not by matching text in the capability listing.
- An unblocked radio and a working host NetworkManager D-Bus connection.
- NetworkManager state **disconnected** or **unmanaged**.

Before **Start**, adapters can be refreshed and changed without modifying host networking. The helper rechecks eligibility immediately before handover. It temporarily marks only that interface unmanaged and moves its physical radio into the main app's isolated network namespace. Busy interfaces are rejected; an active management connection is never disconnected to free an adapter.

After a session finishes, fails or is cancelled, the app returns its dedicated radio and the helper restores the original host settings. The adapter dropdown unlocks after this handshake. No main-app restart is required to choose another adapter. Switching during an active session remains blocked.

The Web UI remains available when discovery fails or no adapter is eligible, so rejection reasons can be read and a newly connected adapter can be selected. Flashing stays blocked. A failed identity/ownership check after assignment stops the main app and releases its namespace. There is no fallback to host networking or broader permissions.

For an **Atheros AR9271 / UB91 (`0cf3:9271`)**, a Hardware entry with `DRIVER: usb` confirms USB enumeration only. A usable adapter needs the host's `ath9k_htc` driver, HTC firmware and a WLAN interface. The Web UI reports these separately. If no interface appears, reconnect it directly to a USB port, refresh adapters, and check Home Assistant's host logs for `ath9k_htc` or firmware errors. Update Home Assistant OS through its UI if appropriate. The apps cannot install host drivers or firmware; installing them inside a container would not fix the host kernel. See the [Linux Wireless driver documentation](https://wireless.docs.kernel.org/en/latest/en/users/drivers/ath9k_htc.html).

## Flash a device

1. Put a compatible TuyaOS3 device into AP pairing mode, typically a slow blink.
2. Select **Start interactive session** in the Web UI.
3. Submit the script's numeric platform and firmware choices using **Menu choice**.
4. Follow **UnTuyaOS3 console** and **Activity & diagnostics**. Verbose TX/RX logging is enabled.
5. Review the exit status and verify your device. A zero script exit code is not an independent check of the installed firmware.
6. Stop the main app when finished. The helper restores the radio's original NetworkManager, up/down and power-saving settings and stays ready.

Closing the browser does not cancel flashing. Reopening the UI replays recent output. **Stop session** interrupts the process group and cleans up the selected interface; interrupting an upload may make a device unusable.

UnTuyaOS3 joins the device's access point as a Wi-Fi **client**. This app additionally requires AP capability as requested; it does not create a host access point. An advertised capability is not a functional driver test.

## Wi-Fi connection

A private foreground **wpa_supplicant / nl80211** controller manages the selected radio. It retries association within a bounded wait and does not abort merely because one scan misses the AP. It connects only to the selected open SSID, pins its BSSID when found, and requires both a completed supplicant state and a matching live `iw` link before starting DHCP. It remains alive during DHCP and OTA and stops during scoped cleanup.

Power saving is temporarily disabled on the selected radio when its original state is known. That state is restored after the run and by the helper when the radio returns. Regulatory settings and global driver parameters are unchanged. Driver events, connection state, signal and independent link checks appear in the activity log.

A reported signal such as **−97 dBm** is very weak even if the lamp is nearby. Check the computer's external Wi-Fi antennas, restore the lamp's AP pairing mode, or choose another eligible adapter. These changes fix premature aborts and replace the fragile one-shot connection path; they cannot guarantee recovery from reception or host-driver faults.

The controller uses the [wpa_supplicant control interface](https://w1.fi/wpa_supplicant/devel/ctrl_iface_page.html). Independent link checks remain necessary: the [`iw` connect implementation](https://kernel.googlesource.com/pub/scm/linux/kernel/git/jberg/iw/+/refs/heads/master/connect.c) can return zero after a failed association event.

## Firmware library

Bundled upstream ESPHome Kickstart images are copied to private persistent storage on first startup. Additional UG `.bin` images can be uploaded in the Web UI. Uploads cannot overwrite existing files and are blocked during a run. Limits are 32 MiB per file and 30 files per platform.

| Platform | Required UG signature |
| --- | --- |
| T1 | `4D 4D 4D 00` at offset 0 |
| BK7231N | `55 AA 55 AA` at offset 0 |
| RTL8720CF | `68 51 3E F8 3E 39 6B 12 BA 05 9A 90 0F 36 B6 D3` at offset 32 |

Format checks do not establish authenticity or device compatibility. Flashing can brick a device or void its warranty. Use compatible hardware, correct firmware and uninterrupted power.

The initial device-AP scan now has a **90-second deadline**. If no matching open AP is found, the run stops before DHCP. Adapter disappearance is checked during scanning and throughout a run; no device-wide reconnect loop is used.

## Logs and recovery

The console shows live PTY output. The separate activity panel includes timestamped diagnostics, driver events and all script output. Ten-second heartbeats indicate that the script is waiting for input, an AP or protocol output.

Each app starts with fresh logs, removing only its previous `app.log` files and rotations. Logs are stored under private `/data/logs/`, capped at three 2 MiB files (6 MiB total per app). Live replay is bounded to 2 MiB / 4,000 events.

**Clear logs** removes the main app's saved logs and clears both panels, including other open views, without stopping an active session. **Download logs** exports the retained main-app logs as ZIP. Download before restarting if you need to keep them. Firmware and recovery metadata survive restarts; old app log files do not. Home Assistant's separately managed Log history is outside this button's scope. Review verbose logs before sharing because they may contain device identifiers or protocol material.

If startup fails, read both apps' **Log** tabs. If the helper is unavailable, start it and select **Refresh adapters**. Streaming Ingress requests are supported; the older misleading body-length error was fixed in 0.1.1-beta.3.

After each run the main app disconnects and resets only the leased interface, then returns that radio through an authenticated handshake. The helper checks its MAC and available device identity (bus, driver, USB path and device path), allowing a new PHY number after a USB reset. Matching by PHY number or interface name alone is not sufficient. An active or different adapter is never disconnected for recovery. Recovery metadata is written before host changes and retained until restoration succeeds. Pending recovery stays visible through Ingress; reconnect a missing USB adapter and refresh. The helper retries while running. If the main app exits unexpectedly, namespace destruction still returns any surviving radio to the host.

## Permission boundaries

The two apps deliberately remain separate. A single host-network app would give its Web UI and upstream flashing code access to the host network alongside the helper code. Separate processes in that same container do not reproduce the current network-namespace boundary automatically.

A nested container is not a supported subordinate-app arrangement in the Supervisor configuration. Managing one through the host Docker socket would grant broad host control; running a nested daemon or creating namespaces internally would introduce additional privileges and lifecycle complexity. We retain the working two-app design and its existing capabilities. See the [Home Assistant app configuration reference](https://contributors.home-assistant.io/apps/reference/configuration/) for the host-network and privilege settings.

| Access | Main app | Wi-Fi Helper |
| --- | --- | --- |
| Network namespace | Isolated | Host; required for radio assignment |
| Requested capabilities | `NET_ADMIN`, `NET_RAW` within app network | `NET_ADMIN` for assignment |
| Host D-Bus | No | NetworkManager queries and per-device managed property |
| Web server | Ingress; real Supervisor peer only | None |
| Docker socket, host PID, Supervisor management API | No | No |
| Full hardware access, all USB devices, kernel modules | No | No |
| Home Assistant configuration directory | Not mounted | Not mounted |
| Shared filesystem | IPC directory only under AppArmor | IPC directory only under AppArmor |

The helper necessarily has host-network `NET_ADMIN` and host D-Bus access. Linux does **not** scope that capability to an interface name. Separating the helper limits which code receives these rights; a compromised helper could still affect host networking. The web server and upstream scripts do not run in the helper.

The Supervisor's `share` mount provides a local Unix socket for SCM_RIGHTS descriptor passing. Custom enforcing AppArmor profiles allow only `/share/untuyaos3-private/`, excluding unrelated shared files. Do not disable AppArmor.

Both apps mutually authenticate using nonce-based HMAC challenges before passing any namespace descriptor. The secret is never sent over the socket. Protocol version and requested operation scope are bound to the proof. For assignment, the helper rejects its own host network namespace as a destination. For return only, it sends a temporary read-only descriptor of its network namespace to the authenticated app. The app passes that descriptor solely to a fixed `iw` command for its verified leased PHY and closes it immediately; it is not inherited by the flash script. No process enters the host network namespace, and no host PID, Docker socket, `setns` or `SYS_ADMIN` is required. A namespace descriptor by itself does not grant the capabilities required to enter it.

Container names and internal DNS names are addresses, not credentials. They cannot replace the pairing secret or carry a namespace descriptor over HTTP/TCP. Both apps use the fixed local socket automatically; no hostname is configured. Keep the same private secret in both apps. Publishing an automatically generated secret in `/share` would expose it to other apps with sufficient mount access.

The main app accepts numeric menu choices only. Ingress requires the actual Supervisor address `172.30.32.2`; forwarded headers cannot bypass it. Browser mutations require a session token. Output is rendered as text. The DHCP hook configures only the selected interface address; device DNS/default routes are ignored and overlapping subnets rejected. Global rfkill changes and upstream host network-manager restoration are disabled.

Network namespaces isolate networking, not the whole kernel. Physical-radio behavior is not a VM-level boundary.

## Upstream and development

See [Wi-Fi compatibility and HAOS driver evidence](docs/wifi-compatibility.md) for tested hardware, configured driver families, live module diagnostics and the internal-adapter failure analysis.

Upstream is pinned to [2111458225c269ddddf5353bf09a1e8f1096d959](https://github.com/tuya-cloudcutter/UnTuyaOS3/commit/2111458225c269ddddf5353bf09a1e8f1096d959). Both apps use the pinned official `ghcr.io/home-assistant/base-python` image (Python 3.13 on Alpine 3.24). Packages are installed during image build, never at startup.

`project.json` is the single source for the shared release version, base image, dependency pins, common options and app metadata. `tools/sync_project.py` generates both `config.yaml` files, Dockerfiles, runtime metadata and translations. `shared/` contains common Python sources. Generated files stay committed so Home Assistant can build each app directly. CI rejects stale generated files.

See [CONTRIBUTING.md](CONTRIBUTING.md). The pinned `hass-workflows` pipeline builds both apps for amd64/aarch64, runs PTY/IPC/HTTP and image runtime tests, and validates AppArmor. It publishes both image sets together with one experimental prerelease. These checks do not replace hardware/Supervisor testing.

References: [Home Assistant configuration](https://contributors.home-assistant.io/apps/reference/configuration/), [Ingress](https://contributors.home-assistant.io/apps/guides/ingress/), [AppArmor](https://contributors.home-assistant.io/apps/guides/security/), [NetworkManager](https://www.networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Device.html), [iw namespace assignment](https://kernel.googlesource.com/pub/scm/linux/kernel/git/jberg/iw/+/c62dc398aa2406bd2dd0aa28ecb34cf4d3a2e1af/phy.c).

Upstream software and firmware retain their licenses. This is not an official Home Assistant or Tuya product.

<!-- support:begin (generated, shared text) -->
## Say thanks

All my projects are built in my spare time, just for the fun of it. Still, they take a lot of time and care, and many of the smart home gadgets I buy end up here because I want to make them cloud-free and smart-home ready. Every bit of support means a lot to me.

If my work helped you or turned out to be useful, show your appreciation with a hot drink for my next sleepless night.

[![PayPal](https://img.shields.io/static/v1?label=Support&message=PayPal&color=0070BA&logo=paypal&logoColor=white&style=for-the-badge)](https://paypal.me/seb5594) [![Buy Me a Coffee](https://img.shields.io/static/v1?label=Support&message=Buy%20Me%20a%20Coffee&color=FFDD00&logo=buy-me-a-coffee&logoColor=black&style=for-the-badge)](https://buymeacoffee.com/seb5594)
<!-- support:end -->

<!-- license:begin (generated from the license file) -->
## License

[![license](https://img.shields.io/static/v1?label=license&message=MIT&color=5B6770&style=flat)](LICENSE)

Published under the [MIT License](LICENSE).
<!-- license:end -->
