#!/usr/bin/env bash
set -Eeuo pipefail

test -x /run.sh
bash -n /run.sh
echo 'PASS: executable service script'

if [[ -f /opt/webapp/server.py ]]; then
    python - <<'PY'
from pathlib import Path
import tempfile
import sslpsk3
import Crypto
import datastruct
import server
import association

data = Path(tempfile.mkdtemp())
library = server.prepare_firmware(Path('/opt/untuyaos3'), data)
for platform in server.MAGIC:
    images = [path for path in (library / platform).iterdir() if path.is_file()]
    assert images, platform
    assert all(server.firmware_valid(platform, path.read_bytes()) for path in images), platform
print('PASS: upstream dependencies and persistent UG firmware library')
PY
    python - <<'CHECK_TARGET'
import importlib.util
from pathlib import Path
import os
import sys
import tempfile
from hashlib import md5
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('patched_ota', '/opt/untuyaos3/scripts/ap-ota.py')
ota = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ota
spec.loader.exec_module(ota)
peer = Mock()
with patch.object(ota, 'load_target', return_value='192.168.175.1'), \
     patch.dict(os.environ, {'UNTUYAOS3_ALLOWED_IFACE': 'wlan-test'}), \
     patch.object(ota.socket, 'socket', return_value=peer):
    assert ota._connect_tcp() is peer
peer.connect.assert_called_once_with(('192.168.175.1', 6668))
peer.setsockopt.assert_called_once_with(ota.socket.SOL_SOCKET, ota.socket.SO_BINDTODEVICE, b'wlan-test\0')
with tempfile.TemporaryDirectory() as directory:
    firmware = Path(directory) / 'test.bin'
    firmware.write_bytes(b'MMM\0test')
    app_key = md5(bytes.fromhex('4f 58 4c 76 73 6c 43 76 55 78 63 54 50 4c 47 4f')).digest()
    unsolicited = ota.Lpv35Frame(type=0x0C, data=b'\0\0\0\0{}').encrypt_and_pack(app_key)
    peer = Mock()
    peer.recv.return_value = unsolicited
    with patch.object(sys, 'argv', ['ap-ota.py', str(firmware), '-v']), patch.object(ota, 'get_socket', return_value=peer):
        try:
            ota.main()
        except RuntimeError as exc:
            assert '0x0C; expected 0x16' in str(exc), str(exc)
        else:
            raise AssertionError('Unexpected AP frame must stop before schema or OTA commands')
    assert peer.sendall.call_count == 1
print('PASS: patched OTA uses validated .175 endpoint and stops on unexpected AP response')
CHECK_TARGET
    python - <<'CHECK_ASSOCIATION'
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    marker = root / 'dhcp-started'
    scan = 'BSS 20:f1:b2:d7:08:02(on wlan-test)\n\tfreq: 2412\n\tSSID: SmartLife-0803\n'
    scripts = {
        'iw': "#!/bin/sh\ncat <<'SCAN'\n" + scan + 'SCAN\n',
        'ip': '#!/bin/sh\nexit 0\n',
        'id': '#!/bin/sh\nprintf "0\\n"\n',
        'sleep': '#!/bin/sh\nexit 0\n',
        'python': '#!/bin/sh\nexit 1\n',
        'udhcpc': '#!/bin/sh\ntouch ' + shlex.quote(str(marker)) + '\n',
    }
    for name, content in scripts.items():
        script = root / name
        script.write_text(content)
        script.chmod(0o755)
    result = subprocess.run(['/bin/bash', '/opt/untuyaos3/scripts/connect.sh', 'wlan-test'],
                            env={**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH']},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert 'DHCP skipped' in result.stderr, result.stderr
    assert not marker.exists(), 'DHCP must not start when association verification fails'
    # Exercise the real deadline branch immediately in a throwaway script;
    # no wall-clock wait or radio is needed to verify its failure boundary.
    bounded = root / 'bounded-connect.sh'
    bounded.write_text(Path('/opt/untuyaos3/scripts/connect.sh').read_text().replace('SECONDS + 90', 'SECONDS + 0'))
    result = subprocess.run(['/bin/bash', str(bounded), 'wlan-test'],
                            env={**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH']},
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert 'No matching open device AP found within 90 seconds' in result.stderr, result.stderr
    assert not marker.exists()
print('PASS: pinned upstream blocks DHCP after failed association verification')
CHECK_ASSOCIATION
    bash /opt/untuyaos3/UnTuyaOS3.sh --help
    echo 'PASS: upstream entry point'
else
    test -f /opt/helper/broker.py
    python -c 'import broker, protocol'
    iw --version
    busctl --version
    echo 'PASS: Wi-Fi helper and namespace authentication imports'
fi
