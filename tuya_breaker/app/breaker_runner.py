"""Three fixed engines using the same guarded runner and radio lease."""
import json
from pathlib import Path
import re
import shutil
import secrets
import subprocess

from lightleak_protocol import Assets

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
        self.lightleak = Assets()
        self.lightleak_settings = self.lightleak_review = None
        self.backups = self.data / 'lightleak/backups'
        self.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        # No partial dump is advertised or resumed after a process/container restart.
        for partial in self.backups.glob('*.partial'):
            if partial.is_file() and not partial.is_symlink():
                partial.unlink()

    def idle(self):
        if self.state in BUSY or (self.thread and self.thread.is_alive()):
            raise ValueError('Wait for the session and radio cleanup to finish')

    def choose_tool(self, tool):
        with self.lock:
            self.idle()
            if tool not in ('untuyaos3', 'lightleak', 'cloudcutter'):
                raise ValueError('Unknown tool')
            self.tool = tool
            self.engine_name = {'untuyaos3':'UnTuyaOS3','lightleak':'Lightleak','cloudcutter':'CloudCutter'}[tool]
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

    def configure_lightleak(self, request):
        with self.lock:
            self.idle()
            self.lightleak_settings = self.lightleak_review = None
            variant = self.lightleak.variant(request.get('variant'))
            mode = request.get('ap_mode')
            if mode not in ('companion', 'linux'):
                raise ValueError('Choose ESP CustomAP or experimental Linux AP')
            if request.get('understand_writes') is not True:
                raise ValueError('Acknowledge that Lightleak setup writes target flash')
            self.lightleak_settings = {'variant':variant.slug,'ap_mode':mode}
            self.lightleak_review = {'variant':variant.name,'chip':variant.chip,'ap_mode':mode,
                                    'operation':'2 MiB post-exploit backup; setup writes device flash'}
            self.journal.emit('info','Lightleak configuration reviewed: '+json.dumps(self.lightleak_review))

    def backup_files(self):
        result = []
        for file in sorted(self.backups.glob('*.json')):
            if file.is_symlink() or not re.fullmatch(r'[0-9a-f]{32}',file.stem):
                continue
            binary = file.with_suffix('.bin')
            if not binary.is_file() or binary.is_symlink() or binary.stat().st_size != 0x200000:
                continue
            try:
                info = json.loads(file.read_text())
                if info.get('id')==file.stem and info.get('size')==0x200000:
                    result.append(info)
            except (ValueError, OSError):
                continue
        return result

    def backup_file(self, identifier):
        if not isinstance(identifier,str) or not re.fullmatch(r'[0-9a-f]{32}',identifier):
            raise ValueError('Invalid backup identifier')
        if not any(info['id']==identifier for info in self.backup_files()):
            raise ValueError('Complete backup unavailable')
        return self.backups/(identifier+'.bin')

    def delete_backup(self, identifier):
        with self.lock:
            self.idle()
            path=self.backup_file(identifier)
            path.unlink()
            path.with_suffix('.json').unlink(missing_ok=True)

    def status(self):
        return {**super().status(), 'tool': self.tool,
                'engine_ready': self.tool == 'untuyaos3' or (self.settings is not None if self.tool=='cloudcutter' else self.lightleak_settings is not None),
                'cloudcutter_review': self.review, 'lightleak_review': self.lightleak_review}

    def ensure_ready(self):
        if self.tool == 'lightleak':
            if not self.lightleak_settings:
                raise ValueError('Review the Lightleak variant, AP mode and flash-write risk first')
            if len(list(self.backups.glob('*.bin')))>=16:
                raise ValueError('Private backup limit reached (16); download and delete an old backup first')
            if shutil.disk_usage(self.backups).free < 18*1024*1024:
                raise ValueError('Insufficient free space for a complete Lightleak backup')
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
        if self.tool == 'lightleak':
            settings = {**self.lightleak_settings, 'original_power_save':self.options.get('original_power_save'),
                        'output':str(self.backups/(secrets.token_hex(16)+'.bin'))}
            target=root/'lightleak.json'
            target.write_text(json.dumps(settings),encoding='utf-8')
            target.chmod(0o600)
            return ['/opt/venv/bin/python','/opt/webapp/lightleak_session.py',str(target)]
        settings = dict(self.settings)
        shutil.copyfile(settings['profile'], root / 'profile.json')
        settings.update(profile=str(root/'profile.json'), credentials=str(self.credentials),
                        original_power_save=self.options.get('original_power_save'))
        target = root / 'cloudcutter.json'
        target.write_text(json.dumps(settings), encoding='utf-8')
        target.chmod(0o600)
        return ['/opt/cloudcutter-venv/bin/python', '/opt/webapp/cloudcutter_session.py', str(target)]

    def before_cleanup(self, present=True):
        if self.tool in ('cloudcutter','lightleak'):
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
            self.journal.emit('info', f'{self.engine_name} services stopped; selected radio restored to managed mode')

    def _run(self):
        try:
            super()._run()
        finally:
            self.lightleak_settings = None
            if self.tool == 'cloudcutter':
                self.settings = None  # Especially the destination Wi-Fi password.
