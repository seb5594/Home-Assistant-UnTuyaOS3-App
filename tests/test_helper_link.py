"""How the main app notices, describes and links to the Wi-Fi helper."""
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "untuyaos3/app"))
sys.path.insert(1, str(ROOT / "untuyaos3_wifi/app"))
import devices
import lease
import links
from protocol import APP_VERSION, BUILD_INFO, PairingFailed, ProtocolMismatch, SecretNotSet, validate_options


class HelperStateTests(unittest.TestCase):
    def test_every_failure_has_its_own_state(self):
        for error, state in ((SecretNotSet("x"), "not_configured"), (lease.HelperUnavailable("x"), "unreachable"),
                             (PairingFailed("x"), "pairing"), (ProtocolMismatch("x"), "protocol"),
                             (RuntimeError("x"), "error")):
            self.assertEqual(lease.helper_state(error), state)

    def test_missing_or_short_secret_is_reported_as_not_configured(self):
        for options in ({}, {"pairing_token": "short"}):
            with self.assertRaises(SecretNotSet):
                validate_options(options)
        with self.assertRaises(lease.HelperUnavailable):
            with patch.object(lease.socket.socket, "connect", side_effect=FileNotFoundError):
                lease.connect({"pairing_token": "x" * 40}, "wlan0")


class DevicesHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner, self.journal, self.fatal = Mock(), Mock(), threading.Event()
        self.runner.options = {}
        self.devices = devices.Devices({}, self.runner, self.journal, self.fatal, Path(self.temp.name))
        self.socket_path = Path(self.temp.name) / "wifi.sock"

    def inventory(self, **extra):
        return patch.object(devices, "inventory", return_value={"adapters": [], "usb_devices": [], **extra})

    def test_state_before_the_first_contact_is_unknown(self):
        self.assertEqual(self.devices.status()["helper"]["state"], "unknown")

    def test_matching_helper_is_ready_and_reports_the_version_it_expects(self):
        with self.inventory(helper={"version": APP_VERSION}):
            self.devices.refresh()
        helper = self.devices.status()["helper"]
        self.assertEqual((helper["state"], helper["version"], helper["expected_version"]), ("ready", APP_VERSION, APP_VERSION))

    def test_different_helper_release_is_only_a_warning(self):
        with self.inventory(helper={"version": "0.0.1"}):
            self.devices.refresh()
        helper = self.devices.status()["helper"]
        self.assertEqual(helper["state"], "outdated")
        self.assertIn("0.0.1", helper["message"])

    def test_old_helper_without_version_info_still_works(self):
        with self.inventory():
            self.devices.refresh()
        self.assertEqual(self.devices.status()["helper"]["state"], "ready")

    def test_failures_become_readable_states(self):
        for error, state in ((lease.HelperUnavailable("gone"), "unreachable"), (PairingFailed("secret"), "pairing")):
            with patch.object(devices, "inventory", side_effect=error):
                with self.assertRaises(type(error)):
                    self.devices.refresh()
            self.assertEqual(self.devices.status()["helper"]["state"], state)
            self.assertTrue(self.devices.status()["helper"]["message"])

    def test_new_helper_socket_is_picked_up_exactly_once(self):
        self.socket_path.touch()
        with patch.object(devices, "inventory", side_effect=lease.HelperUnavailable("stale")) as inventory:
            self.devices.poll_helper(self.socket_path)
            self.devices.poll_helper(self.socket_path)  # Same stale socket: no second attempt.
            self.assertEqual(inventory.call_count, 1)
            self.socket_path.unlink()
            self.socket_path.touch()
            os.utime(self.socket_path, ns=(1, 1))  # A restarted helper creates a different socket.
            self.devices.poll_helper(self.socket_path)
            self.assertEqual(inventory.call_count, 2)

    def test_started_helper_is_connected_without_pressing_refresh(self):
        self.socket_path.touch()
        with self.inventory(helper={"version": APP_VERSION}):
            self.devices.poll_helper(self.socket_path)
        self.assertEqual(self.devices.status()["helper"]["state"], "ready")

    def test_stopped_helper_is_noticed_and_adapters_are_dropped(self):
        self.socket_path.touch()
        with self.inventory(helper={"version": APP_VERSION}):
            self.devices.poll_helper(self.socket_path)
        self.socket_path.unlink()
        self.devices.poll_helper(self.socket_path)
        status = self.devices.status()
        self.assertEqual((status["helper"]["state"], status["adapters"], status["selected_adapter"]), ("unreachable", [], None))

    def test_watcher_never_interferes_with_a_lease_or_running_session(self):
        self.socket_path.touch()
        with patch.object(devices, "inventory") as inventory:
            self.devices.lease = Mock()
            self.devices.poll_helper(self.socket_path)
            self.devices.lease = None
            self.runner.state = "running"
            self.devices.poll_helper(self.socket_path)
            inventory.assert_not_called()


class LinkTests(unittest.TestCase):
    def test_helper_link_follows_the_repository_hash_of_the_running_app(self):
        self.assertEqual(links.helper_url("a1b2c3d4-untuyaos3"),
                         "https://my.home-assistant.io/redirect/supervisor_addon/?addon=a1b2c3d4_untuyaos3_wifi")
        self.assertIn("addon=local_untuyaos3_wifi", links.helper_url("local-untuyaos3"))

    def test_unknown_hostname_falls_back_to_the_app_store(self):
        for hostname in ("a1b2c3d4-untuyaos3-wifi", "something", "A1B2C3D4-untuyaos3"):
            self.assertTrue(links.helper_url(hostname).endswith("/supervisor_addons/"), hostname)

    def test_page_shows_version_credit_and_report_form(self):
        page = links.render_page((ROOT / "untuyaos3/app/static/index.html").read_text(encoding="utf-8"), "csrf-token", "abcdef01-untuyaos3")
        self.assertIsNone(re.search(r"__[A-Z_]+__", page), "unreplaced placeholder")
        self.assertIn(f">{APP_VERSION}<", page)
        self.assertIn("https://github.com/tuya-cloudcutter/UnTuyaOS3", page)
        self.assertIn(BUILD_INFO["upstream_revision"], page)
        self.assertIn("template=device-report.yml", page)
        self.assertIn("abcdef01_untuyaos3_wifi", page)
        self.assertIn('content="csrf-token"', page)

    def test_report_form_exists_in_the_repository(self):
        form = ROOT / ".github/ISSUE_TEMPLATE/device-report.yml"
        self.assertTrue(form.is_file())
        text = form.read_text(encoding="utf-8")
        for field in ("app_version", "wifi_adapter", "host_kernel", "upstream_revision"):
            self.assertIn(f"id: {field}", text, "the Web UI prefills this field")


if __name__ == "__main__":
    unittest.main()
