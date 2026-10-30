# Compatibility list

What people have tried with this app so far, and how far they got. It starts small, with my own devices, and grows with your reports.

Please read the results as *a report from one unit with one firmware version*. Two devices with the same name can carry different chips or firmware. The firmware version shown in the Smart Life / Tuya app decides whether the exploit works, not the product name, the shop or the year.

A flash has several stages, and they are reported separately because each can fail on its own: the device accepts the exploit, the OTA transfer completes, the device confirms it, the new firmware boots, and finally its outputs work. **Kickstart**, the firmware that is bundled, is a generic setup firmware: it brings up a Wi-Fi network and a captive portal, but it does not know your lamp's pins until you configure it.

## Devices

| Device | Chip | Original firmware | Result | Wi-Fi adapter |
| --- | --- | --- | --- | --- |
| LSC Smart Floor Lamp | T1 | 1.2.1 | **Worked.** The log shows the device's OTA-finish response. Bundled T1 Kickstart image. | Atheros AR9271 |
| LSC Smart Connect table lamp, Action 3225458 | T1 | 1.0.43 | **Kickstart running.** All 432,292 bytes were sent, but the final confirmation never arrived. A Kickstart Wi-Fi appeared afterwards; the lamp's outputs were not set up. See the [incident notes](table-lamp-3225458.md). | Atheros AR9271 |
| LSC Smart LED Strip Kit, Action 3225770 (SmartLife name: Eurodomest Smart LED Strip Kit) | not noted | 1.0.28 | **Exploit accepted.** Device info (`0x16`) answered and the schema command sent. The excerpt does not cover the OTA or a boot check. | not noted |
| Battletron Lightbar (2024) | not noted | not noted | **Not accepted.** The device answered the device-info request with `0x0C`, so no later stage was attempted. Wi-Fi and DHCP were fine. | Atheros AR9271 and internal Realtek |
| LSC Powerstrip without energy monitoring (2024) | BK7231N | not noted | **Unknown.** Wi-Fi and DHCP worked on `192.168.175.x` (older versions of the app wrongly refused that subnet). A flash was not confirmed. | not noted |

Private identifiers, UUIDs, local keys and full protocol payloads are left out on purpose.

## Wi-Fi adapters

| Adapter | Driver | Result |
| --- | --- | --- |
| Atheros AR9271 / UB91 (`0cf3:9271`, sometimes mistyped as AR7271) | `ath9k_htc` | Works. Used for all the flashes above. |
| Internal Realtek RTL8822CE | `rtw88_8822ce` | Handover, association and DHCP work. At about −95 dBm the association can time out. |

More background, and the list of drivers HAOS builds, is in [wifi-compatibility.md](wifi-compatibility.md).

## Add your device or adapter

The easiest way is the **Report a device** button at the bottom of the app's Web UI. It opens the device report form on GitHub with the app version, your Wi-Fi adapter and the kernel already filled in.

You can also [open the form directly](https://github.com/seb5594/Home-Assistant-Anti-Tuya-Apps/issues/new?template=device-report.yml). It asks for:

- the device and where it comes from (brand, product name, article number),
- the chip or platform you chose in the menu,
- the original firmware version,
- how far you got, and which stages you saw,
- your Wi-Fi adapter and Home Assistant OS version.

Failures are welcome. "The device answered `0x0C`" is a useful result: it tells the next person that this firmware is probably not affected.

Please do not paste local keys, UUIDs, device IDs or your Wi-Fi password. The issue is public.

## For maintainers

Reports come in as issues with the `compatibility` label. To rebuild the device table from them:

```bash
gh issue list --label compatibility --state all --limit 200 --json number,title,body,url > issues.json
python tools/compat_report.py issues.json
```

The script reads the headings the issue form writes, so keep its field labels and `tools/compat_report.py` in step (a test checks this). Paste the output into the table above and double-check the entries before merging.
