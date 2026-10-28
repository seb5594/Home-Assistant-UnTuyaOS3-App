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
