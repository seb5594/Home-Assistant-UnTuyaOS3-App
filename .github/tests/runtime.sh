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

data = Path(tempfile.mkdtemp())
library = server.prepare_firmware(Path('/opt/untuyaos3'), data)
for platform in server.MAGIC:
    images = [path for path in (library / platform).iterdir() if path.is_file()]
    assert images, platform
    assert all(server.firmware_valid(platform, path.read_bytes()) for path in images), platform
print('PASS: upstream dependencies and persistent UG firmware library')
PY
    bash /opt/untuyaos3/UnTuyaOS3.sh --help
    echo 'PASS: upstream entry point'
else
    test -f /opt/helper/broker.py
    python -c 'import broker, protocol'
    iw --version
    busctl --version
    echo 'PASS: Wi-Fi helper and namespace authentication imports'
fi
