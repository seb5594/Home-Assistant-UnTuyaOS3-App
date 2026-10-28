# Using UnTuyaOS3

Experimental. Install **UnTuyaOS3 Wi-Fi Helper** from the same repository. Enter the same private pairing secret of at least 32 characters in both apps' Configuration tabs. No interface name or hostname is required. Update both apps together; 1.0.0-beta.2 uses helper protocol v3.

Start the helper first, then this app. Open the Web UI. A single eligible adapter is selected automatically; choose from the dropdown when several are available. **Refresh adapters** detects newly plugged USB devices. **USB detection** distinguishes enumeration, driver binding and a usable WLAN interface. Press **Start interactive session** and submit the script's numeric choices. Console and diagnostics update continuously.

Integrated and USB Wi-Fi require AP and namespace support. The dedicated interface must be disconnected, without addresses/routes or bridge membership. Use Ethernet for Home Assistant management.

Upload additional UG images in the Web UI. **Clear logs** clears saved app logs and both panels without stopping a session. **Download logs** exports retained logs; download before restarting because each app starts with fresh logs. Home Assistant's own Log history is managed separately. If startup fails, read both apps' **Log** tabs. No terminal commands are required.

The private nl80211 controller retries association and verifies the live link before DHCP. It temporarily disables power saving only when the original setting can be restored. Restore the device's AP pairing mode, check antennas or choose another adapter when reception is very weak. A driver/reception fault cannot be guaranteed fixed by these retries.

After each completed, failed or cancelled session, the radio is returned and the dropdown unlocks when restoration finishes. The initial AP scan stops after 90 seconds without a match. A missing adapter aborts the run; reconnect USB hardware and refresh after recovery. Stop the app after use. The helper restores the original settings and stays ready. See the English repository README for full instructions and permissions.
