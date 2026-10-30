"""Tool separation, profile boundaries and pre-write cancellation without a radio."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
from http.client import HTTPConnection

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT/'tuya_breaker/app'))
from breaker_catalog import Catalogue, slug, validate_profile
from breaker_runner import BreakerRunner
import cloudcutter_session as session
from breaker import BreakerHandler
import server
from journal import Journal

PROFILE = {'slug':'test-profile', 'name':'1.0.0 - BK7231N', 'type':'CLASSIC',
           'firmware':{'chip':'BK7231N'}, 'data':{'address_finish':'0x12345'}}
DEVICE = {'name':'Test lamp', 'profiles':[{'slug':'test-profile'}], 'schemas':{'test':[]}}


class CatalogueTests(unittest.TestCase):
    def test_no_path_or_url_can_replace_the_profile_api(self):
        for value in ('../secret', 'https://evil.test', 'a/b', '', None, 'a\n'):
            with self.assertRaises(ValueError):
                slug(value)

    def test_only_matching_classic_profiles_are_accepted(self):
        validate_profile(DEVICE, PROFILE)
        for profile in ({**PROFILE, 'slug':'other'}, {**PROFILE, 'type':'LIGHTLEAK'},
                        {**PROFILE, 'firmware':{'chip':'ESP32'}}):
            with self.assertRaises(ValueError):
                validate_profile(DEVICE, profile)


class BreakerRunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runner = BreakerRunner({}, Mock(), threading.Event(), data=self.root)
        self.runner.state = 'ready'

    def test_tool_change_refused_until_cleanup_finishes(self):
        for state in ('running', 'assigning', 'cleaning', 'releasing'):
            self.runner.state = state
            with self.assertRaises(ValueError):
                self.runner.choose_tool('cloudcutter')
        self.runner.state = 'finished'
        self.runner.choose_tool('cloudcutter')
        self.assertFalse(self.runner.status()['engine_ready'])
        with self.assertRaises(ValueError):
            self.runner.ensure_ready()

    def test_failed_reconfiguration_removes_old_approval(self):
        self.runner.settings = {'method':'flash'}
        with self.assertRaises(ValueError):
            self.runner.configure({'method':'unknown'}, self.root)
        self.assertIsNone(self.runner.settings)

    def test_wifi_credentials_never_appear_in_status_or_journal(self):
        combined = {'device':DEVICE, 'profile':PROFILE}
        with patch.object(self.runner.catalogue, 'combined', return_value=(self.root/'profile.json', combined)):
            self.runner.configure({'device':'test', 'profile':'test-profile', 'method':'detach',
                                   'ssid':'private-network', 'password':'private-password'}, self.root)
        self.assertNotIn('private-password', json.dumps(self.runner.status()))
        self.assertNotIn('private-network', str(self.runner.journal.emit.call_args_list))
        self.assertNotIn('private-password', str(self.runner.journal.emit.call_args_list))
        self.runner.choose_tool('cloudcutter')
        self.assertTrue(self.runner.status()['engine_ready'])

    def test_cloudcutter_command_is_fixed_and_configuration_is_private(self):
        profile = self.root/'profile.json'
        profile.write_text('{}')
        self.runner.tool = 'cloudcutter'
        self.runner.settings = {'profile':str(profile), 'method':'detach', 'ssid':'test', 'password':'secret'}
        folder = self.root/'runtime'; folder.mkdir()
        args = self.runner.session_command(folder)
        self.assertEqual(args[:2], ['/opt/cloudcutter-venv/bin/python','/opt/webapp/cloudcutter_session.py'])
        self.assertNotIn('secret', repr(args))
        self.assertEqual((folder/'cloudcutter.json').stat().st_mode & 0o777, 0o600)

    def test_ap_cleanup_restores_only_the_leased_radio(self):
        self.runner.tool = 'cloudcutter'
        self.runner.adapter = types.SimpleNamespace(name='wlan1')
        with patch('breaker_runner.same_device'), patch('breaker_runner.command') as command:
            self.runner.before_cleanup()
        self.assertEqual(command.call_args_list[0].args, ('ip','link','set','dev','wlan1','down'))
        self.assertEqual(command.call_args_list[1].args, ('iw','dev','wlan1','set','type','managed'))


class ControllerTests(unittest.TestCase):
    def test_secret_redaction_across_output_chunks(self):
        target = io.StringIO()
        output = session.RedactedOutput(target)
        output.write('Progress 50%\nLocal ')
        output.write('Key: private-secret\nDone\n')
        self.assertNotIn('private-secret', target.getvalue())
        self.assertIn('Progress 50%', target.getvalue())

    def fake_session(self):
        value = session.Session.__new__(session.Session)
        value.settings = {'method':'detach'}
        value.adapter = types.SimpleNamespace(name='wlan1')
        value.ap, value.stop_services, value.managed, value.connect = Mock(), Mock(), Mock(), Mock(return_value='192.168.175.1')
        value.exploit_and_flash = Mock(return_value=3)
        return value

    def run_stubbed(self, value, answer):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'profile.json'; path.write_text('{}')
            value.settings['profile'] = str(path)
            fake_cloudcutter = types.ModuleType('cloudcutter')
            fake_cloudcutter.exploit = Mock()
            with patch.dict(sys.modules, {'cloudcutter':fake_cloudcutter}), \
                 patch.object(session, 'command', return_value='[]'), patch.object(session, 'prompt', return_value=answer), \
                 patch.object(session.subprocess, 'run'):
                return value.run()

    def test_cancel_at_final_prompt_never_sends_exploit(self):
        value = self.fake_session()
        self.assertEqual(self.run_stubbed(value, 1), 1)
        value.exploit_and_flash.assert_not_called()
        value.ap.assert_called_once_with(services=False)

    def test_ap_failure_prevents_even_the_first_device_connection(self):
        value = self.fake_session()
        value.ap.side_effect = RuntimeError('AP unavailable')
        with self.assertRaisesRegex(RuntimeError, 'AP unavailable'):
            self.run_stubbed(value, 0)
        value.connect.assert_not_called()
        value.exploit_and_flash.assert_not_called()
        value.stop_services.assert_called_once()
        value.managed.assert_called_once()


class BreakerHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.journal = Journal(self.root/'logs')
        self.runner = BreakerRunner({}, self.journal, threading.Event(), data=self.root)
        self.runner.state = 'ready'
        self.devices = Mock(operation=threading.Lock(), lease=None)
        self.devices.status.return_value = {}
        with patch.object(server, 'Handler', BreakerHandler):
            self.http = server.Server(('127.0.0.1',0), self.runner, self.journal, self.root, self.devices)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(2)
        self.journal.close(); self.directory.cleanup()

    def request(self, method, path, value=None, token=True):
        connection = HTTPConnection(*self.http.server_address, timeout=3)
        try:
            headers = {'Content-Type':'application/json'}
            if token:
                headers['X-CSRF-Token'] = self.http.csrf
            connection.request(method, path, json.dumps(value) if value is not None else None, headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_private_endpoints_require_real_ingress_peer(self):
        code, body = self.request('GET', '/api/cloudcutter/credentials')
        self.assertEqual(code, 403)
        self.assertNotIn(b'PK\x03\x04', body)

    def test_tool_mutation_requires_csrf_and_idle_runner(self):
        with patch.object(BreakerHandler, 'trusted', return_value=True):
            self.assertEqual(self.request('POST','/api/tool',{'tool':'cloudcutter'},token=False)[0],403)
            self.assertEqual(self.runner.tool,'untuyaos3')
            self.assertEqual(self.request('POST','/api/tool',{'tool':'cloudcutter'})[0],200)
            self.runner.state = 'releasing'
            self.assertEqual(self.request('POST','/api/tool',{'tool':'untuyaos3'})[0],400)
            self.assertEqual(self.runner.tool,'cloudcutter')

    def test_configuration_secret_does_not_leave_status_or_journal(self):
        combined = {'device':DEVICE, 'profile':PROFILE}
        with patch.object(BreakerHandler, 'trusted', return_value=True), \
             patch.object(self.runner.catalogue, 'combined', return_value=(self.root/'profile.json', combined)):
            code, _ = self.request('POST','/api/cloudcutter/configure',{'method':'detach',
                'device':'test-device','profile':'test-profile','ssid':'private-network','password':'private-password'})
            self.assertEqual(code,200)
            code, body = self.request('GET','/api/events')
            self.assertEqual(code,200)
            self.assertNotIn(b'private-password',body)
            self.assertNotIn(b'private-network',body)

    def test_lightleak_downloads_require_ingress_and_changes_require_csrf(self):
        self.assertEqual(self.request('GET','/api/lightleak')[0],403)
        self.assertEqual(self.request('GET','/api/lightleak/backups/'+'a'*32)[0],403)
        with patch.object(BreakerHandler,'trusted',return_value=True):
            code,body=self.request('GET','/api/lightleak')
            self.assertEqual(code,200)
            self.assertEqual(len(json.loads(body)['variants']),13)
            self.assertEqual(json.loads(body)['backups'],[])
            value={'variant':'lightleak-bk7231t','ap_mode':'linux','understand_writes':True}
            self.assertEqual(self.request('POST','/api/lightleak/configure',value,token=False)[0],403)
            self.assertIsNone(self.runner.lightleak_settings)
            self.assertEqual(self.request('POST','/api/lightleak/configure',value)[0],200)
            self.runner.state='releasing'
            self.assertEqual(self.request('POST','/api/lightleak/backups/delete',{'id':'a'*32})[0],400)


if __name__ == '__main__':
    unittest.main()
