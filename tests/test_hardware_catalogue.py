import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT/'tuya_breaker/app'))
from hardware_catalogue import HardwareCatalogue, SOURCE, guide_url, normalize


class HardwareCatalogueTests(unittest.TestCase):
    def test_hardware_record_never_implies_exploit_support(self):
        record = normalize({'name':'Test lamp','chip':'BK7231M','bDetailed':'1','pins':{'6':'PWM;1'}})
        self.assertFalse(record['cloudcutter_verified'])
        self.assertEqual(record['chip'],'BK7231M')  # Do not silently map to a profile chip.
        self.assertTrue(record['has_template'])

    def test_external_links_are_restricted_to_source_community_hosts(self):
        for value in ('javascript:alert(1)','https://elektroda.com.evil.test/x','https://127.0.0.1/x',
                      'https://user:password@www.elektroda.com/x','https://www.elektroda.com:444/x'):
            self.assertEqual(guide_url(value),'')
        self.assertEqual(guide_url('http://www.elektroda.com/rtvforum/topic1.html'),
                         'https://www.elektroda.com/rtvforum/topic1.html')

    def test_bounded_reference_data_does_not_execute_commands(self):
        record = normalize({'name':'<script>example</script>','pins':{'1':'Rel;1'},'command':'startDriver Test',
                            'keywords':['relay']*100, 'wiki':'javascript:alert(1)'})
        self.assertEqual(record['name'],'<script>example</script>')  # UI must render as text.
        self.assertEqual(record['guide_url'],'')
        self.assertEqual(len(record['keywords']),40)
        self.assertEqual(record['template']['command'],'startDriver Test')

    def test_refresh_is_atomic_and_failed_update_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            catalogue = HardwareCatalogue(directory)
            response = io.BytesIO(json.dumps({'version':.1,'devices':[{'name':'Lamp','pins':{'6':'PWM;1'}}]}).encode())
            response.url = SOURCE
            with patch('hardware_catalogue.urlopen',return_value=response):
                snapshot = catalogue.snapshot(refresh=True)
            record = snapshot['devices'][0]
            self.assertNotIn('template',record)
            self.assertEqual(catalogue.detail(record['id'])['template']['pins'],{'6':'PWM;1'})
            old = catalogue.path.read_bytes()
            with patch('hardware_catalogue.urlopen',side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    catalogue.snapshot(refresh=True)
            self.assertEqual(catalogue.path.read_bytes(),old)
            self.assertEqual(catalogue.snapshot()['updated_at'],snapshot['updated_at'])
            with self.assertRaises(ValueError):
                catalogue.detail('../../etc/passwd')


if __name__=='__main__':
    unittest.main()
