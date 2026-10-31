import contextlib
from http.client import HTTPConnection
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'untuyaos3/app'))
import wifi,protocol,dhcp,server,devices,lease,supplicant
from wifi import Adapter,radio_unblocked,PreflightError
from journal import Journal
from runner import Runner
IW = "phy#0\n\tInterface wlan1\n\t\tifindex 4\n\t\ttype managed\n"
INFO = "Wiphy phy0\n\tSupported interface modes:\n\t\t * managed\n\t\t * AP\n\tBand 1:\n"
CANDIDATE = {"name": "wlan1", "phy": "phy0", "type": "managed"}
MAC = "02:00:00:00:00:01"
SNAPSHOT = {"name": "wlan1", "phy": "phy3", "mac": MAC, "bus": "USB", "usb_path": "2-2.2", "driver": "ath9k_htc", "up": False, "managed": True}
DETAILS = {"bus": "USB", "usb_path": "2-2.2", "driver": "ath9k_htc"}
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
        with self.assertRaisesRegex(ValueError, "Wait"):
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
