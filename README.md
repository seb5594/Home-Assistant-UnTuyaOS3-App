# UnTuyaOS3 for Home Assistant

An interactive Home Assistant app for [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3), with an Ingress console, continuously visible verbose logs, firmware uploads and a dedicated Wi-Fi radio.

**Experimental.** Supports amd64 and aarch64 Home Assistant OS hosts. Integrated and USB Wi-Fi work when their Linux driver supports AP mode and network-namespace reassignment. Real hardware validation is still required.

## Two apps, one repository

- **UnTuyaOS3** provides the Ingress interface and original numbered script menus.
- **UnTuyaOS3 Wi-Fi Helper** checks and temporarily assigns the configured radio.

The main app has its own network namespace. Only the dedicated physical radio is moved into it. The flashing tools cannot see the host's Ethernet or other Wi-Fi interfaces through their namespace.

The helper necessarily has host-network `NET_ADMIN` and host D-Bus access. Linux does **not** scope that capability to an interface name. Separating the helper limits which code receives these rights; a compromised helper could still affect host networking. The web server and upstream scripts do not run in the helper.

No VM, host terminal or end-user shell commands are required.

## Install using Home Assistant

1. Open **Settings → Apps → App store** (**Add-ons** on older versions), then **Repositories** in the store menu. Add this repository's GitHub URL.
2. Install **UnTuyaOS3 Wi-Fi Helper** and **UnTuyaOS3**. The first local image build may take several minutes.
3. Find the dedicated Wi-Fi name in **Settings → System → Network**. Alternatively, start the helper with its initial options: its **Log** tab lists detected names before explaining the missing configuration.
4. In both apps' **Configuration** tabs, enter the same exact **Dedicated Wi-Fi interface**, such as `wlan0`, `wlan1` or `wlx…`.
5. Enter the same private **Pairing secret** of at least 32 characters in both apps. A password manager can generate one.
6. Save both configurations. Keep **Protection mode and AppArmor enabled**.
7. Start the **Wi-Fi Helper** and wait for **Ready** in its Log tab.
8. Start **UnTuyaOS3** and select **Open Web UI**. Optionally enable **Show in sidebar**.

Both apps start manually. Before a new container session, start the helper first, then the main app. Multiple flashing sessions can run within one main-app session. Do not enable an automatic restart watchdog during flashing.

**Private repositories:** Home Assistant must be able to clone the URL. Your browser's GitHub login does not grant Home Assistant access to a private repository. For simple store installation, make the repository public when ready, or use authenticated repository installation supported by your setup. Never put a GitHub token in app options or logs.

## Adapter checks

Use Ethernet for Home Assistant's management connection. The configured Wi-Fi must have:

- No current association, IP addresses, routes in any table or bridge/bond membership.
- No other virtual interface on the same physical radio.
- Advertised `AP` and `managed` modes and `set_wiphy_netns`.
- An unblocked radio and a working host NetworkManager D-Bus connection.
- NetworkManager state **disconnected** or **unmanaged**.

A disconnected interface may initially be administratively up. After the checks, the helper temporarily marks only that interface unmanaged and brings it down. It repeats the checks before moving the radio. Busy interfaces are rejected; an active management connection is never disconnected to free an adapter.

The configured name is a strict selection: the helper never falls back to another adapter. For USB adapters, plug one in before starting the helper and select its Linux interface name. No blanket USB passthrough is enabled. The host must already have a working driver. Integrated adapters are supported only if the driver can move their radio between namespaces.

If any required check fails, the affected app exits immediately after that check, with detailed diagnostics. There is no fallback to host networking or broader permissions.

## Flash a device

1. Put a compatible TuyaOS3 device into AP pairing mode, typically a slow blink.
2. In the web interface, select **Start interactive session**.
3. Submit the script's requested numeric platform and firmware choices using **Menu choice**.
4. Follow **UnTuyaOS3 console** and **Activity & diagnostics**. Verbose TX/RX logging is always enabled.
5. Review the exit status and verify your device. A zero script exit code is not an independent check of the installed firmware.
6. Stop the main app when finished. The helper restores the dedicated radio's original managed/up settings and exits.

Closing the browser does not cancel flashing. Reopening the UI replays recent output. **Stop session** interrupts the process group and cleans up the selected interface; interrupting an upload may make a device unusable.

UnTuyaOS3 joins the device's access point as a Wi-Fi **client**. This app additionally requires AP capability as requested; it does not create a host access point. An advertised capability is not a functional driver test.

## Firmware library

Bundled upstream ESPHome Kickstart images are copied to private persistent storage on first startup. Additional UG `.bin` images can be uploaded in the web interface.

Uploads must match the platform's UG signature. They are limited to 32 MiB per file and 30 files per platform, cannot overwrite existing files and are blocked during a run. Format checks do not establish authenticity or device compatibility.

