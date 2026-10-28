# Wi-Fi adapters on Home Assistant OS

The app uses whatever the host kernel brings along. It cannot add a driver or firmware that Home Assistant OS (HAOS) does not ship, because a container cannot extend the host kernel. Every interface that `iw` reports is looked at, whatever the brand. There is no vendor allowlist: an adapter qualifies when it is idle, not blocked, alone on its radio, supports `managed` and `AP` mode, and the kernel accepts moving it into another namespace.

The device's own access point is 2.4 GHz, so an adapter that cannot do 2.4 GHz is no use.

## What has actually been tested

| Adapter | Driver | Evidence | Verdict |
| --- | --- | --- | --- |
| Atheros AR9271 / UB91, USB `0cf3:9271` | `ath9k_htc` | Successful flash of an LSC Smart Floor Lamp (T1); also associated and got DHCP with other devices. HAOS kernel 6.18.52-haos. | Works |
| Internal Realtek RTL8822CE | `rtw88_8822ce` | Namespace handover, association and DHCP confirmed in several runs. Some attempts ended at about −95 dBm, never reaching DHCP. | Connects, flash not confirmed |

Everything in the next section is **a candidate, not a result**. If you try one, please [tell me how it went](compatibility.md#add-your-device-or-adapter).

## Drivers HAOS builds

HAOS compiles Wi-Fi drivers as kernel modules from two configuration fragments. I read them on 28 October 2026 (kernel 6.18, `dev` branch of the HAOS repository):
[USB/SDIO fragment](https://github.com/home-assistant/operating-system/blob/dev/buildroot-external/kernel/v6.18.y/device-support-wireless.config),
[PCI(e) fragment](https://github.com/home-assistant/operating-system/blob/dev/buildroot-external/kernel/v6.18.y/device-support-wireless-pci.config).
Which fragments a particular board uses is decided per board, so a driver listed here is not automatically present on *your* installation. The Web UI shows the modules that are really loaded on your host (**USB Wi-Fi diagnostics**).

### USB and SDIO

These are the interesting ones for a spare USB stick.

| Family | Modules | Typical chips |
| --- | --- | --- |
| Atheros | `ath9k_htc`, `carl9170`, `ath6kl_usb`, `ath10k_usb` | AR9271 / AR7010 (`ath9k_htc`), AR9170 (`carl9170`) |
| MediaTek | `mt7601u`, `mt76x0u`, `mt76x2u`, `mt7663u`, `mt7921u` | MT7601U, MT7610U, MT7612U, MT7921AU |
| Ralink | `rt2500usb`, `rt73usb`, `rt2800usb` | RT2570, RT2571W, RT2870 / RT3070 / RT3572 / RT5370 |
| Realtek | `rtl8xxxu`, `rtl8192cu`, `rtw88_8822bu`, `rtw88_8822cu`, `rtw88_8723du` | RTL8188CU / RTL8192CU / RTL8723AU and relatives, RTL8822BU, RTL8822CU, RTL8723DU |
| Broadcom | `brcmfmac` (USB), `b43`, `brcmsmac` | rare as USB sticks |
| Marvell | `mwifiex` (USB, SDIO) | rare as USB sticks |

SDIO builds (`ath6kl_sdio`, `ath10k_sdio`, `mt7663s`, `mt7921s`, `mwifiex_sdio`, `rtw88_8822bs`, `rtw88_8822cs`, `rtw88_8723ds`, `rtw88_8821cs`, `rtl8723bs`) are for modules soldered onto boards.

The RTL8821CU is deliberately *not* built in-tree by HAOS because of [a known problem](https://github.com/home-assistant/operating-system/issues/3205). Do not assume a Realtek stick works because another one does: the chip behind the same retail name changes between hardware revisions.

### PCI(e), usually the built-in Wi-Fi

Atheros (`ath5k`, `ath9k`, `ath10k_pci`, `ath11k_pci`, `ath12k`), Intel (`iwlwifi` with `iwldvm` / `iwlmvm` / `iwlmld`, plus the legacy `iwl3945` / `iwl4965`), MediaTek (`mt7603e`, `mt7615e`, `mt7915e`, `mt7921e`, `mt7996e`, `mt76x0e`, `mt76x2e`), Realtek (`rtw88_*e`, `rtw89_*`, the older `rtl81xx` / `rtl8723` families), Broadcom (`brcmfmac` PCIe), Marvell (`mwifiex_pcie`, `mwl8k`) and Ralink (`rt2800pci`).

Internal adapters are the least predictable candidates. Many are shared with HAOS's own management connection, and some vendors' drivers cannot move a radio between namespaces at all. The app refuses to touch an adapter that is in use, and it reports why.

### What the driver list cannot tell you

- Whether the driver is loaded on *your* system, and whether its firmware file is present.
- Whether the chip supports AP mode. Some drivers only do client mode. Those adapters are rejected with a clear message and nothing changes on your host.
- Whether the kernel lets the radio move into another namespace. This is only known at the moment of the handover.
- Whether reception is good enough. See below.

## Reading the diagnostics in the Web UI

Open **USB Wi-Fi diagnostics** after pressing **Refresh adapters**. It shows the running kernel, the loaded Wi-Fi related modules (from `/sys/module`), the USB identity, which driver is bound to each USB interface and the WLAN names. A module showing up there is not a compatibility certificate. Nothing is loaded and no firmware is changed by looking.

A USB radio that is currently assigned to the app disappears from the host on purpose. The UI then says *assigned to this app*, not *missing firmware*. It comes back by itself after the run. If a USB reset changes the PHY number, the helper recognises the same device again by its MAC address and device attributes.

If the stick is listed on the USB bus but there is no WLAN interface, plug it directly into a USB port, refresh, look into the host logs for firmware or driver errors and update HAOS the normal way. If the adapter is present but rejected, follow the rejection reason. Never disable Protection mode and never use the Wi-Fi that Home Assistant itself connects through.

## When the signal is the problem

One log from the internal Realtek showed −95 dBm against −60 dBm on the AR9271 in the same spot. The Realtek stayed in authentication and scanning states until the association deadline, and DHCP never started. Lines such as `1/45`, `6/45`, `11/45` are status samples of that wait, not an endless DHCP loop.

That is a reception problem, not an app problem, and no software retry changes it. Move the device closer, use an adapter with an external antenna or try a different one.
