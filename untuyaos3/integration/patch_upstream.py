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
    ota = root / "scripts/ap-ota.py"
    text = ota.read_text()
    changes = {
        'VICTIM_IP = "192.168.176.1"':
            'sys.path.insert(0, "/opt/webapp")\n'
            'from ota_target import load_target, expect_frame_type\n'
            'from ota_progress import TransferProgress',
        '    for attempt in range(1, SOCKET_RETRIES + 1):\n        sock = socket.socket':
            '    target = load_target()\n'
            '    for attempt in range(1, SOCKET_RETRIES + 1):\n        sock = socket.socket',
        '            sock.connect((VICTIM_IP, 6668))':
            '            import os\n'
            '            interface = os.environ["UNTUYAOS3_ALLOWED_IFACE"]\n'
            '            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\\0")\n'
            '            print(f"Connecting to validated device target {target}:6668 via {interface}")\n'
            '            sock.connect((target, 6668))',
    }
    for expected in ("FRM_AP_CFG_GET_DEV_INFO", "FRM_AP_CFG_SET_DEV_SCHEMA", "FRM_SECURITY_TYPE4"):
        changes[f"assert frame.type == {expected}"] = f"expect_frame_type(frame, {expected})"
    changes.update({
        '        result = int.from_bytes(frame.data[0:4], "little")':
            '        result = int.from_bytes(frame.data[0:4], "little")\n'
            '        frame.result = result',
        '        return\n    VERBOSE =': '        return 2\n    VERBOSE =',
        '        print("Upgrade path is not a file")\n        return':
            '        print("Upgrade path is not a file")\n        return 1',
        '            return\n\n        # FRM_AP_CFG_GET_DEV_INFO':
            '            return 1\n\n        # FRM_AP_CFG_GET_DEV_INFO',
        '        return\n\n    # FRM_SECURITY_TYPE3':
            '        return 1\n\n    # FRM_SECURITY_TYPE3',
        '    ota_send_complete = False':
            '    transfer = TransferProgress(total)\n    ota_result = 3',
        '        except socket.timeout:\n'
        '            if ota_send_complete is False:\n'
        '                print("Socket timed out while attempting OTA.  Please try again.")\n'
        '                return\n'
        '            else:\n'
        '                print("\\nOTA upload completed, but we didn\'t get a final confirmation packet.  Check to see if your device rebooted to custom firmware, otherwise try again.")\n'
        '                break\n'
        '        if not msg:\n'
        '            break':
            '        except socket.timeout:\n'
            '            ota_result = transfer.incomplete_result()\n'
            '            break\n'
            '        if not msg:\n'
            '            ota_result = transfer.incomplete_result()\n'
            '            break',
        '            print("Reported OTA finished!")\n            break':
            '            if transfer.complete and frame.result == 0:\n'
            '                print("Reported OTA finished!")\n'
            '                ota_result = 0\n'
            '            else:\n'
            '                print("Device OTA finish response did not confirm a complete successful transfer.")\n'
            '                ota_result = 1\n'
            '            break',
        '            if offset + length >= total:\n                ota_send_complete = True\n': '',
        '        f.seek(offset, SEEK_SET)':
            '        if offset < 0 or length <= 0 or offset >= total:\n'
            '            raise RuntimeError("Device requested an invalid firmware byte range")\n'
            '        f.seek(offset, SEEK_SET)',
        '        sock.sendall(frame.encrypt_and_pack(session_key))':
            '        sock.sendall(frame.encrypt_and_pack(session_key))\n'
            '        transfer.record(offset, len(chunk))',
        '    sock.shutdown(socket.SHUT_RDWR)\n    sock.close()\n\n\nif __name__':
            '    try:\n'
            '        sock.shutdown(socket.SHUT_RDWR)\n'
            '    except OSError:\n'
            '        pass\n'
            '    finally:\n'
            '        sock.close()\n'
            '    return ota_result\n\n\nif __name__',
        'if __name__ == "__main__":\n    main()':
            'if __name__ == "__main__":\n    raise SystemExit(main())',
    })
    for old, new in changes.items():
        if text.count(old) != 1:
            raise RuntimeError(f"Upstream OTA context changed: {old}")
        text = text.replace(old, new)
    ota.write_text(text)
    (root / "scripts/restore-network.sh").write_text(
        '#!/usr/bin/env bash\nprintf "Adapter cleanup is handled by the Home Assistant app.\\n"\n'
    )


if __name__ == "__main__":
    patch(Path(sys.argv[1]))
