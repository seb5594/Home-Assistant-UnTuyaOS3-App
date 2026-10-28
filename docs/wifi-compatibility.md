# Wi-Fi on Home Assistant OS

The app uses the **host kernel's drivers and firmware**. Its Python image cannot add a missing host driver. Every wireless interface reported by `iw` is considered, independent of brand. Eligibility still requires an idle, unblocked, dedicated radio with managed and AP modes; the kernel must accept namespace reassignment. No vendor allowlist restricts flashing.

## Evidence levels

| Adapter / driver | Evidence | Status |
| --- | --- | --- |
| Atheros AR9271 / UB91, `0cf3:9271`, `ath9k_htc` | User-confirmed LSC Smart Floor Lamp / T1 flash; HAOS kernel 6.18.52-haos, app 0.2.0-beta.2 | Tested successfully in this setup |
| Internal Realtek 8822CE, `rtw88_8822ce` | Namespace handover, association and DHCP confirmed in later user logs; some other attempts timed out at weak signal | Wi-Fi/DHCP confirmed; successful flash not confirmed |
| Other adapters below | HAOS kernel configuration, not a hardware flash test | Candidates only; live checks remain required |

## Drivers configured by HAOS

Reviewed on 27 October 2026 at HAOS source revision `87cca66d53485c3e2bc51e1dacc4e44be012edb1`. The [Linux 6.18 USB/SDIO configuration](https://github.com/home-assistant/operating-system/blob/87cca66d53485c3e2bc51e1dacc4e44be012edb1/buildroot-external/kernel/v6.18.y/device-support-wireless.config) enables these representative USB driver families:

| Family | Configured USB drivers / options |
| --- | --- |
| Atheros | `ATH9K_HTC`, `CARL9170`, `ATH6KL_USB`, `ATH10K_USB` |
| MediaTek | `MT7601U`, `MT7663U`, `MT76x0U`, `MT76x2U`, `MT7921U` |
| Ralink | `RT2500USB`, `RT73USB`, `RT2800USB` |
| Realtek | `RTL8XXXU`, `RTL8192CU`, `RTW88_8822BU`, `RTW88_8822CU`, `RTW88_8723DU` |
| Broadcom | `BRCMFMAC_USB` |
| Marvell | `MWIFIEX_USB` |

The separate [PCI configuration](https://github.com/home-assistant/operating-system/blob/87cca66d53485c3e2bc51e1dacc4e44be012edb1/buildroot-external/kernel/v6.18.y/device-support-wireless-pci.config) includes `RTW88_8822CE` and other internal drivers. It also contains some Realtek USB AU options, so board-specific fragment selection matters. HAOS notes a separate out-of-tree driver choice for 8821CU in the USB/SDIO fragment; do not infer its support from a single in-tree option.

These source options show what that HAOS configuration enables; they do **not** prove which modules are loaded on a particular installed release, whether firmware is present, or whether an adapter supports AP mode and namespace moves. Hardware revisions under the same retail name may use different chips. No additional adapter beyond the reported AR9271 has been physically validated here.

## Read your system through the Web UI

Open **USB Wi-Fi diagnostics** after **Refresh adapters**. It displays the running kernel, loaded Wi-Fi-related modules visible in `/sys/module`, USB identity, bound USB-interface drivers and WLAN names. Module visibility alone is not a compatibility certificate. Discovery includes Ralink, MediaTek, Marvell, Broadcom, Realtek and Atheros driver families; it neither loads modules nor changes host firmware.

An assigned USB radio intentionally disappears from the host's network namespace. The UI labels it **assigned to this app**, not missing firmware. The adapter returns automatically after a run; selection unlocks when the helper confirms restoration. If USB resets and the PHY number changes, recovery uses the saved MAC and device attributes. A stale rfkill entry belonging to another moved/unplugged radio is ignored; the selected radio must still have readable, explicitly unblocked rfkill state.

If USB enumeration is visible but no WLAN interface exists, reconnect the adapter directly to a USB port and refresh. Inspect Home Assistant's host logs for firmware/driver errors and use its normal OS update UI. If the adapter is present but rejected, follow the rejection reason; do not disable protection mode or use Home Assistant's management Wi-Fi.

## Interpreting the reported Realtek failure

The supplied log records −95 dBm on the internal adapter versus −60 dBm on the successful AR9271. The Realtek stayed in authentication/scanning states and stopped at the bounded association deadline. DHCP was never started. Periodic `1/45`, `6/45`, `11/45` messages are status samples, not an endless DHCP loop.

The helper restored the internal radio's original state at 19:11:27 UTC. Later inventory still listed it, but an unrelated missing `rfkill3/name` prevented eligibility. Version 1.0.0-beta.1 corrects that discovery failure. This does not prove a fix for the Realtek's weak reception; check its antennas and hardware/driver behavior separately. Read-only sysctl and rfkill-control notices also appeared in the successful USB run, so those notices alone do not explain the Realtek failure.


## Later device-protocol results

On 28 October 2026, user logs showed successful Wi-Fi association and DHCP with both the internal Realtek and the AR9271 for a 2024 Battletron Lightbar. The device answered request `0x16` with `0x0C`; this is not a successful UnTuyaOS3 device-info exchange, and firmware compatibility is unconfirmed.

A 2024 BK7231N LSC Powerstrip without energy monitoring offered `192.168.175.100/24` from `192.168.175.1`. This was incorrectly rejected by the app's old fixed `.176.1` assumption. Version 1.0.0-beta.3 validates and uses the DHCP-derived endpoint instead. This fixes that app-side networking restriction; a successful powerstrip flash has not been confirmed. The firmware version, rather than year or chip alone, is needed to investigate exploit support.
