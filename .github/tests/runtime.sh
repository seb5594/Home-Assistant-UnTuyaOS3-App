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

if Path('/opt/webapp/breaker.py').exists():
    import breaker
    breaker.configure_server()

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
import contextlib
import io
import hmac
from hashlib import sha256
from types import SimpleNamespace

with tempfile.TemporaryDirectory() as directory:
    firmware = Path(directory) / 'test.bin'
    firmware.write_bytes(b'MMM\0test')
    uuid = '0123456789abcdef'
    security = b'fedcba9876543210' + hmac.new(uuid.encode(), b'0123456789abcdef', sha256).digest()
    for verbose in (False, True):
        for ending, full, expected in (('finish', True, 0), ('timeout', True, 3), ('eof', True, 3),
                                        ('timeout', False, 1), ('finish', False, 1), ('finish-error', True, 1)):
            frames = [SimpleNamespace(type=0x16, data=b'{"uuid":"0123456789abcdef"}'),
                      SimpleNamespace(type=0x17, data=b'{}'), SimpleNamespace(type=0x04, data=security),
                      SimpleNamespace(type=0x1B, sequence=1,
                                      data=b'{"file_offset":"0","data_block_len":"' + (b'8' if full else b'4') + b'"}')]
            if ending in ('finish', 'finish-error'):
                frames.append(SimpleNamespace(type=0x1C, data=b'', result=1 if ending == 'finish-error' else 0))
            reads = iter([b'frame'] * len(frames))
            def receive(_size):
                try:
                    return next(reads)
                except StopIteration:
                    if ending == 'timeout':
                        raise ota.socket.timeout()
                    return b''
            peer = Mock()
            peer.recv.side_effect = receive
            arguments = ['ap-ota.py', str(firmware)] + (['-v'] if verbose else [])
            with contextlib.redirect_stdout(io.StringIO()) as output, patch.object(sys, 'argv', arguments), \
                 patch.object(ota, 'get_socket', return_value=peer), patch.object(ota, 'sleep'), \
                 patch.object(ota.Lpv35Frame, 'unpack_and_decrypt', side_effect=frames):
                result = ota.main()
            assert result == expected, (verbose, ending, full, result, output.getvalue())
            assert ('Reported OTA finished!' in output.getvalue()) == (expected == 0)
            if expected == 3:
                assert 'not confirmed' in output.getvalue()
        with contextlib.redirect_stdout(io.StringIO()), patch.object(sys, 'argv', ['ap-ota.py', str(firmware)]), \
             patch.object(ota, 'get_socket', side_effect=ConnectionError('TCP refused')):
            assert ota.main() == 1, 'Connection failure must not be reported as success'
print('PASS: actual OTA main distinguishes confirmation, full-transfer timeout, EOF, partial transfer and connection failure in both log modes')
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

if [[ -f /opt/webapp/breaker.py ]]; then
    /opt/cloudcutter-venv/bin/python - <<'CHECK_CLOUDCUTTER'
from pathlib import Path
import sys
sys.path.insert(0, '/opt/cloudcutter/src')
import get_input
from cloudcutter.crypto.pskcontext import PSKContext
from cloudcutter_session import NETWORK
assert str(NETWORK) == '10.204.0.0/24'
assert sys.version_info[:2] == (3, 13)
assert PSKContext()._psk_and_pskid(b'', True) == b''
for chip in ('BK7231T', 'BK7231N', 'RTL8710BN', 'RTL8720CF'):
    files = list((Path('/opt/untuyaos3/custom-firmware') / chip).glob('*.bin'))
    assert files, chip
    assert any(get_input.validate_firmware_file_internal(str(file), chip.lower()).name.startswith('VALID_') for file in files), chip
print('PASS: CloudCutter Python 3.13, binary-PSK bridge, controller and per-chip UG/OTA library')
CHECK_CLOUDCUTTER
    /opt/cloudcutter-venv/bin/python - <<'CHECK_EMBEDDED_SERVERS'
# Exercise both actual embedded entry points: an absent firmware_dir in Detach
# must not break startup, and Detach must expose no firmware-download route.
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    profile = root/'profile.json'
    profile.write_text(json.dumps({'device':{'schemas':{'test':[]}}}))
    config = root/'config.json'
    config.write_text(json.dumps({'uuid':'u'*12,'auth_key':'a'*16,'sec_key':'s'*16,'local_key':'l'*16,'device_id':'d'*20}))
    firmware = next((Path('/opt/untuyaos3/custom-firmware')/'BK7231N').glob('*.bin'))
    for method in ('configure_local_device','update_firmware'):
        args = [method,str(profile),'/opt/cloudcutter/device-profiles/schema',str(config)]
        if method=='update_firmware':
            args += [str(firmware.parent),str(firmware)]
        args += ['30','true','--ip','127.0.0.1']
        if method=='configure_local_device':
            args += ['--ssid','test-network','--password','test-password']
        child = subprocess.Popen(['/opt/cloudcutter-venv/bin/python','-m','cloudcutter',*args],
                                 env={**os.environ,'PYTHONPATH':'/opt/cloudcutter/src'},
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            deadline = time.monotonic()+8
            while True:
                if child.poll() is not None:
                    raise AssertionError(child.stdout.read())
                try:
                    with socket.create_connection(('127.0.0.1',80),timeout=.2):
                        break
                except OSError:
                    if time.monotonic()>deadline:
                        raise AssertionError('Embedded server startup deadline')
                    time.sleep(.1)
            # HTTP, TLS and legacy TLS must all bind only the approved address.
            for line in Path('/proc/net/tcp').read_text().splitlines()[1:]:
                fields = line.split()
                host, port = fields[1].split(':')
                if fields[3]=='0A' and int(port,16) in (80,443,4433):
                    assert host=='0100007F', line
            request = http.client.HTTPConnection('127.0.0.1',80,timeout=3)
            request.request('GET','/files/'+firmware.name)
            response = request.getresponse()
            assert response.status==(404 if method=='configure_local_device' else 200), response.status
            response.read(); request.close()
        finally:
            child.terminate()
            child.wait(5)
            child.stdout.close()
print('PASS: actual CloudCutter Flash/Detach servers start, bind only approved IP, and expose firmware only in Flash mode')
CHECK_EMBEDDED_SERVERS
fi