| Platform | Signature |
| --- | --- |
| T1 | `4D 4D 4D 00` at offset 0 |
| BK7231N | `55 AA 55 AA` at offset 0 |
| RTL8720CF | `68 51 3E F8 3E 39 6B 12 BA 05 9A 90 0F 36 B6 D3` at offset 32 |

Flashing can brick a device or void its warranty. Use a compatible device, correct firmware and uninterrupted power.

## Logging and recovery

The console shows the live PTY output. The separate activity panel includes timestamped diagnostics and all script output. Ten-second heartbeats indicate that the script is still waiting for input, an AP or protocol output.

Logs include discovery, rejection reasons, ownership changes, handover, verbose stdout/stderr, exit status, timeout, cancellation and cleanup. Both apps also write to Home Assistant's **Log** tab and private `/data/logs/app.log`, with five 10 MiB rotated files.

**Download logs** exports the main app's retained logs as ZIP. Live replay is bounded to 2 MiB / 4,000 events. A gap notice directs users to the persistent download. Firmware and logs survive restarts and normal app backups. Verbose logs may contain device identifiers and protocol material; review before sharing.

If startup fails, read both apps' **Log** tabs. An exited app cannot serve Ingress, so its final startup error remains available through Home Assistant's logs.

After a normal stop, the main app disconnects and resets only the leased interface. When its network namespace is destroyed, Linux returns the radio to the host. The helper checks its identity and idle state, then restores its previous settings. Recovery metadata is written before host changes. If restoration cannot finish, stop the main app and restart the helper from Home Assistant. Device removal, driver faults or host crashes may prevent immediate restoration; logs explain the failure and recovery metadata is retained.

## Permission boundaries

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

The Supervisor's `share` mount provides the local Unix socket required for SCM_RIGHTS descriptor passing. The custom enforcing AppArmor profiles allow only `/share/untuyaos3-private/`, excluding unrelated shared files. Do not disable AppArmor.

The helper authenticates requests using the private pairing secret and rejects the host's own network namespace as a destination. It passes the namespace descriptor directly to `iw`; no host PID, Docker socket, `setns` or `SYS_ADMIN` is required.

The main app accepts numeric menu choices only. Ingress requires the actual Supervisor address `172.30.32.2`; forwarded headers cannot bypass it. Browser mutations need a session token. Output is rendered as text.

The DHCP hook configures only the selected interface address inside the app's namespace. Device DNS and default routes are ignored; overlapping subnets are rejected. The integration disables upstream's global rfkill unblock and replaces host network-manager restoration with scoped cleanup.

Network namespaces isolate networking, not the whole kernel. Regulatory settings and physical-radio behaviour are not a VM-level boundary.

## Upstream and development

The build pins upstream revision [2111458225c269ddddf5353bf09a1e8f1096d959](https://github.com/tuya-cloudcutter/UnTuyaOS3/commit/2111458225c269ddddf5353bf09a1e8f1096d959). Packages are installed during image build, never at startup.

See [CONTRIBUTING.md](CONTRIBUTING.md) for automated checks and the hardware acceptance checklist. CI builds both apps on amd64/aarch64, runs Linux PTY/IPC and HTTP tests and validates AppArmor. This does not replace hardware/Supervisor testing.

References: [Home Assistant configuration](https://contributors.home-assistant.io/apps/reference/configuration/), [Ingress](https://contributors.home-assistant.io/apps/guides/ingress/), [AppArmor](https://contributors.home-assistant.io/apps/guides/security/), [NetworkManager](https://www.networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Device.html), [iw namespace assignment](https://kernel.googlesource.com/pub/scm/linux/kernel/git/jberg/iw/+/c62dc398aa2406bd2dd0aa28ecb34cf4d3a2e1af/phy.c).

Upstream software and firmware retain their licenses. This is not an official Home Assistant or Tuya product.

<!-- support:begin (generated, shared text) -->
## Say thanks

All my projects are built in my spare time, just for the fun of it. Still, they take a lot of time and care, and many of the smart home gadgets I buy end up here because I want to make them cloud-free and smart-home ready. Every bit of support means a lot to me.

If my work helped you or turned out to be useful, show your appreciation with a hot drink for my next sleepless night.

[![Buy Me a Coffee](https://img.shields.io/static/v1?label=Support&message=Buy%20Me%20a%20Coffee&color=FFDD00&logo=buy-me-a-coffee&logoColor=black&style=for-the-badge)](https://buymeacoffee.com/seb5594) [![PayPal](https://img.shields.io/static/v1?label=Support&message=PayPal&color=0070BA&logo=paypal&logoColor=white&style=for-the-badge)](https://www.paypal.com/donate/?hosted_button_id=QMQPNRENXDN26)
<!-- support:end -->
