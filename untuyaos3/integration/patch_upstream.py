"""Reviewed adaptations to the pinned upstream. Fail when context drifts."""
from pathlib import Path
import sys


def patch(root):
    connect = root / "scripts/connect.sh"
    text = connect.read_text()
    changes = {
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
