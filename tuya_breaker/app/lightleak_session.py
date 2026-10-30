"""Bounded Lightleak controller using the existing isolated radio and PTY.

Port of the upstream Android workflow; experimental until checked on physical devices.
Neither the firmware exploit nor the backup is claimed to be non-destructive.
"""
from contextlib import redirect_stdout
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import struct
import subprocess
import sys
import time
import zlib

from association import AccessPoint, access_points, link_matches
from cloudcutter_session import Session, RedactedOutput, log, prompt
from lightleak_protocol import Assets, packet, parse_response, words
from ota_target import load_target, state_path
from supplicant import Control, Supplicant
from wifi import command, same_device

IDLE_SSID='LightleakIdle'
IDLE_PASSWORD=b'cl0udcutt3r!@#'
CUSTOM_SSID='LightleakCustom'
FLASH_SIZE=0x200000
# The BK7231N IP stager's final CRC assumes an address beginning with 10.0.
# Match the upstream CustomAP network exactly, including in native Linux mode.
GATEWAY='10.0.0.1'
NETWORK=ipaddress.ip_network(GATEWAY+'/24',strict=False)


def psk(password, ssid):
    return hashlib.pbkdf2_hmac('sha1',password,ssid.encode('utf-8'),4096,32).hex()


def custom_ap_packet(stager):
    if len(stager)!=62 or b'\0' in stager:
        raise ValueError('Invalid CustomAP stager')
    data=CUSTOM_SSID.encode().ljust(33,b'\0')+stager.ljust(63,b'\0')+words(8000)
    return b'cctr'+bytes([104])+data+words(zlib.crc32(data))


