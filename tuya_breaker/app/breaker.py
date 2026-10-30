"""Ingress entry point for Tuya Breaker. Reuse the existing HTTP and lease boundaries."""
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

import server
from devices import Devices
from breaker_runner import BreakerRunner
from request_body import read_body, RequestBodyError


class BreakerDevices(Devices):
    def start(self):
        self.runner.idle()
        self.runner.ensure_ready()
        super().start()


class BreakerHandler(server.Handler):
    server_version = 'TuyaBreaker'

    def do_GET(self):
        path = urlsplit(self.path).path
        backup = re.fullmatch(r'/api/lightleak/backups/([0-9a-f]{32})',path)
        hardware_detail = re.fullmatch(r'/api/cloudcutter/hardware/([0-9a-f]{20})',path)
        if path not in ('/breaker.js', '/hardware.js', '/lightleak.js', '/api/lightleak', '/api/cloudcutter/catalogue', '/api/cloudcutter/credentials', '/api/cloudcutter/hardware') and not hardware_detail and not backup:
            return super().do_GET()
        if not self.trusted():
            return
        if path in ('/breaker.js','/hardware.js','/lightleak.js'):
            return self.reply(200, (server.STATIC/path[1:]).read_bytes(), 'text/javascript; charset=utf-8')
        if path == '/api/lightleak':
            runner=self.server.runner
            return self.reply(200,{'variants':[{'slug':v.slug,'name':v.name,'chip':v.chip}
                                    for v in runner.lightleak.variants.values()], 'backups':runner.backup_files()})
        if backup:
            try:
                file=self.server.runner.backup_file(backup[1])
                return self.reply(200,file.read_bytes(),'application/octet-stream')
            except (OSError,ValueError):
                return self.reply(404,{'error':'Complete backup unavailable'})
        if path == '/api/cloudcutter/hardware' or hardware_detail:
            try:
                result = self.server.runner.hardware.detail(hardware_detail[1]) if hardware_detail else self.server.runner.hardware.snapshot()
                return self.reply(200,result)
            except (OSError,ValueError,KeyError):
                return self.reply(400,{'error':'Hardware cache unavailable; update the device database'})
        if path.endswith('catalogue'):
            return self.reply(200, {'devices': self.server.runner.catalogue.devices()})
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(self.server.runner.credentials.glob('*.json')):
                if file.is_file() and not file.is_symlink():
                    archive.writestr(file.name, file.read_bytes())
        self.reply(200, output.getvalue(), 'application/zip')

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/api/lightleak/configure', '/api/lightleak/backups/delete', '/api/tool', '/api/cloudcutter/catalogue/refresh', '/api/cloudcutter/device', '/api/cloudcutter/configure', '/api/cloudcutter/hardware/refresh'):
            return super().do_POST()
        if not self.trusted():
            return
        import hmac
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token', '').encode(), self.server.csrf.encode()):
            return self.reply(403, {'error': 'Invalid request token; reload the app'})
        try:
            raw, _ = read_body(self.headers, self.rfile, server.MAX_JSON_BODY)
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError('Expected an object')
            # Same lock order as Devices.start: adapter operation, then runner.
            with self.server.devices.operation:
                self.server.runner.idle()
                if self.server.devices.lease:
                    raise ValueError('Wait for adapter return')
                if path == '/api/tool':
                    self.server.runner.choose_tool(value.get('tool'))
                elif path == '/api/lightleak/configure':
                    self.server.runner.configure_lightleak(value)
                elif path == '/api/lightleak/backups/delete':
                    self.server.runner.delete_backup(value.get('id'))
                elif path == '/api/cloudcutter/hardware/refresh':
                    self.server.journal.emit('info','Refreshing the official OpenBeken hardware database')
                    result = self.server.runner.hardware.snapshot(refresh=True)
                    self.server.journal.emit('info',f"OpenBeken hardware cache updated: {len(result['devices'])} reference records; no exploit profile approved")
                    return self.reply(200,result)
                elif path == '/api/cloudcutter/catalogue/refresh':
                    return self.reply(200, {'devices': self.server.runner.catalogue.devices(refresh=True)})
                elif path.endswith('/device'):
                    return self.reply(200, {'profiles': self.server.runner.catalogue.profiles(value.get('device'))})
                else:
                    self.server.runner.configure(value, self.server.firmware)
            return self.reply(200, {'ok': True})
        except RequestBodyError as exc:
            self.close_connection = True
            self.reply(exc.status, {'error': str(exc)})
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            # Never log a configuration body: it can contain Wi-Fi credentials.
            self.server.journal.emit('warning', f'Breaker operation rejected: {type(exc).__name__}')
            self.reply(400, {'error': str(exc)})


def configure_server():
    server.Runner, server.Devices, server.Handler = BreakerRunner, BreakerDevices, BreakerHandler
    server.MAGIC.update(BK7231T=(0, bytes.fromhex('55aa55aa')),
                        RTL8710BN=(8, bytes.fromhex('4f54413118000000')))


def main():
    configure_server()
    return server.main()


if __name__ == '__main__':
    raise SystemExit(main())
