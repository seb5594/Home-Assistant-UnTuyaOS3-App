"""iw's exit code alone does not prove the device AP was joined."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "untuyaos3/app"))
import association
from wifi import Adapter

SSID = "SmartLife-0803"
MAC = "20:f1:b2:d7:08:02"
ADAPTER = Adapter("wlp2s0", "phy0", 3)
SCAN = f"""BSS {MAC}(on wlp2s0)
\tfreq: 2412
\tsignal: -42.00 dBm
\tcapability: ESS ShortSlotTime (0x0401)
\tSSID: {SSID}
"""
LINK = f"Connected to {MAC} (on wlp2s0)\n\tSSID: {SSID}\n\tfreq: 2412\n\tsignal: -42 dBm\n"


class FakeRadio:
    def __init__(self, links=(), scan=SCAN, refresh=SCAN):
        self.links, self.scan, self.refresh = list(links), scan, refresh
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if args[-2:] == ("scan", "dump"):
            return 0, self.scan
        if "scan" in args:
            return 0, self.refresh
        if args[-1] == "link":
            return 0, self.links.pop(0) if self.links else "Not connected.\n"
        if "connect" in args:
            # The observed failure: exit=0, but the connect event says timeout.
            return 0, f"wlp2s0 (phy #0): timed out to {MAC}\n"
        return 0, ""

    def connections(self):
        return [args for args, _ in self.calls if "connect" in args]


class FakeControl:
    def __init__(self, completed=True, transient=0, ssid=SSID, reject=False):
        self.completed, self.transient, self.ssid, self.reject = completed, transient, ssid, reject
        self.calls, self.status_calls = [], 0

    def request(self, message):
        self.calls.append(message)
        if message == "ADD_NETWORK":
            return "0"
        if message == "STATUS":
            self.status_calls += 1
            state = "COMPLETED" if self.completed and self.status_calls > self.transient else "SCANNING"
            return f"wpa_state={state}\nssid={self.ssid}\nbssid={MAC}\nfreq=2412"
        return "FAIL" if self.reject and message.startswith("SET_NETWORK") else "OK"


class AssociationTests(unittest.TestCase):
    def associate(self, radio, **kwargs):
        self.logs = []
        return association.associate(ADAPTER, SSID, log=self.logs.append, run=radio,
                                     wait=lambda _: None, checks=6, **{"guard": lambda _: None, **kwargs})

    def test_scan_selects_strongest_exact_open_ssid_only(self):
        weaker = SCAN.replace(MAC, "20:f1:b2:d7:08:03").replace("-42.00", "-75.00")
        unrelated = SCAN.replace(SSID, "SmartLife-9999").replace("-42.00", "-10.00")
        protected = [SCAN + line for line in ("\tRSN:\n", "\tWPA:\n")]
        protected.append(SCAN.replace("ESS ShortSlotTime", "ESS Privacy ShortSlotTime"))
        points = association.access_points(weaker + unrelated + "".join(protected) + SCAN, SSID)
        self.assertEqual([point.bssid for point in points], [MAC, "20:f1:b2:d7:08:03"])
        self.assertEqual(points[0].frequency, 2412)
        self.assertEqual(points[0].signal, -42)

    def test_disconnected_status_never_allows_dhcp(self):
        with self.assertRaisesRegex(association.AssociationError, "DHCP was not started"):
            self.associate(FakeRadio(), control=FakeControl(completed=False))
        self.assertFalse(any("DHCP may now start" in line for line in self.logs))

    def test_transient_scan_miss_and_disconnection_recover(self):
        control = FakeControl(transient=3)
        self.associate(FakeRadio(scan="", refresh="", links=[LINK]), control=control)
        self.assertIn("DHCP may now start", self.logs[-1])
        self.assertEqual(control.status_calls, 4)
        self.assertFalse(any("REMOVE_NETWORK" in call for call in control.calls))
        self.assertIn("SET_NETWORK 0 ssid " + SSID.encode().hex(), control.calls)

    def test_completed_status_requires_independent_matching_link(self):
        for link in ("Not connected.", LINK.replace(MAC, "20:f1:b2:d7:08:04"),
                     LINK.replace(SSID, "other"), LINK.replace("2412", "2437")):
            control = FakeControl()
            with self.subTest(link=link), self.assertRaises(association.AssociationError):
                self.associate(FakeRadio(links=[link]*6), control=control)
            self.assertIn("REMOVE_NETWORK 0", control.calls)

    def test_selected_bssid_pinned_and_fractional_iw_frequency_accepted(self):
        control = FakeControl()
        self.associate(FakeRadio(scan=SCAN.replace("2412", "2412.0"), links=[LINK.replace("2412", "2412.0")]), control=control)
        self.assertIn("SET_NETWORK 0 bssid " + MAC, control.calls)

    def test_other_ssid_in_status_rejected(self):
        control = FakeControl(ssid="SmartLife-9999")
        with self.assertRaises(association.AssociationError):
            self.associate(FakeRadio(links=[LINK]*6), control=control)

    def test_control_failure_and_invalid_ssid_fail_closed(self):
        for ssid in ("", "x"*33, "SmartLife\nADD_NETWORK"):
            with self.assertRaises(association.AssociationError):
                association.associate(ADAPTER, ssid, guard=lambda _: None)
        control = FakeControl(reject=True)
        with self.assertRaises(association.AssociationError):
            self.associate(FakeRadio(), control=control)
        self.assertIn("REMOVE_NETWORK 0", control.calls)

    def test_adapter_replacement_stops_before_any_mutation(self):
        radio = FakeRadio()
        with self.assertRaisesRegex(RuntimeError, "replaced"):
            self.associate(radio, guard=lambda _: (_ for _ in ()).throw(RuntimeError("adapter replaced")))
        self.assertFalse(radio.calls)

    def test_subprocess_timeout_preserves_driver_output(self):
        for output in (b"connect event", "connect event"):
            with self.subTest(output=output), patch.object(association.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired(["iw"], 15, output=output)):
                code, text = association.command("iw", timeout=15)
                self.assertEqual(code, 124)
                self.assertIn("connect event", text)

    def test_cli_rejects_unapproved_interface_before_running_commands(self):
        with patch.object(sys, "argv", ["association.py", "eth0", SSID]), \
             patch.dict(association.os.environ, {"UNTUYAOS3_ALLOWED_IFACE": "wlp2s0"}), \
             patch.object(association, "associate") as connect:
            with self.assertRaisesRegex(association.AssociationError, "Unapproved"):
                association.main()
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
