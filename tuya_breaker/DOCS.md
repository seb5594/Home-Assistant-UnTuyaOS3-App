# Tuya Breaker (experimental)

**Flashing or changing a device's cloud configuration can permanently brick it or make the stock app unusable. Use this tool at your own risk. A successful exploit, a transfer and a working device are different results. The new CloudCutter integration has software/container coverage, but has not yet been tested on a physical device.**

Tuya Breaker brings UnTuyaOS3 and classic Tuya CloudCutter into one Home Assistant Ingress UI. The original UnTuyaOS3 app remains available separately. Use only one of these main apps at a time. The same **UnTuyaOS3 Wi-Fi Helper** serves either app; it owns one radio lease at a time.

## Install and prepare

1. Install Tuya Breaker and UnTuyaOS3 Wi-Fi Helper from this repository.
2. Enter the same pairing secret of at least 32 characters in their Home Assistant **Configuration** tabs. The Web UI can generate one.
3. Keep Protection mode and AppArmor enabled. Start the helper, then Tuya Breaker, and open its Web UI.
4. Select an idle AP-capable Wi-Fi adapter. Home Assistant must use another connection, preferably Ethernet. Both USB and internal adapters depend on the HAOS driver and firmware.

The helper's host privileges do not change. Tuya Breaker has no Docker socket, host networking, host D-Bus, Supervisor API, full-device access or kernel-module loading. Its low-port protocol servers need the standard `NET_BIND_SERVICE` permission in its AppArmor profile, alongside the existing namespace-local `NET_ADMIN` and `NET_RAW`. No ports are published.

## Choose a tool

The interface defaults to dark mode with a light-blue accent. The optional **Appearance** section offers an RGB colour picker and a reset button. This preference is stored only in your browser; it does not change app configuration or the flashing engine. Button text and link highlights adapt to keep dark colours readable.

**UnTuyaOS3** uses the same fixed script, platform menus, firmware library and lease cleanup as the original app. Choose platform and firmware in its numbered console menus. Bundled T1 firmware is for Tuya T1/BK7238; **T1 is not BK7231T**.

**Tuya CloudCutter** uses the different, classic profile-based exploit. It needs the exact original firmware profile. It does not automatically bypass patched firmware. Matching a brand or the year printed on a package is insufficient.

1. Select the CloudCutter tool. Load the official device catalogue, search for the exact device and original firmware, then load its profiles.
2. Select the exact profile and operation. **Flash** needs a matching firmware image. **Detach** keeps stock firmware but changes its cloud configuration and asks for the Wi-Fi network the device should join afterwards.
3. Upload an image in the optional firmware library if needed. Format/header checks do not prove that an image suits your device's hardware or GPIO wiring.
4. Press **Review and use this configuration**, check the displayed summary, acknowledge the risk, and start.
5. CloudCutter first verifies that the selected radio can actually start an AP. It then joins the device's AP and requests a final numbered confirmation before sending the exploit.
6. Follow the numbered instructions to power-cycle the target and put it into AP pairing mode again. The app reconnects only to the expected `A-XXXX` AP for that device, then hosts `cloudcutterflash` inside its isolated namespace.
7. After completion, verify the device independently. CloudCutter's near-completion MQTT heuristic produces **Unconfirmed**, not a claim that the new firmware booted. Check for Kickstart Wi-Fi before considering another flash.

The first integration supports the usual open `SmartLife-XXXX`, `TuyaSmart-XXXX` and `A-XXXX` AP names. Custom AP prefixes, arbitrary shell hooks, known-secret injection and UF2 conversion are not exposed. Firmware upload accepts `.bin` UG/OTA images; it does not accept UART/full-flash images.

## Community device explorer

The CloudCutter view also includes a native **Device explorer** based on the [OpenBeken device list](https://openbekeniot.github.io/webapp/devicesList.html). It reads the same [public JSON database](https://openbekeniot.github.io/webapp/devices.json) programmatically, normalizes the records, and caches one snapshot in private app storage. Updates are explicit; cached records work offline. The UI shows the last successful fetch and source dataset version.

Search across vendor, model, chip, module and keywords; filter for detailed teardowns or available pin maps. Results are paginated, so a large database does not create thousands of live DOM elements on a phone. Teardown links open the original community source. Pin-map JSON is a read-only reference, with an explicit warning that hardware revisions differ; no GPIO command or template is automatically executed or applied. Images and external scripts from the source page are not loaded into Ingress.

**OpenBeken hardware support is not CloudCutter exploit compatibility.** Some records describe ESP, Zigbee or other hardware outside CloudCutter's supported platforms. **Find CloudCutter profiles** only fills a model search in the separate official catalogue. It does not select or approve an exploit profile. You still need to verify the exact original firmware and explicitly review the operation.

Thank you to **OpenBeken / openshwprojects**, the **Elektroda.com teardown authors and contributors**, and the **tuya-cloudcutter community** for building and sharing these resources. Source links remain visible in the explorer. Community data retains its original attribution and terms; this app's MIT license does not relicense those records.

## Secrets, logs and cleanup

Destination Wi-Fi credentials are not returned in status or written to the journal. They live in memory and a mode-0600 private session file, and are removed after the attempt. Obvious secret-bearing upstream log lines are redacted. Treat diagnostic archives as private nevertheless.

CloudCutter's generated local credentials are deliberately retained in this app's private data directory, including after an interrupted attempt. **Download private local credentials** retrieves them as a ZIP; keep it private. Up to 100 credential files are retained. Do not publish them in issues. These generated credentials are not a backup of the original firmware.

Logs start fresh on app startup. **Clear logs** clears saved logs and both panels while a running session continues. Saved log retention is bounded to 6 MiB. Firmware and private recovery/credential files survive restarts.

On finish, failure or cancellation the runner terminates its own process group, stops AP services, removes its forwarding-filter table, returns the adapter to managed mode, verifies the interface/address/route cleanup and asks the helper to restore its original host settings. If a USB device vanishes, recovery follows the existing helper path. It never unloads a host driver or changes the global regulatory domain.

Closing the page does not stop a run. **Stop session** can interrupt a write and brick the target. Tool changes and adapter changes stay locked until cleanup finishes.

## Upstreams and Python 3.13

- [UnTuyaOS3](https://github.com/tuya-cloudcutter/UnTuyaOS3) supplies the established interactive flashing engine.
- [Tuya CloudCutter](https://github.com/tuya-cloudcutter/tuya-cloudcutter) supplies the classic exploit, protocol handlers, schemas and device catalogue.
- The CloudCutter revision in `project.json` comes from [seb5594's fork](https://github.com/seb5594/tuya-cloudcutter), with the Python 3.13 binary-PSK change submitted as [upstream PR #928](https://github.com/tuya-cloudcutter/tuya-cloudcutter/pull/928).

Both tools use the official Home Assistant Python 3.13 base. Separate virtual environments retain UnTuyaOS3's `sslpsk3` 2.x and CloudCutter's byte-preserving 1.1.1 callbacks. Both projects retain their original licenses. Source commits, base image and package pins are central in `project.json`; Dockerfiles, configurations and shared copies are generated.

The new icon and logo keep the UnTuyaOS3 colour family with a separate lightning mark. The logo subtitle reads **Powered by tuya-cloudcutter + seb5594**; editable SVG sources live in `assets/branding/`.
