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
class RecoveryTests(unittest.TestCase):


    @unittest.skipUnless(sys.platform == "linux", "Linux namespace descriptor type check")
    def test_return_rejects_regular_file_before_any_radio_mutation(self):
        import os
        active = lease.Lease.__new__(lease.Lease)
        active.options, active.interface, active.phy = {}, "wlan1", "phy3"
        active.closed, active.sock, active.journal = threading.Event(), Mock(), Mock()
        with tempfile.TemporaryFile() as file:
            descriptor = os.dup(file.fileno())
            with patch.object(lease, "connect", return_value=Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False))), \
                 patch.object(lease, "send"), patch.object(lease, "receive", return_value=({"event": "return_target", "phy": "phy3"}, [descriptor])), \
                 patch.object(lease.subprocess, "run") as mutate:
                with self.assertRaises((OSError, RuntimeError)):
                    active.release(Adapter("wlan1", "phy3", 3))
            mutate.assert_not_called()
            with self.assertRaises(OSError):
                os.fstat(descriptor)


    def test_completion_releases_lease_and_allows_adapter_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, journal, fatal = Mock(), Mock(), threading.Event()
            runner.options = {}
            manager = devices.Devices({}, runner, journal, fatal, Path(directory))
            radio = Adapter("wlan1", "phy3", 3)
            runner.adapter, runner.state = radio, "releasing"
            active = Mock()
            manager.lease = active
            with patch.object(devices, "inventory", return_value={"adapters": [{"name": "wlan2", "eligible": True}], "usb_devices": []}):
                manager.finished()
            active.release.assert_called_once_with(radio)
            self.assertIsNone(manager.lease)
            self.assertFalse(manager.status()["selection_locked"])
            self.assertEqual(runner.state, "releasing")  # Runner alone publishes the final outcome.
            runner.state = "cancelled"
            manager.choose("wlan2")
            self.assertFalse(fatal.is_set())


    def test_repeated_start_never_releases_an_active_radio(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Mock(options={})
            manager = devices.Devices({}, runner, Mock(), threading.Event(), Path(directory))
            runner.state = "running"
            active = Mock()
            manager.lease, manager.selected = active, "wlan1"
            with self.assertRaisesRegex(ValueError, "already active"):
                manager.start()
            active.release.assert_not_called()
            self.assertIs(manager.lease, active)
            runner.start.assert_not_called()
