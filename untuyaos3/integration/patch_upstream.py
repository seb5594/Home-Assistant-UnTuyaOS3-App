"""Reviewed adaptations to the pinned upstream. Fail when context drifts."""
from pathlib import Path
import sys


def patch(root):
    connect = root / "scripts/connect.sh"
    text = connect.read_text()
    changes = {
        '    while :; do':
            '    local __untuya_scan_deadline=$((SECONDS + 90))\n'
            '    while :; do\n'
            '        if (( SECONDS >= __untuya_scan_deadline )); then\n'
            '            die "No matching open device AP found within 90 seconds. Check AP pairing mode and reception, or select another adapter. DHCP was not started."; return 1\n'
            '        fi\n'
            '        iw dev "$iface" info >/dev/null 2>&1 || { die "Selected Wi-Fi adapter disappeared; session stopped."; return 1; }\n'
            '        local __untuya_remaining=$((__untuya_scan_deadline - SECONDS))\n'
            '        if (( __untuya_remaining > 15 )); then __untuya_remaining=15; fi',
        'raw="$(iw dev "$iface" scan 2>&1)"':
            'raw="$(timeout "${__untuya_remaining}s" iw dev "$iface" scan 2>&1)"',
        'command -v rfkill >/dev/null 2>&1 && rfkill unblock wifi 2>/dev/null':
            ': # Never unblock host radios.',
        'udhcpc -i "$iface" -q -n >/dev/null 2>&1':
            'udhcpc -i "$iface" -q -n -s /opt/webapp/dhcp.sh',
        'iw dev "$iface" connect -w "$match" || { die "failed to associate with \'$match\'"; return 1; }':
            'python /opt/webapp/association.py "$iface" "$match" || { die "Wi-Fi association was not verified; DHCP skipped. Review the Wi-Fi diagnostics above."; return 1; }',
    }
    for old, new in changes.items():
        if text.count(old) != 1:
            raise RuntimeError(f"Upstream context changed: {old}")
        text = text.replace(old, new)
    connect.write_text(text)
    (root / "scripts/restore-network.sh").write_text(
        '#!/usr/bin/env bash\nprintf "Adapter cleanup is handled by the Home Assistant app.\\n"\n'
    )


if __name__ == "__main__":
    patch(Path(sys.argv[1]))
