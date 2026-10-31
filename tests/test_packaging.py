"""One self-contained app, reproducible generated files and minimum host permissions."""
import hashlib, importlib.util, json
from pathlib import Path
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'project.json').read_text())
SLUG=next(iter(SPEC['apps']))

class PackagingTests(unittest.TestCase):
    def test_one_app_only_and_generated_sources_match(self):
        self.assertEqual([p.parent.name for p in ROOT.glob('*/config.yaml')],[SLUG])
        spec=importlib.util.spec_from_file_location('standalone_sync',ROOT/'tools/sync_project.py')
        generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
        for name,expected in generator.outputs().items():
            self.assertEqual((ROOT/name).read_text(),expected,name)
        self.assertEqual(json.loads((ROOT/'.github/apps.json').read_text())['apps'],[SLUG])

    def test_permissions_and_generic_ipc_path(self):
        config=yaml.safe_load((ROOT/SLUG/'config.yaml').read_text())
        helper=SLUG=='wifi_helper'
        self.assertEqual(config['privileged'],['NET_ADMIN'] if helper else ['NET_ADMIN','NET_RAW'])
        for key in ('host_pid','docker_api','full_access','usb','hassio_api','homeassistant_api','ports'):
            self.assertFalse(config.get(key,False),key)
        self.assertEqual(bool(config.get('host_network')),helper)
        self.assertEqual(bool(config.get('host_dbus')),helper)
        profile=(ROOT/SLUG/'apparmor.txt').read_text()
        self.assertIn('/share/wifi-helper-private/{,**} rwk,',profile)
        self.assertNotIn('/share/** rw',profile)
        self.assertNotIn('capability sys_admin',profile)
        for lang in ('en','de'):
            fields=json.loads((ROOT/SLUG/'translations'/(lang+'.json')).read_text())['configuration']
            self.assertEqual(set(fields),set(config['options']))

    def test_pinned_vendor_sources_have_not_drifted(self):
        for manifest in (ROOT/'vendor').glob('*/UPSTREAM.json'):
            data=json.loads(manifest.read_text())
            self.assertRegex(data['revision'],r'^[0-9a-f]{40}$')
            for name,expected in data['files'].items():
                self.assertEqual(hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest(),expected,name)
