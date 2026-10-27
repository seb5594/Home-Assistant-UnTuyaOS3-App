"""Selection, retention and private Wi-Fi controller regressions without host hardware."""
import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "untuyaos3/app"))
sys.path.insert(1, str(ROOT / "untuyaos3_wifi/app"))
import devices
import inventory
import supplicant
from journal import Journal
from wifi import Adapter
from wifi import radio_unblocked, PreflightError


class RfkillTests(unittest.TestCase):
    def test_stale_unrelated_entry_does_not_hide_valid_radio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfkill3").mkdir()  # name missing after another PHY moved namespaces
            selected = root / "rfkill4"
            selected.mkdir()
            for key, value in {"name": "phy0", "soft": "0", "hard": "0"}.items():
                (selected / key).write_text(value)
            radio_unblocked("phy0", root)
            for key in ("soft", "hard"):
                for value in ("1", "", "unknown"):
                    (selected / key).write_text(value)
                    with self.assertRaises(PreflightError):
                        radio_unblocked("phy0", root)
                (selected / key).write_text("0")
            (selected / "hard").unlink()
            with self.assertRaisesRegex(PreflightError, "became unavailable"):
                radio_unblocked("phy0", root)

    def test_missing_selected_radio_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfkill3").mkdir()
            with self.assertRaisesRegex(PreflightError, "cannot verify"):
                radio_unblocked("phy0", root)


