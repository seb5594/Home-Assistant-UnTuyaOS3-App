import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_generated_build_contexts_match_central_source(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sync_project", ROOT / "tools/sync_project.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        for name, expected in generator.outputs().items():
            self.assertEqual((ROOT / name).read_text(encoding="utf-8"), expected, name)

    def test_shared_security_code_stays_in_sync(self):
        for name in ("wifi.py", "protocol.py", "journal.py"):
            self.assertEqual((ROOT / "untuyaos3/app" / name).read_bytes(),
                             (ROOT / "untuyaos3_wifi/app" / name).read_bytes())

    def test_no_surprise_host_permissions(self):
        import yaml
        core = yaml.safe_load((ROOT / "untuyaos3/config.yaml").read_text())
        helper = yaml.safe_load((ROOT / "untuyaos3_wifi/config.yaml").read_text())
        for key in ("host_network", "host_dbus", "host_pid", "docker_api", "full_access", "usb",
                    "hassio_api", "homeassistant_api"):
            self.assertFalse(core.get(key, False), key)
        for key in ("host_pid", "docker_api", "full_access", "usb", "hassio_api", "homeassistant_api"):
            self.assertFalse(helper.get(key, False), key)
        self.assertEqual(core["privileged"], ["NET_ADMIN", "NET_RAW"])
        self.assertEqual(helper["privileged"], ["NET_ADMIN"])
        self.assertNotIn("ports", core)
        for app in ("untuyaos3", "untuyaos3_wifi"):
            profile = (ROOT / app / "apparmor.txt").read_text()
            self.assertIn("/share/untuyaos3-private/{,**} rwk,", profile)
            self.assertNotIn("/share/** rw", profile)

    def test_translations_are_valid_and_cover_options(self):
        import yaml
        for app in ("untuyaos3", "untuyaos3_wifi"):
            options = yaml.safe_load((ROOT / app / "config.yaml").read_text())["options"]
            for language in ("en", "de"):
                translation = json.loads((ROOT / app / "translations" / (language+".json")).read_text(encoding="utf-8"))
                self.assertEqual(set(translation["configuration"]), set(options))


if __name__ == "__main__":
    unittest.main()
