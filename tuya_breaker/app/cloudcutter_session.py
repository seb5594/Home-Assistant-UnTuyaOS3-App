"""Fixed CloudCutter workflow inside the leased namespace; never invoke its host launcher."""
import argparse
from contextlib import redirect_stdout
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import signal
import socket
import subprocess
import sys
import threading
import time

from association import access_points, associate
from ota_target import approved_adapter, load_target, state_path
from supplicant import Control, Supplicant
from wifi import command, same_device

ROOT = Path('/opt/cloudcutter/src')
GATEWAY = '10.204.0.1'
NETWORK = ipaddress.ip_network(GATEWAY + '/24', strict=False)
SECRET_LINE = re.compile(r'auth.?key|local.?key|sec.?key|psk.?key|uuid|device.?id|dev.?id|"passwd"|"password"', re.I)


def log(text):
    print(text, flush=True)


class RedactedOutput:
    """Line-buffer secret-bearing upstream output before it reaches the shared journal."""
    def __init__(self, target):
        self.target, self.pending = target, ''

    def write(self, text):
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.target.write(('[Private protocol credentials redacted]' if SECRET_LINE.search(line) else line) + '\n')
            self.target.flush()
        return len(text)

    def flush(self):
        self.target.flush()

    def finish(self):
        if self.pending:
            self.write('\n')


def prompt(message, choices):
    log(message)
    for index, label in enumerate(choices, 1):
        log(f'  [{index}] {label}')
    while True:
        value = input(f'Enter choice [1-{len(choices)}]: ').strip()
        if value.isdigit() and 1 <= int(value) <= len(choices):
            return int(value) - 1
        log('Choose one of the numbered options above.')