class LogTests(unittest.TestCase):
    def test_restart_and_clear_delete_only_owned_logs_and_reset_replay(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            for name in ("app.log", "app.log.1", "app.log.5", "keep.txt"):
                (root / name).write_text("old")
            journal = Journal(root)
            try:
                self.assertEqual([p.name for p in root.iterdir()], ["keep.txt"])
                journal.emit("info", "old terminal", "terminal")
                old = journal.snapshot(0)
                (root / "app.log.2").write_text("old")
                generation = journal.clear()
                journal.emit("info", "new terminal", "terminal")
                self.assertNotEqual(generation, old["generation"])
                fresh = journal.snapshot(99999, old["generation"])
                self.assertEqual(fresh["cursor"], 3)
                self.assertNotIn("old terminal", json.dumps(fresh))
                self.assertIn("new terminal", json.dumps(fresh))
                self.assertFalse((root / "app.log.2").exists())
                self.assertNotIn("old terminal", (root / "app.log").read_text())
                self.assertEqual((root / "keep.txt").read_text(), "old")
            finally:
                journal.close()


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner, self.log, self.fatal = Mock(), Mock(), threading.Event()
        self.runner.options = {}
        self.devices = devices.Devices({}, self.runner, self.log, self.fatal, Path(self.temp.name))

    def refresh(self, entries):
        with patch.object(devices, "inventory", return_value={"adapters": entries, "usb_devices": []}):
            self.devices.refresh()

    def test_only_eligible_selected_and_no_radio_claim_on_discovery(self):
        with patch.object(devices, "Lease") as lease:
            self.refresh([{"name": "wlan0", "eligible": False}, {"name": "wlx123", "eligible": True}])
            self.assertEqual(self.devices.selected, "wlx123")
            lease.assert_not_called()
        self.assertFalse((Path(self.temp.name) / "selected-adapter.json").exists())

    def test_multiple_require_selection_and_explicit_choice_survives_restart(self):
        entries = [{"name": name, "eligible": True} for name in ("wlan0", "wlan1")]
        self.refresh(entries)
        self.assertIsNone(self.devices.selected)
        self.devices.choose("wlan1")
        other = devices.Devices({}, self.runner, self.log, self.fatal, Path(self.temp.name))
        with patch.object(devices, "inventory", return_value={"adapters": entries, "usb_devices": []}):
            other.refresh()
        self.assertEqual(other.selected, "wlan1")

    def test_busy_missing_and_active_lease_cannot_be_selected(self):
        self.refresh([{"name": "wlan0", "eligible": False}])
        for value in ("wlan0", "eth0", None, "../net"):
            with self.assertRaises(ValueError):
                self.devices.choose(value)
        self.refresh([{"name": "wlan1", "eligible": True}])
        self.devices.lease = Mock()
        with self.assertRaisesRegex(ValueError, "Restart"):
            self.devices.choose("wlan1")

    def test_helper_failure_keeps_ui_available_without_claiming_radio(self):
        with patch.object(devices, "inventory", side_effect=RuntimeError("Helper unavailable")):
            self.devices.initialize()
        self.assertIn("unavailable", self.devices.error)
        self.assertFalse(self.fatal.is_set())
        self.runner.start.assert_not_called()

    def test_assignment_rechecked_on_start_and_failure_never_runs_script(self):
        self.refresh([{"name": "wlan1", "eligible": True}])
        with patch.object(devices, "Lease", side_effect=RuntimeError("now in use")):
            with self.assertRaises(RuntimeError):
                self.devices.start()
        self.runner.start.assert_not_called()
        self.assertIsNone(self.devices.lease)

    def test_assigned_identity_mismatch_stops_app(self):
        self.refresh([{"name": "wlan1", "eligible": True}])
        self.runner.adapter = Adapter("wlan1", "phy9", 3)
        with patch.object(devices, "Lease", return_value=Mock(phy="phy0", power_save="on")):
            with self.assertRaisesRegex(RuntimeError, "match"):
                self.devices.start()
        self.assertTrue(self.fatal.is_set())
        self.runner.start.assert_not_called()


@unittest.skipUnless(sys.platform == "linux", "Linux sysfs-style symlinks and Unix sockets")
class UsbTests(unittest.TestCase):
    def test_assigned_usb_radio_is_not_reported_as_missing_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "2-2.2"
            device.mkdir()
            for key, value in {"idVendor": "0cf3", "idProduct": "9271", "product": "UB91"}.items():
                (device / key).write_text(value)
            lease = {"name": "wlp4s0f3u2u2", "bus": "USB", "usb_path": "2-2.2"}
            row = inventory.usb_devices(root, leased=lease)[0]
            self.assertEqual(row["assigned_interface"], lease["name"])
            self.assertIn("Assigned", row["hint"])
            self.assertNotIn("requires", row["hint"])
            row = inventory.usb_devices(root, leased={**lease, "usb_path": "2-3"})[0]
            self.assertIsNone(row["assigned_interface"])
            self.assertIn("requires", row["hint"])

    def test_additional_driver_families_detected_without_interface_name_assumptions(self):
        for name in ("rt2800usb", "mt7921u", "mwifiex_usb", "ath6kl_usb", "brcmfmac", "rtw_8822bu"):
            with self.subTest(driver=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                device = root / "1-1"
                device.mkdir()
                (device / "idVendor").write_text("1234")
                (device / "idProduct").write_text("5678")
                child = root / "1-1:1.0"
                child.mkdir()
                driver = root / name
                driver.mkdir()
                (child / "driver").symlink_to(driver, target_is_directory=True)
                self.assertEqual(inventory.usb_devices(root)[0]["drivers"], [name])

    def test_host_module_inventory_reports_observed_modules_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("ath9k_htc", "rtw88_8822ce", "mt7921u", "unrelated"):
                (root / name).mkdir()
            info = inventory.host_drivers(root)
            self.assertEqual(info["loaded_wifi_modules"], ["ath9k_htc", "mt7921u", "rtw88_8822ce"])
            self.assertTrue(info["kernel"])

    def test_ar9271_usb_enumeration_distinguished_from_bound_wifi(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "2-2.2"
            device.mkdir()
            for key, value in {"idVendor": "0cf3", "idProduct": "9271", "product": "UB91"}.items():
                (device / key).write_text(value)
            first = inventory.usb_devices(root)[0]
            self.assertEqual(first["id"], "0cf3:9271")
            self.assertEqual(first["drivers"], [])
            self.assertIn("ath9k_htc", first["hint"])
            interface = root / "2-2.2:1.0"
            (interface / "net/wlan1").mkdir(parents=True)
            driver = root / "ath9k_htc"
            driver.mkdir()
            (interface / "driver").symlink_to(driver, target_is_directory=True)
            second = inventory.usb_devices(root)[0]
            self.assertEqual(second["interfaces"], ["wlan1"])
            self.assertEqual(second["drivers"], ["ath9k_htc"])
            self.assertEqual(second["hint"], "")


class SupplicantTests(unittest.TestCase):
    def test_power_save_restored_after_start_failure_only_on_owned_adapter(self):
        adapter = Adapter("wlan1", "phy0", 3)
        connection = supplicant.Supplicant(adapter, "on", Mock(), threading.Event())
        with patch.object(supplicant, "same_device") as guard, patch.object(supplicant, "command") as command, \
             patch.object(supplicant.tempfile, "TemporaryDirectory", side_effect=OSError("full")):
            with self.assertRaises(OSError):
                connection.start()
            connection.close()
        self.assertEqual(command.call_args_list[-1].args, ("iw", "dev", "wlan1", "set", "power_save", "on"))
        self.assertEqual(guard.call_count, 2)

    def test_unknown_power_save_not_modified(self):
        connection = supplicant.Supplicant(Adapter("wlan1", "phy0", 3), None, Mock(), threading.Event())
        with patch.object(supplicant, "same_device"), patch.object(supplicant, "command") as command, \
             patch.object(supplicant.tempfile, "TemporaryDirectory", side_effect=OSError("full")):
            with self.assertRaises(OSError):
                connection.start()
            connection.close()
        self.assertEqual(command.call_count, 1)

    @unittest.skipUnless(sys.platform == "linux", "Unix datagram control")
    def test_real_private_control_roundtrip_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "wlan1")
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as peer:
                peer.bind(path)
                peer.settimeout(3)
                def reply():
                    message, sender = peer.recvfrom(4096)
                    peer.sendto(b"PONG\n" if message == b"PING" else b"FAIL\n", sender)
                thread = threading.Thread(target=reply)
                thread.start()
                with supplicant.Control(path) as control:
                    self.assertEqual(control.request("PING"), "PONG")
                    client = Path(control.directory.name)
                thread.join(4)
                self.assertFalse(client.exists())
