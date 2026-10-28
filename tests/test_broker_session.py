"""Real authenticated Unix IPC with mocked radio operations: never touches host Wi-Fi."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "untuyaos3/app"))
sys.path.insert(1, str(ROOT / "untuyaos3_wifi/app"))
import broker
import lease
import protocol
from wifi import Adapter


@unittest.skipUnless(sys.platform == "linux", "Linux SCM_RIGHTS")
class BrokerSessionTests(unittest.TestCase):
    def test_pending_recovery_keeps_authenticated_inventory_available(self):
        from wifi import PreflightError
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            path = str(root / "wifi.sock")
            options = {"pairing_token": "private-test-secret-" * 3}
            (root / "options.json").write_text(json.dumps(options))
            (root / "recovery.json").write_text(json.dumps({"name": "wlan1", "phy": "phy3", "mac": "02:00:00:00:00:01"}))
            stopping = threading.Event()
            with contextlib.ExitStack() as stack:
                for target, name, value in (
                    (broker, "DATA", root), (broker, "SOCKET", path), (lease, "SOCKET", path),
                    (broker, "stopping", stopping), (broker, "secure_directory", Mock()),
                    (broker, "command", Mock(return_value="phy#6\n\tInterface wlan1\n\t\ttype managed\n")),
                    (broker, "inventory", Mock(return_value={"adapters": [], "usb_devices": []})),
                    (broker, "restore", Mock(side_effect=PreflightError("USB device missing"))),
                ):
                    stack.enter_context(patch.object(target, name, value))
                thread = threading.Thread(target=broker.main, daemon=True)
                thread.start()
                try:
                    for _ in range(100):
                        if Path(path).exists():
                            break
                        time.sleep(0.02)
                    result = lease.inventory(options)
                    self.assertEqual(result["recovery_pending"], "USB device missing")
                    self.assertTrue(thread.is_alive())
                    self.assertTrue((root / "recovery.json").exists())
                finally:
                    stopping.set()
                    thread.join(5)

    def test_inventory_lease_return_and_second_lease_with_same_helper(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            path = str(root / "wifi.sock")
            options = {"pairing_token": "private-test-secret-" * 3}
            (root / "options.json").write_text(json.dumps(options))
            snapshot = {"name": "wlan1", "phy": "phy0", "mac": "02:00:00:00:00:01", "power_save": "on"}
            stopping = threading.Event()
            restored = threading.Event()
            fatal = threading.Event()
            result = []
            with contextlib.ExitStack() as stack:
                for target, name, value in (
                    (broker, "DATA", root), (broker, "SOCKET", path), (lease, "SOCKET", path),
                    (broker, "stopping", stopping), (broker, "secure_directory", Mock()),
                    (broker, "command", Mock(return_value="phy#0\n\tInterface wlan1\n\t\ttype managed\n")),
                    (broker, "inventory", Mock(return_value={"adapters": [{"name": "wlan1", "eligible": True}], "usb_devices": []})),
                    (broker, "handover", Mock(return_value=(Adapter("wlan1", "phy0", 3), snapshot))),
                    (broker, "restore", Mock(side_effect=lambda *args, **kwargs: restored.set())),
                ):
                    stack.enter_context(patch.object(target, name, value))
                thread = threading.Thread(target=lambda: result.append(broker.main()), daemon=True)
                thread.start()
                active = None
                try:
                    for _ in range(100):
                        if Path(path).exists():
                            break
                        time.sleep(0.02)
                    self.assertEqual(lease.inventory(options)["adapters"][0]["name"], "wlan1")
                    for _ in range(2):
                        restored.clear()
                        active = lease.Lease(options, Mock(), fatal, "wlan1")
                        self.assertEqual(active.power_save, "on")
                        self.assertEqual(active.phy, "phy0")
                        # Discovery remains available while the radio is assigned.
                        self.assertTrue(lease.inventory(options)["adapters"])
                        with patch.object(lease, "same_device"), patch.object(lease, "command", return_value=json.dumps([{"address": snapshot["mac"]}])), patch.object(lease.subprocess, "run", return_value=Mock(returncode=0)) as move:
                            active.release(Adapter("wlan1", "phy0", 3))
                        self.assertEqual(move.call_args.args[0][:6], ["iw", "phy", "phy0", "set", "netns", "name"])
                        active = None
                        self.assertTrue(restored.wait(3))
                        self.assertFalse(fatal.is_set())
                    self.assertEqual(broker.handover.call_count, 2)
                    self.assertEqual(broker.restore.call_count, 2)
                finally:
                    if active:
                        active.close()
                    stopping.set()
                    thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(result, [0])

    def test_protocol_mismatch_fails_before_namespace_transfer(self):
        import socket
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        with left, right:
            protocol.send(right, {"protocol": 1, "challenge": "a" * 64})
            with self.assertRaisesRegex(ValueError, "Update both"):
                protocol.client_authenticate(left, protocol.INVENTORY, "secret" * 8)

    def test_uncertain_assignment_stops_main_but_safe_rejection_does_not(self):
        for response, expected in (({"error": "busy", "restart_required": False}, False),
                                   ({"error": "restoration pending", "restart_required": True}, True)):
            fatal = threading.Event()
            sock = Mock()
            with patch.object(lease, "connect", return_value=sock), patch.object(lease, "send"), \
                 patch.object(lease, "receive", return_value=(response, [])):
                with self.assertRaises(RuntimeError):
                    lease.Lease({}, Mock(), fatal, "wlan1")
            self.assertEqual(fatal.is_set(), expected)
            sock.close.assert_called_once()
