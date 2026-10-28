"""Exact, fail-closed embedding patches; never run the upstream Docker/host launcher."""
from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'src'
path = root / 'cloudcutter/__main__.py'
source = path.read_text()
for old, new in [
    ('http_server.listen(80)', 'http_server.listen(80, address=args.ip)'),
    ('https_server.listen(443)', 'https_server.listen(443, address=args.ip)'),
    ('dns_https_server.listen(4433)', 'dns_https_server.listen(4433, address=args.ip)'),
    ("(f'/files/(.*)', handlers.OTAFilesHandler, dict(path=\"/work/custom-firmware/\", graceful_exit_timeout=args.flash_timeout, verbose_output=args.verbose_output)),",
     "*([(r'/files/(.*)', handlers.OTAFilesHandler, dict(path=args.firmware_dir, graceful_exit_timeout=args.flash_timeout, verbose_output=args.verbose_output))] if update_firmware else []),")
]:
    if source.count(old) != 1:
        raise RuntimeError(f'CloudCutter embedding patch drift: {old}')
    source = source.replace(old, new)
path.write_text(source)
# Upstream's "nearly complete" MQTT heuristic is not a verified firmware boot.
path = root / 'cloudcutter/protocol/mqtt.py'
source = path.read_text()
if source.count('os._exit(0)') != 1:
    raise RuntimeError('CloudCutter completion patch drift')
path.write_text(source.replace('os._exit(0)', 'os._exit(3)'))
