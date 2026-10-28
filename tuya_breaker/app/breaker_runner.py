"""Two fixed engines using the same guarded runner and radio lease."""
import json
from pathlib import Path
import re
import shutil
import subprocess

from runner import Runner
from wifi import command, same_device
from breaker_catalog import Catalogue
from hardware_catalogue import HardwareCatalogue

BUSY = ('running', 'assigning', 'cleaning', 'releasing')


class BreakerRunner(Runner):
    def __init__(self, *args, data=Path('/data'), **kwargs):
        super().__init__(*args, **kwargs)
        self.tool, self.settings, self.review = 'untuyaos3', None, None
        self.data = Path(data)
        self.catalogue = Catalogue(self.data / 'cloudcutter/profiles')
        self.hardware = HardwareCatalogue(self.data / 'openbeken')
        self.credentials = self.data / 'cloudcutter/credentials'
        self.credentials.mkdir(parents=True, exist_ok=True, mode=0o700)

    def idle(self):
        if self.state in BUSY or (self.thread and self.thread.is_alive()):
            raise ValueError('Wait for the session and radio cleanup to finish')

    def choose_tool(self, tool):
        with self.lock:
            self.idle()
            if tool not in ('untuyaos3', 'cloudcutter'):
                raise ValueError('Unknown tool')
            self.tool = tool
            self.engine_name = 'CloudCutter' if tool == 'cloudcutter' else 'UnTuyaOS3'
            self.journal.emit('info', f'Selected tool: {tool}')

    def configure(self, request, firmware):
        """Caller holds Devices.operation; keep status polling responsive during downloads."""
        with self.lock:
            self.idle()
            self.settings = self.review = None
        method = request.get('method')
        if method not in ('flash', 'detach'):
            raise ValueError('Choose Flash or Detach')
        profile_path, combined = self.catalogue.combined(request.get('device'), request.get('profile'))
        chip = combined['profile']['firmware']['chip'].upper()
        settings = {'method': method, 'profile': str(profile_path), 'chip': chip}
        if method == 'flash':
            name = request.get('firmware', '')
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.bin', name):
                raise ValueError('Select a matching firmware image')
            image = Path(firmware) / chip / name
            if not image.is_file() or image.is_symlink():
                raise ValueError('Firmware image is unavailable; upload it first')
            settings['firmware'] = str(image)
        else:
            ssid, password = request.get('ssid', ''), request.get('password', '')
            if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32 or any(ord(c)<32 for c in ssid):
                raise ValueError('Destination SSID must be 1–32 bytes without control characters')
            if not isinstance(password, str) or (password and not 8 <= len(password.encode()) <= 63) or any(ord(c)<32 for c in password):
                raise ValueError('Destination password must be empty (open Wi-Fi) or 8–63 bytes')
            settings.update(ssid=ssid, password=password)
        self.settings = settings
        self.review = {'device': combined['device']['name'], 'profile': combined['profile']['name'],
                       'chip': chip, 'method': method, 'firmware': Path(settings['firmware']).name if method == 'flash' else None}
        self.journal.emit('info', 'CloudCutter configuration reviewed: ' + json.dumps(self.review))

    def status(self):
        return {**super().status(), 'tool': self.tool,
                'engine_ready': self.tool == 'untuyaos3' or self.settings is not None,
                'cloudcutter_review': self.review}

    def ensure_ready(self):
        if self.tool == 'cloudcutter' and not self.settings:
            raise ValueError('Review the exact CloudCutter profile and operation first')
        if self.tool == 'cloudcutter' and len(list(self.credentials.glob('*.json'))) >= 100:
            raise ValueError('Private credential storage limit reached; back up and remove old files before another run')

    def prepare_connection(self):
        self.ensure_ready()
        return super().prepare_connection() if self.tool == 'untuyaos3' else (None, None)

    def session_command(self, session_dir):
        if self.tool == 'untuyaos3':
            return super().session_command(session_dir)
        root = Path(session_dir)
        settings = dict(self.settings)
        shutil.copyfile(settings['profile'], root / 'profile.json')
        settings.update(profile=str(root/'profile.json'), credentials=str(self.credentials),
                        original_power_save=self.options.get('original_power_save'))
        target = root / 'cloudcutter.json'
        target.write_text(json.dumps(settings), encoding='utf-8')
        target.chmod(0o600)
        return ['/opt/cloudcutter-venv/bin/python', '/opt/webapp/cloudcutter_session.py', str(target)]

    def before_cleanup(self, present=True):
        if self.tool == 'cloudcutter':
            if self.process:
                table = f'breaker_{int(self.process.pid)}'
                exists = subprocess.run(['nft', 'list', 'table', 'inet', table], capture_output=True, timeout=8)
                if exists.returncode == 0:
                    subprocess.run(['nft', 'delete', 'table', 'inet', table], check=True, timeout=8)
            if not present:
                return
            same_device(self.adapter)
            command('ip', 'link', 'set', 'dev', self.adapter.name, 'down')
            command('iw', 'dev', self.adapter.name, 'set', 'type', 'managed')
            self.journal.emit('info', 'CloudCutter services stopped; selected radio restored to managed mode')

    def _run(self):
        try:
            super()._run()
        finally:
            if self.tool == 'cloudcutter':
                self.settings = None  # Especially the destination Wi-Fi password.
