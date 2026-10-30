"""Lightleak wire interoperability, real UDP readout and guarded execution boundaries."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock,patch
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT/'tuya_breaker/app'))
from lightleak_protocol import Assets,packet,parse_response,words
import lightleak_session as session
from breaker_runner import BreakerRunner


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assets=Assets(ROOT/'tuya_breaker/lightleak')

    def test_pinned_fork_artifact_and_generic_variants_match_central_revision(self):
        spec=json.loads((ROOT/'project.json').read_text())
        manifest=json.loads((ROOT/'tuya_breaker/lightleak/manifest.json').read_text())
        self.assertEqual(manifest['revision'],spec['lightleak_revision'])
        self.assertEqual(len(self.assets.variants),13)
        for v in self.assets.variants.values():
            steps=list(v.setup(self.assets.binary(v,'proper')))
            self.assertEqual(v.proper_offset,0x132000)
            self.assertTrue(all(len(data)==256 for label,data in steps))
            self.assertEqual(v.read(0,8,99,'192.168.176.100')[0:4],b'\0\0\x55\xaa')

    def test_binary_json_header_crc_and_escaping_follow_android_wire_format(self):
        wire=packet({'ssid':b'LightleakCustom','passwd':b'a"b\\c\xff','token':b'1'})
        head,number,kind,length=struct.unpack_from('>IIII',wire)
        self.assertEqual((head,number,kind),(0x55AA,0,1))
        end=16+length-8
        self.assertEqual(wire[16:end],b'{"ssid":"LightleakCustom","passwd":"a\\"b\\\\c\xff","token":"1"}')
        self.assertEqual(struct.unpack_from('>II',wire,end),(zlib.crc32(wire[:end]),0xAA55))
        with self.assertRaises(ValueError):packet({'ssid':b'bad\0field'})
        with self.assertRaises(ValueError):packet(command=b'X'*240,options=b'1234')

    def test_callback_token_overflow_and_stager_options(self):
        for v in self.assets.variants.values():
            wire=v.callback()
            self.assertIn(b'A'*72+words(v.address['stager'])[:3],wire)
            self.assertEqual(wire[-4:],words(0xFF))
            if v.chip=='BK7231T':
                self.assertEqual(struct.unpack_from('<III',wire,240),(3,0xB000,v.address['store']))
                self.assertEqual(wire[0x88:0x8C],words(2))
            else:
                self.assertEqual(struct.unpack_from('<IIII',wire,236),
                    (0,3,int(v.gadgets['finish']['branch_offset'],0)-4,v.address['handle']))
                # Proper branch -2 must be encoded as a signed two's-complement word.
                self.assertEqual(v.read(0,1,1,'192.168.176.100')[244:248],words(0xFFFFFFFE))

    def test_setup_writes_only_the_reviewed_payload_sector_in_128_byte_chunks(self):
        for v in self.assets.variants.values():
            binary=self.assets.binary(v,'proper')
            chunks=[]
            for label,data in v.setup(binary):
                if label.startswith('Write payload'):
                    if v.chip=='BK7231T':
                        cmd,offset,length=struct.unpack_from('<III',data,0x48)
                        self.assertEqual(cmd,1);payload=data[0x54:0x54+length]
                    else:
                        length,offset=struct.unpack_from('<II',data,0x48)
                        payload=data[0x50:0x50+length]
                    self.assertLessEqual(length,128)
                    self.assertEqual(offset,0x132000+sum(map(len,chunks)))
                    self.assertLessEqual(offset+length,0x133000)
                    chunks.append(payload)
            self.assertEqual(b''.join(chunks),binary)
            with self.assertRaises(ValueError):list(v.setup(b'x'*4097))
            with self.assertRaises(ValueError):v.read(0x200000,1,1,'192.168.176.100')

    def test_binary_custom_ap_key_and_configuration_layout(self):
        self.assertEqual(str(session.NETWORK),'10.0.0.0/24')
        self.assertEqual(session.GATEWAY,'10.0.0.1')
        stager=self.assets.binary(self.assets.variant('lightleak-bk7231t'),'stager')
        data=session.custom_ap_packet(stager)
        self.assertEqual(len(data),109)
        self.assertEqual(data[:5],b'cctr\x68')
        self.assertEqual(data[38:100],stager)
        self.assertEqual(struct.unpack_from('<I',data,101)[0],8000)
        self.assertEqual(struct.unpack_from('<I',data,105)[0],zlib.crc32(data[5:105]))
        # Published WPA PBKDF2 test vector; no UTF-8 conversion of binary stager passwords.
        self.assertEqual(session.psk(b'password','IEEE'),'f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e')

    def test_checksum_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'manifest.json').write_text(json.dumps({'files':{'test.bin':'0'*64}}))
            (path/'test.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):Assets(path)


class UdpReadoutTests(unittest.TestCase):
    def test_real_udp_out_of_order_blocks_crc_stale_and_duplicate_rejection(self):
        variant=Assets().variant('lightleak-bk7231n-type1-addr1-xor')
        data=bytes(range(256))*(0x200000//256)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as target:
            receiver.bind(('127.0.0.1',0));receiver.settimeout(.05)
            target.bind(('127.0.0.1',0));target.settimeout(2)
            failures=[]
            def responder():
                try:
                    for batch in range(256):
                        request,peer=target.recvfrom(2048)
                        request_id=struct.unpack_from('<I',request,0x50)[0]
                        offset,length,maximum=struct.unpack_from('<III',request,0x5C)
                        self.assertEqual(maximum,1024)
                        if batch==0:
                            target.sendto(words(request_id,0)+b'bad crc',peer)
                            target.sendto(words(request_id-1,0)+b'stale',peer)
                            invalid=words(0x200000,1024)+b'x'*1024
                            target.sendto(words(request_id,zlib.crc32(invalid))+invalid,peer)
                        for start in reversed(range(offset,offset+length,1024)):
                            payload=words(start,1024)+data[start:start+1024]
                            response=words(request_id,zlib.crc32(payload))+payload
                            target.sendto(response,peer)
                            if batch==0:target.sendto(response,peer)
                except BaseException as exc:failures.append(exc)
            worker=threading.Thread(target=responder);worker.start()
            output=io.BytesIO()
            send=lambda packet:receiver.sendto(packet,target.getsockname())
            reader=session.DumpReceiver(variant,'127.0.0.1','127.0.0.1',receiver,Mock(),send)
            checksum=reader.read(output,progress=lambda _:None)
            worker.join(3)
            self.assertFalse(worker.is_alive());self.assertEqual(failures,[])
            self.assertEqual(output.getvalue(),data)
            self.assertEqual(checksum,hashlib.sha256(data).hexdigest())

    def test_response_id_crc_and_size_are_checked(self):
        payload=b'test'
        good=words(14,zlib.crc32(payload))+payload
        self.assertEqual(parse_response(good,14),payload)
        for data,identifier in [(good,15),(good[:-1]+b'!',14),(b'1',14),(b'0'*1041,14)]:
            with self.assertRaises(ValueError):parse_response(data,identifier)


class SessionBoundaryTests(unittest.TestCase):
    def fake(self, directory):
        value=session.LightleakSession.__new__(session.LightleakSession)
        value.variant=Assets().variant('lightleak-bk7231t')
        value.proper=Assets().binary(value.variant,'proper')
        value.stager=Assets().binary(value.variant,'stager')
        value.settings={'ap_mode':'linux','output':str(Path(directory)/('a'*32+'.bin'))}
        value.adapter=types.SimpleNamespace(name='wlan1')
        value.custom_ap=Mock();value.stop_services=Mock();value.managed=Mock()
        value.connect_wifi=Mock();value.close_connection=Mock();value.responsive=Mock()
        value.send_packet=Mock();value.verify_proper=Mock()
        value.receiver_socket=Mock(return_value=(Mock(),'192.168.176.1','192.168.176.100'))
        value.target_point=types.SimpleNamespace(ssid='SmartLife-1234')
        return value

    def run_stubbed(self,value,answers):
        with patch.object(session,'prompt',side_effect=answers),patch.object(session,'command',return_value='[]'), \
             patch.object(session.subprocess,'run'),patch.object(session.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):
            return value.run()

    def test_declining_first_prompt_sends_no_target_write(self):
        with tempfile.TemporaryDirectory() as directory:
            value=self.fake(directory)
            self.assertEqual(self.run_stubbed(value,[1]),1)
            value.send_packet.assert_not_called()
            value.custom_ap.assert_called_once_with(preflight=True)

    def test_declining_payload_stage_never_erases_the_sector(self):
        with tempfile.TemporaryDirectory() as directory:
            value=self.fake(directory)
            self.assertEqual(self.run_stubbed(value,[0,0,1]),1)
            self.assertEqual(value.send_packet.call_count,2)  # Wi-Fi credentials and callback only.
            value.verify_proper.assert_not_called()

    def test_incomplete_dump_is_discarded_and_never_advertised_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            value=self.fake(directory)
            with patch.object(session.DumpReceiver,'read',side_effect=RuntimeError('missing blocks')):
                with self.assertRaisesRegex(RuntimeError,'missing blocks'):
                    self.run_stubbed(value,[0,0,0])
            self.assertEqual(list(Path(directory).iterdir()),[])
            value.receiver_socket.return_value[0].close.assert_called_once()

    def test_complete_backup_requires_exact_installed_payload_readback(self):
        for matches in (False,True):
            with self.subTest(matches=matches),tempfile.TemporaryDirectory() as directory:
                value=self.fake(directory)
                data=bytearray(0x200000)
                if matches:
                    data[value.variant.proper_offset:value.variant.proper_offset+len(value.proper)]=value.proper
                def received(file):
                    file.write(data)
                    return hashlib.sha256(data).hexdigest()
                with patch.object(session.DumpReceiver,'read',side_effect=received):
                    if matches:
                        self.assertEqual(self.run_stubbed(value,[0,0,0]),0)
                        output=Path(value.settings['output'])
                        self.assertEqual(output.read_bytes(),data)
                        metadata=json.loads(output.with_suffix('.json').read_text())
                        self.assertTrue(metadata['post_exploit'])
                        self.assertEqual(metadata['sha256'],hashlib.sha256(data).hexdigest())
                    else:
                        with self.assertRaisesRegex(RuntimeError,'Readback differs'):
                            self.run_stubbed(value,[0,0,0])
                        self.assertEqual(list(Path(directory).iterdir()),[])

    def test_ap_failure_happens_before_device_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            value=self.fake(directory);value.custom_ap.side_effect=RuntimeError('AP unavailable')
            with self.assertRaisesRegex(RuntimeError,'AP unavailable'):
                self.run_stubbed(value,[])
            value.connect_wifi.assert_not_called();value.send_packet.assert_not_called()
            value.stop_services.assert_called_once();value.managed.assert_called_once()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.runner=BreakerRunner({},Mock(),threading.Event(),data=self.root)
        self.runner.state='ready'

    def test_review_required_and_command_path_is_fixed(self):
        self.runner.choose_tool('lightleak')
        with self.assertRaises(ValueError):self.runner.ensure_ready()
        for request in [{'variant':'../../x','ap_mode':'linux','understand_writes':True},
                        {'variant':'lightleak-bk7231t','ap_mode':'linux','understand_writes':False}]:
            with self.assertRaises(ValueError):self.runner.configure_lightleak(request)
        self.runner.configure_lightleak({'variant':'lightleak-bk7231t','ap_mode':'linux','understand_writes':True})
        self.runner.ensure_ready()
        self.assertTrue(self.runner.status()['engine_ready'])
        folder=self.root/'session';folder.mkdir()
        args=self.runner.session_command(folder)
        self.assertEqual(args[:2],['/opt/venv/bin/python','/opt/webapp/lightleak_session.py'])
        self.assertEqual((folder/'lightleak.json').stat().st_mode&0o777,0o600)
        settings=json.loads((folder/'lightleak.json').read_text())
        self.assertEqual(Path(settings['output']).parent,self.runner.backups)

    def test_only_complete_pairs_are_downloadable_and_deletion_is_idle_only(self):
        identifier='a'*32
        file=self.runner.backups/(identifier+'.bin');file.write_bytes(b'123')
        metadata={'id':identifier,'size':0x200000,'chip':'BK7231N'}
        file.with_suffix('.json').write_text(json.dumps(metadata))
        self.assertEqual(self.runner.backup_files(),[])
        file.write_bytes(b'1'*0x200000)
        self.assertEqual(self.runner.backup_files(),[metadata])
        with self.assertRaises(ValueError):self.runner.backup_file('../secret')
        self.runner.state='releasing'
        with self.assertRaises(ValueError):self.runner.delete_backup(identifier)
        self.runner.state='finished';self.runner.delete_backup(identifier)
        self.assertEqual(self.runner.backup_files(),[])

    def test_startup_discards_partials_without_deleting_complete_backups(self):
        partial=self.runner.backups/'previous.partial';partial.write_bytes(b'incomplete')
        binary=self.runner.backups/'existing.bin';binary.write_bytes(b'complete')
        BreakerRunner({},Mock(),threading.Event(),data=self.root)
        self.assertFalse(partial.exists());self.assertTrue(binary.exists())


if __name__=='__main__':unittest.main()