class DumpReceiver:
    """Only accept complete, CRC-valid 1024-byte blocks from this request and endpoint."""
    def __init__(self, variant, target, local, client, guard, send, clock=time.monotonic):
        self.variant,self.target,self.local=variant,target,local
        self.client,self.guard,self.send,self.clock=client,guard,send,clock
        self.request_id=secrets.randbelow(0x7FFFFFFF)+1

    def read(self, output, progress=log):
        blocks=[None]*(FLASH_SIZE//1024)
        deadline=self.clock()+300
        failures=0
        while None in blocks:
            self.guard()
            if self.clock()>deadline:
                raise RuntimeError('Flash read deadline reached; incomplete backup was discarded')
            start=blocks.index(None)
            count=1
            while count<8 and start+count<len(blocks) and blocks[start+count] is None:
                count+=1
            self.request_id=(self.request_id+1)&0xFFFFFFFF
            self.send(self.variant.read(start*1024,count,self.request_id,self.local))
            until=self.clock()+.6
            received=0
            while self.clock()<until and received<count:
                self.guard()
                try:
                    datagram,peer=self.client.recvfrom(2048)
                except socket.timeout:
                    continue
                if peer[0]!=self.target:
                    continue
                try:
                    data=parse_response(datagram,self.request_id)
                    if len(data)!=1032:
                        continue
                    offset,length=struct.unpack_from('<II',data)
                    index=offset//1024
                    if length!=1024 or offset%1024 or not start<=index<start+count:
                        continue
                    if blocks[index] is not None and blocks[index]!=data[8:]:
                        raise RuntimeError('Conflicting flash bytes; refusing to certify this backup')
                    if blocks[index] is None:
                        blocks[index]=data[8:]
                        received+=1
                except ValueError:
                    continue
            if not received:
                failures+=1
                if failures>=10:
                    raise RuntimeError('No valid flash blocks after 10 requests; incomplete backup discarded')
            else:
                failures=0
                done=sum(block is not None for block in blocks)
                progress(f'[Lightleak] Backup {done*100//len(blocks)}% · {done*1024}/{FLASH_SIZE} bytes')
        for block in blocks:
            output.write(block)
        output.flush()
        return hashlib.sha256(b''.join(blocks)).hexdigest()


class LightleakSession(Session):
    def __init__(self, settings, root):
        super().__init__(settings,root)
        self.assets=Assets()
        self.variant=self.assets.variant(settings['variant'])
        self.stager=self.assets.binary(self.variant,'stager')
        self.proper=self.assets.binary(self.variant,'proper')
        self.target_point=None

    def close_connection(self):
        # A target switching from AP to station may already have dropped the link.
        # Stopping our own supplicant is authoritative; an ENOTCONN disconnect must
        # not abort the transition. Interface identity and address cleanup still fail closed.
        if self.connection:
            connection,self.connection=self.connection,None
            connection.close()
        same_device(self.adapter)
        result=subprocess.run(['iw','dev',self.adapter.name,'disconnect'],capture_output=True,text=True,timeout=8)
        if result.returncode:
            log('[Lightleak] Disconnect after supplicant stop: '+(result.stderr.strip() or str(result.returncode)))
        self.checked('ip','-4','address','flush','dev',self.adapter.name)
        state_path(os.environ).unlink(missing_ok=True)

    def dhcp(self):
        self.checked('ip','-4','address','flush','dev',self.adapter.name)
        state_path(os.environ).unlink(missing_ok=True)
        result=subprocess.run(['udhcpc','-f','-q','-n','-i',self.adapter.name,
                               '-s','/opt/webapp/dhcp.sh','-t','5','-T','3'],timeout=25)
        if result.returncode:
            raise RuntimeError('No DHCP lease; no later protocol command was sent')
        return load_target()

    def connect_wifi(self, companion=False):
        """Pin both initial selection and every reconnection to the same target BSSID."""
        self.connection=Supplicant(self.adapter,self.settings.get('original_power_save'),
                    lambda level,text,channel='wifi':log('[Wi-Fi] '+text),self.cancelled,new_session=False)
        path=self.connection.start()
        deadline=time.monotonic()+90
        point=None
        log('[Lightleak] Scanning for '+(IDLE_SSID if companion else 'the selected target AP')+'; deadline 90 seconds')
        while time.monotonic()<deadline:
            scan=self.checked('iw','dev',self.adapter.name,'scan')
            if companion:
                for block in re.split(r'(?m)^BSS ',scan)[1:]:
                    mac=re.match(r'([0-9a-fA-F:]{17})',block)
                    if mac and re.search(r'(?m)^\s*SSID: LightleakIdle\s*$',block):
                        freq=re.search(r'(?m)^\s*freq: (\d+)',block)
                        if freq:
                            point=AccessPoint(IDLE_SSID,mac[1].lower(),int(freq[1]),0)
                            break
            else:
                names=sorted(set(re.findall(r'(?m)^\s*SSID: (.+)$',scan)))
                points=[p for name in names if re.fullmatch(r'[\w +\-]+-[A-Fa-f0-9]{4}',name)
                        for p in access_points(scan,name)]
                if self.target_point:
                    points=[p for p in points if p.ssid==self.target_point.ssid and p.bssid==self.target_point.bssid]
                if points:
                    point=points[prompt('Choose your target AP:',[f'{p.ssid} · {p.bssid} · {p.signal:g} dBm' for p in points])] if len(points)>1 else points[0]
                    self.target_point=point
            if point:
                break
            log('[Lightleak] Waiting for AP pairing mode; no target writes yet in this connection stage')
            time.sleep(2)
        if point is None:
            raise RuntimeError('AP scan deadline reached; selected device was not substituted')
        log(f'[Lightleak] Connecting only to {point.ssid!r} ({point.bssid})')
        with Control(path) as control:
            number=control.request('ADD_NETWORK')
            if not number.isdigit():
                raise RuntimeError('Cannot create private Wi-Fi network')
            fields={'ssid':point.ssid.encode().hex(),'bssid':point.bssid,'scan_ssid':'1',
                    'key_mgmt':'WPA-PSK' if companion else 'NONE'}
            if companion:
                fields['psk']=psk(IDLE_PASSWORD,IDLE_SSID)
            for key,value in fields.items():
                if control.request(f'SET_NETWORK {number} {key} {value}')!='OK':
                    raise RuntimeError('Private Wi-Fi configuration rejected')
            if control.request('SELECT_NETWORK '+number)!='OK':
                raise RuntimeError('Cannot select private Wi-Fi network')
            for attempt in range(45):
                same_device(self.adapter)
                status=dict(line.split('=',1) for line in control.request('STATUS').splitlines() if '=' in line)
                if attempt%5==0:
                    log(f'[Lightleak] Association {attempt+1}/45: '+status.get('wpa_state','UNKNOWN'))
                if status.get('wpa_state')=='COMPLETED' and status.get('bssid','').lower()==point.bssid:
                    live=AccessPoint(point.ssid,point.bssid,int(status.get('freq','0')),point.signal)
                    if link_matches(self.checked('iw','dev',self.adapter.name,'link'),live):
                        return self.dhcp()
                time.sleep(1)
        raise RuntimeError('Wi-Fi association deadline reached; DHCP was not started')

    def send_packet(self, data):
        same_device(self.adapter)
        target=load_target()
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
            client.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,(self.adapter.name+'\0').encode())
            client.sendto(data,(target,6669))
        time.sleep(.1)

    def responsive(self):
        same_device(self.adapter)
        target=load_target()
        result=subprocess.run(['ping','-I',self.adapter.name,'-c','1','-W','2',target],
                              capture_output=True,timeout=4)
        if result.returncode:
            raise RuntimeError('Device stopped responding; no later setup command was sent')

    def custom_ap(self, preflight=False):
        self.checked('ip','link','set','dev',self.adapter.name,'down')
        self.checked('iw','dev',self.adapter.name,'set','type','__ap')
        control_dir=self.root/'lightleak-ap';control_dir.mkdir(exist_ok=True)
        config=self.root/'lightleak-hostapd.conf'
        ssid='LightleakPreflight' if preflight else CUSTOM_SSID
        config.write_text(f'interface={self.adapter.name}\ndriver=nl80211\nctrl_interface={control_dir}\n'
                f'ssid={ssid}\nhw_mode=g\nchannel=6\nwmm_enabled=1\nauth_algs=1\nwpa=2\n'
                f'wpa_key_mgmt=WPA-PSK\nwpa_psk={psk(self.stager,ssid)}\nrsn_pairwise=CCMP\n')
        config.chmod(0o600)
        child=self.spawn(['hostapd',str(config)])
        path=control_dir/self.adapter.name
        for _ in range(80):
            same_device(self.adapter)
            if child.poll() is not None:
                raise RuntimeError('Lightleak Linux AP could not start')
            if path.exists():
                with Control(path) as control:
                    if 'state=ENABLED' in control.request('STATUS'):
                        break
            time.sleep(.1)
        else:
            raise RuntimeError('Lightleak Linux AP startup deadline reached')
        log('[Lightleak] Actual Linux AP startup verified on the selected isolated radio')
        if preflight:
            return
        self.checked('ip','address','add',GATEWAY+'/24','dev',self.adapter.name)
        self.spawn(['dnsmasq','--keep-in-foreground','--conf-file=/dev/null','--port=0','--no-resolv',
                    '--interface='+self.adapter.name,'--bind-interfaces','--except-interface=lo',
                    '--dhcp-range=10.0.0.100,10.0.0.120,10m','--dhcp-option=3','--dhcp-option=6',
                    '--dhcp-leasefile='+str(self.root/'lightleak.leases'),'--user=root',
                    '--pid-file='+str(self.root/'lightleak-dnsmasq.pid')])
        log('[Lightleak] Waiting at most 90 seconds for a WPA-authenticated target station')
        deadline=time.monotonic()+90
        with Control(path) as control:
            while time.monotonic()<deadline:
                same_device(self.adapter)
                if any(c.poll() is not None for c in self.children):
                    raise RuntimeError('Lightleak AP service exited unexpectedly')
                station=control.request('STA-FIRST')
                if '[AUTHORIZED]' in station:
                    log('[Lightleak] Station authenticated; allowing the upstream eight-second storage window')
                    time.sleep(8)
                    return
                time.sleep(.25)
        raise RuntimeError('Target did not join the temporary AP; no payload setup was attempted')

    def configure_companion(self):
        target=self.connect_wifi(companion=True)
        if target!='10.0.0.1':
            raise RuntimeError('CustomAP DHCP endpoint differs from upstream 10.0.0.1; refusing configuration')
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as client:
            client.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,(self.adapter.name+'\0').encode())
            client.settimeout(5);client.connect((target,8080))
            client.sendall(custom_ap_packet(self.stager))
            if client.recv(1)!=b'\xde':
                raise RuntimeError('CustomAP did not acknowledge its configuration')
        log('[Lightleak] Companion configuration acknowledged; reset the companion before another attempt')
        self.close_connection()

    def receiver_socket(self):
        same_device(self.adapter)
        target=load_target()
        local=json.loads(state_path(os.environ).read_text())['address'].split('/')[0]
        client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            client.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,(self.adapter.name+'\0').encode())
            client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,262144)
            client.settimeout(.15);client.bind((local,6667))
        except BaseException:
            client.close();raise
        return client,target,local

    def verify_proper(self, client, target, local):
        request_id=secrets.randbelow(0x7FFFFFFF)+1
        self.send_packet(self.variant.proper(0x0E,words(0xFF01,180000),request_id,local))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            same_device(self.adapter)
            try:
                data,peer=client.recvfrom(2048)
            except socket.timeout:
                continue
            if peer[0]!=target:
                continue
            try:
                reply=parse_response(data,request_id)
            except ValueError:
                continue
            if len(reply)==4:
                log('[Lightleak] Payload response verified by endpoint, request ID and CRC; flash read can start')
                return
        raise RuntimeError('No verified proper-payload response; no complete backup exists')

    def run(self):
        log('[Lightleak] EXPERIMENTAL: setup writes the Wi-Fi stager and a payload sector. It can brick a device.')
        log('[Lightleak] This creates a post-exploit flash backup; it does not flash replacement firmware.')
        # Validate every datagram and payload boundary before changing a target.
        steps=list(self.variant.setup(self.proper))
        table=f'breaker_{os.getpid()}'
        subprocess.run(['nft','-f','-'],input=f'add table inet {table}\n'
             f'add chain inet {table} forward {{ type filter hook forward priority 0; policy drop; }}\n',
             text=True,check=True,timeout=8)
        log('[Lightleak] Device forwarding to the app uplink is blocked')
        for route in json.loads(command('ip','-4','-j','route','show','table','all')):
            if route.get('dev')!=self.adapter.name and route.get('dst') not in (None,'default'):
                if ipaddress.ip_network(route['dst'],strict=False).overlaps(NETWORK):
                    raise ValueError('Temporary AP subnet overlaps the app network')
        linux=self.settings['ap_mode']=='linux'
        if linux:
            try:
                self.custom_ap(preflight=True)
            finally:
                self.stop_services();self.managed()
        else:
            self.configure_companion()
        self.connect_wifi()
        if prompt(f'Target {self.target_point.ssid}; {self.variant.name}. Confirm the chip and accept flash-write risk.',
                  ['Install the selected stager (changes target flash)','Stop before target writes'])!=0:
            return 1
        self.send_packet(packet({'ssid':CUSTOM_SSID.encode(),'passwd':self.stager,'token':b'1'}))
        log('[Lightleak] Stager credentials sent; this is not proof of an accepted exploit')
        time.sleep(1)
        self.close_connection()
        if linux:
            try:
                self.custom_ap()
            finally:
                self.stop_services();self.managed()
        else:
            # The upstream companion returns to LightleakIdle eight seconds after a station joins.
            self.connect_wifi(companion=True)
            log('[Lightleak] Companion returned to idle after its target-join window')
            self.close_connection()
        if prompt('Power-cycle the target and restore AP pairing mode. Keep the same device selected.',
                  ['Target ready; reconnect to the same AP','Stop here'])!=0:
            return 1
        self.connect_wifi()
        self.send_packet(self.variant.callback());self.responsive()
        if prompt('Next: erase sector 0x132000 and install the dump payload. A ping alone cannot prove exploit compatibility.',
                  ['Accept payload-sector write risk; continue','Stop before payload-sector writes'])!=0:
            return 1
        for label,datagram in steps:
            log('[Lightleak] '+label)
            self.send_packet(datagram)
            self.responsive()
        client,target,local=self.receiver_socket()
        try:
            self.verify_proper(client,target,local)
            output=Path(self.settings['output'])
            temporary=output.with_suffix('.partial')
            metadata=output.with_suffix('.json')
            descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(descriptor,'wb') as file:
                    receiver=DumpReceiver(self.variant,target,local,client,lambda:same_device(self.adapter),self.send_packet)
                    checksum=receiver.read(file)
                    os.fsync(file.fileno())
                with temporary.open('rb') as verify:
                    verify.seek(self.variant.proper_offset)
                    if verify.read(len(self.proper))!=self.proper:
                        raise RuntimeError('Readback differs from the installed payload; backup was not certified')
                info={'id':output.stem,'chip':self.variant.chip,'variant':self.variant.slug,
                      'size':FLASH_SIZE,'sha256':checksum,'post_exploit':True,'created':int(time.time())}
                meta_fd=os.open(metadata,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(meta_fd,'w') as file:
                    json.dump(info,file);file.flush();os.fsync(file.fileno())
                # Publish the binary last: readers require both a valid record and 2 MiB.
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
                if not output.exists():
                    metadata.unlink(missing_ok=True)
        finally:
            client.close()
        log('[Lightleak] Complete 2 MiB post-exploit backup saved privately. Download it from the Lightleak tab.')
        log('[Lightleak] This dump contains secrets and the installed payload; it is not a pristine pre-exploit backup.')
        return 0


def main():
    root=Path(os.environ['UNTUYAOS3_RUN_DIR'])
    path=Path(sys.argv[1])
    if path!=root/'lightleak.json':
        raise ValueError('Invalid fixed Lightleak configuration path')
    session=LightleakSession(json.loads(path.read_text()),root)
    def interrupted(*_):
        raise InterruptedError('Lightleak session cancellation requested')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    output=RedactedOutput(sys.stdout)
    try:
        with redirect_stdout(output):
            return session.run()
    except (Exception,KeyboardInterrupt) as exc:
        log(f'Lightleak stopped: {type(exc).__name__}: {exc}')
        return 1
    finally:
        session.close();output.finish()


if __name__=='__main__':
    raise SystemExit(main())