class Session:
    def __init__(self, settings, root):
        self.settings, self.root = settings, root
        self.adapter = approved_adapter(os.environ)
        self.cancelled = threading.Event()
        self.connection, self.children = None, []
        self.ssid = self.bssid = None

    def checked(self, *args):
        same_device(self.adapter)
        return command(*args)

    def stop_services(self):
        for child in reversed(self.children):
            if child.poll() is None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
                try:
                    child.wait(3)
                except subprocess.TimeoutExpired:
                    try:
                        child.kill()
                    except ProcessLookupError:
                        pass
                    child.wait(3)
        self.children.clear()

    def managed(self):
        self.checked('ip', 'link', 'set', 'dev', self.adapter.name, 'down')
        self.checked('ip', '-4', 'addr', 'flush', 'dev', self.adapter.name)
        self.checked('iw', 'dev', self.adapter.name, 'set', 'type', 'managed')

    def close_connection(self):
        if self.connection:
            connection, self.connection = self.connection, None
            connection.close()
        self.checked('iw', 'dev', self.adapter.name, 'disconnect')
        self.checked('ip', '-4', 'addr', 'flush', 'dev', self.adapter.name)
        state_path(os.environ).unlink(missing_ok=True)

    def connect(self, after_exploit=False):
        self.connection = Supplicant(self.adapter, self.settings.get('original_power_save'),
                                     lambda level, text, channel='wifi': log(f'[Wi-Fi] {text}'),
                                     self.cancelled, new_session=False)
        control_path = self.connection.start()
        deadline = time.monotonic() + 90
        log('Scanning for the target AP; deadline 90 seconds.')
        while time.monotonic() < deadline:
            scan = self.checked('iw', 'dev', self.adapter.name, 'scan')
            names = sorted(set(re.findall(r'(?m)^\s*SSID: (.+)$', scan)))
            if after_exploit:
                names = [name for name in names if name == 'A-' + self.ssid[-4:]]
            else:
                names = [name for name in names if re.fullmatch(r'(?:SmartLife|TuyaSmart|A)-[A-Za-z0-9]{4}', name)]
            names = [name for name in names if access_points(scan, name)]
            if names:
                break
            log('No matching open AP yet; restore AP pairing mode on the target.')
            time.sleep(2)
        else:
            raise RuntimeError('Target AP scan deadline reached; no later stage was attempted')
        selected = names[prompt('Select your target device AP:', names)] if len(names)>1 else names[0]
        if not after_exploit:
            self.ssid = selected
        log(f'Connecting only to selected AP {selected!r}')
        with Control(control_path) as control:
            associate(self.adapter, selected, log=log, control=control)
        self.checked('ip', '-4', 'addr', 'flush', 'dev', self.adapter.name)
        state_path(os.environ).unlink(missing_ok=True)
        result = subprocess.run(['udhcpc', '-f', '-q', '-n', '-i', self.adapter.name,
                                 '-s', '/opt/webapp/dhcp.sh', '-t', '5', '-T', '3'], timeout=25)
        if result.returncode:
            raise RuntimeError('DHCP failed; no device protocol command was sent')
        target = load_target()
        log(f'Verified device endpoint: {target} via {self.adapter.name}')
        return target

    def send(self, payload):
        from cloudcutter.exploit import build_network_config_packet
        target = load_target()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, (self.adapter.name+'\0').encode())
            datagram = build_network_config_packet(payload)
            for _ in range(4):
                same_device(self.adapter)
                client.sendto(datagram, (target, 6669))
                time.sleep(.05)

    def spawn(self, args):
        # Children share the controller's process group. Runner kills that exact
        # group after every outcome, including abrupt exits in upstream MQTT.
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, close_fds=True)
        self.children.append(child)
        return child

    def ap(self, services=True):
        self.checked('ip', 'link', 'set', 'dev', self.adapter.name, 'down')
        self.checked('iw', 'dev', self.adapter.name, 'set', 'type', '__ap')
        control_dir = self.root/'hostapd'
        control_dir.mkdir(exist_ok=True)
        config = self.root/'hostapd.conf'
        config.write_text(f'interface={self.adapter.name}\ndriver=nl80211\nctrl_interface={control_dir}\n'
                          'ssid=cloudcutterflash\nhw_mode=g\nchannel=6\nwmm_enabled=1\nauth_algs=1\n'
                          'wpa=2\nwpa_key_mgmt=WPA-PSK\nwpa_passphrase=abcdabcd\nrsn_pairwise=CCMP\n')
        process = self.spawn(['hostapd', str(config)])
        for _ in range(80):
            same_device(self.adapter)
            if process.poll() is not None:
                raise RuntimeError('hostapd failed: AP mode could not start on the selected radio')
            path = control_dir/self.adapter.name
            if path.exists():
                with Control(path) as control:
                    if 'state=ENABLED' in control.request('STATUS'):
                        break
            time.sleep(.1)
        else:
            raise RuntimeError('Selected radio did not enter AP mode within 8 seconds')
        log('Real AP-mode startup verified on the selected radio.')
        if not services:
            return
        self.checked('ip', 'addr', 'add', GATEWAY+'/24', 'dev', self.adapter.name)
        self.checked('ip', 'addr', 'add', '10.204.0.2/32', 'dev', self.adapter.name)
        self.checked('ip', 'addr', 'add', '10.204.0.3/32', 'dev', self.adapter.name)
        self.spawn(['dnsmasq', '--keep-in-foreground', '--conf-file=/dev/null', '--no-resolv',
                    '--interface='+self.adapter.name, '--bind-interfaces', '--listen-address='+GATEWAY,
                    '--except-interface=lo', '--dhcp-range=10.204.0.10,10.204.0.40,12h',
                    '--dhcp-option=option:router,'+GATEWAY,
                    '--dhcp-option=option:dns-server,10.204.0.1,10.204.0.2,10.204.0.3',
                    '--dhcp-option=option:netmask,255.255.255.0', '--address=/#/'+GATEWAY,
                    '--dhcp-leasefile='+str(self.root/'leases'), '--user=root', '--log-dhcp', '--log-facility=-',
                    '--pid-file='+str(self.root/'dnsmasq.pid')])
        mqtt = self.root/'mosquitto.conf'
        mqtt.write_text(f'user root\nlistener 1883 {GATEWAY}\nlistener 1883 127.0.0.1\nallow_anonymous true\npersistence false\n')
        self.spawn(['mosquitto', '-c', str(mqtt), '-v'])
        time.sleep(.5)
        if any(child.poll() is not None for child in self.children):
            raise RuntimeError('A scoped CloudCutter AP service failed to start')

    def run(self):
        sys.path.insert(0, str(ROOT))
        from cloudcutter import exploit
        settings = self.settings
        combined = json.loads(Path(settings['profile']).read_text())
        # A dedicated network namespace prevents port collisions; an explicit
        # forward policy also prevents the device AP from routing through eth0.
        table = f'breaker_{os.getpid()}'
        subprocess.run(['nft', '-f', '-'], input=f'add table inet {table}\n'
                       f'add chain inet {table} forward {{ type filter hook forward priority 0; policy drop; }}\n',
                       text=True, check=True, timeout=8)
        log('Forwarding between the device radio and container uplink is blocked.')
        if settings['method'] == 'flash':
            import get_input
            validity = get_input.validate_firmware_file_internal(settings['firmware'], settings['chip'].lower())
            if not validity.name.startswith('VALID_'):
                raise ValueError('CloudCutter rejected the image/chip combination before exploitation')
        # Refuse a conflicting AP subnet before changing the target device.
        for route in json.loads(command('ip', '-4', '-j', 'route', 'show', 'table', 'all')):
            if route.get('dev') != self.adapter.name and route.get('dst') not in (None, 'default'):
                if ipaddress.ip_network(route['dst'], strict=False).overlaps(NETWORK):
                    raise ValueError('CloudCutter AP subnet overlaps the app network')
        log('Checking real AP startup before sending any exploit to the target.')
        try:
            self.ap(services=False)
        finally:
            self.stop_services()
            self.managed()
        target = self.connect()
        if prompt('Verify the original device firmware matches the selected CloudCutter profile. Continue?',
                  ['Profile matches; send exploit', 'Stop without sending the exploit']) != 0:
            return 1
        return self.exploit_and_flash(exploit, combined, target)

    def exploit_and_flash(self, exploit, combined, target):
        args = argparse.Namespace(local_key='', device_id='', verbose_output=True, victim_ip=target)
        original_send = exploit.send_network_config_datagram
        def guarded_send(datagram, victim_ip):
            if victim_ip != load_target():
                raise ValueError('Device endpoint changed')
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, (self.adapter.name+'\0').encode())
                client.sendto(datagram, (victim_ip, 6669))
        exploit.send_network_config_datagram = guarded_send
        try:
            config = exploit.exploit_device_with_config(args, combined)
        finally:
            exploit.send_network_config_datagram = original_send
        credential = Path(self.settings['credentials'])/(self.root.name+'.json')
        config.write(credential)
        credential.chmod(0o600)
        log('Exploit attempt sent. Private local credentials retained; this alone is not proof of success.')
        self.close_connection()
        if prompt('Power-cycle the target and put it into AP pairing mode again.',
                  ['Device is in AP pairing mode; continue', 'Stop here']) != 0:
            return 1
        self.connect(after_exploit=True)
        self.send(json.dumps({'ssid':'cloudcutterflash', 'passwd':'abcdabcd', 'token':'AAAAAAAA'}).encode('ascii'))
        self.close_connection()
        self.ap()
        schema = str(ROOT.parent/'device-profiles/schema')
        # Schema files are copied into the image by the Docker build.
        if self.settings['method'] == 'flash':
            firmware = self.settings['firmware']
            arguments = ['update_firmware', self.settings['profile'], schema, str(credential),
                         str(Path(firmware).parent), firmware, '30', 'true', '--ip', GATEWAY]
        else:
            arguments = ['configure_local_device', self.settings['profile'], schema, str(credential), '30', 'true',
                         '--ip', GATEWAY, '--ssid', self.settings['ssid'], '--password', self.settings['password']]
        log('Device must now join the private cloudcutterflash AP. Follow its requests below.')
        sys.argv = ['cloudcutter', *arguments]
        try:
            runpy.run_module('cloudcutter', run_name='__main__')
        except SystemExit as exc:
            return 3 if exc.code in (0, None) and self.settings['method']=='flash' else (exc.code or 0)
        return 3 if self.settings['method']=='flash' else 0

    def close(self):
        self.stop_services()
        if self.connection:
            self.close_connection()


def main():
    root = Path(os.environ['UNTUYAOS3_RUN_DIR'])
    path = Path(sys.argv[1])
    if path != root/'cloudcutter.json':
        raise ValueError('Invalid fixed session configuration path')
    session = Session(json.loads(path.read_text()), root)
    def interrupted(*_):
        raise InterruptedError('Session cancellation requested')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    output = RedactedOutput(sys.stdout)
    try:
        with redirect_stdout(output):
            return session.run()
    except (Exception, KeyboardInterrupt) as exc:
        log(f'CloudCutter session stopped: {type(exc).__name__}: {exc}')
        return 1
    finally:
        session.close()
        output.finish()


if __name__ == '__main__':
    raise SystemExit(main())
