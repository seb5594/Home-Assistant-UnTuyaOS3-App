# Using UnTuyaOS3

Install **UnTuyaOS3 Wi-Fi Helper** from the same repository. In both apps' Configuration tabs, enter the exact dedicated Wi-Fi name and the same pairing secret of at least 32 characters.

Start the helper first, then this app. Select **Open Web UI**, press **Start interactive session**, and submit the script's numeric choices. Console and diagnostics update continuously.

Integrated and USB Wi-Fi require AP and namespace support. The dedicated interface must be disconnected, without addresses/routes or bridge membership. Use Ethernet for Home Assistant management.

Upload additional UG images in the web interface. **Download logs** exports diagnostics. If startup fails, read both apps' **Log** tabs. No terminal commands are required.

Stop this app after use. The helper restores the radio and exits. See the English repository README for full instructions and permissions.
