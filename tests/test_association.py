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


class AssociationTests(unittest.TestCase):
    def associate(self, radio, **kwargs):
        self.logs = []
        return association.associate(ADAPTER, SSID, log=self.logs.append, run=radio,
                                     wait=lambda _: None, **{"guard": lambda _: None, **kwargs})

    def test_scan_selects_strongest_exact_open_ssid_only(self):
        weaker = SCAN.replace(MAC, "20:f1:b2:d7:08:03").replace("-42.00", "-75.00")
        unrelated = SCAN.replace(SSID, "SmartLife-9999").replace("-42.00", "-10.00")
        protected = [SCAN + line for line in ("\tRSN:\n", "\tWPA:\n")]
        protected.append(SCAN.replace("ESS ShortSlotTime", "ESS Privacy ShortSlotTime"))
        points = association.access_points(weaker + unrelated + "".join(protected) + SCAN, SSID)
        self.assertEqual([point.bssid for point in points], [MAC, "20:f1:b2:d7:08:03"])
        self.assertEqual(points[0].frequency, 2412)
        self.assertEqual(points[0].signal, -42)

    def test_timeout_with_zero_exit_code_is_not_success(self):
        radio = FakeRadio()
        with self.assertRaisesRegex(association.AssociationError, "DHCP was not started"):
            self.associate(radio)
        self.assertEqual(len(radio.connections()), 3)
        self.assertTrue(any("timed out" in line for line in self.logs))
        self.assertFalse(any("DHCP may now start" in line for line in self.logs))

    def test_verified_live_link_allows_dhcp_after_transient_failure(self):
        radio = FakeRadio(links=["Not connected.\n"] * 3 + [LINK])
        self.associate(radio)
        self.assertEqual(len(radio.connections()), 2)
        for args in radio.connections():
            self.assertEqual(args, ("iw", "dev", "wlp2s0", "connect", "-w", SSID, "2412", MAC, "auth", "open"))
        self.assertIn("DHCP may now start", self.logs[-1])

    def test_other_bssid_ssid_or_frequency_never_counts_as_success(self):
        wrong_links = [LINK.replace(MAC, "20:f1:b2:d7:08:04"), LINK.replace(SSID, "SmartLife-0804"),
                       LINK.replace("2412", "2437"), LINK.replace("\tfreq: 2412\n", "")]
        for link in wrong_links:
            with self.subTest(link=link), self.assertRaises(association.AssociationError):
                self.associate(FakeRadio(links=[link] * 9))

    def test_missing_or_disappearing_ap_is_rejected_without_selecting_another_ssid(self):
        other = SCAN.replace(SSID, "SmartLife-9999")
        for initial, refresh, attempts in ((other, SCAN, 0), (SCAN, other, 1)):
            radio = FakeRadio(scan=initial, refresh=refresh)
            with self.subTest(initial=initial), self.assertRaises(association.AssociationError):
                self.associate(radio)
            self.assertEqual(len(radio.connections()), attempts)

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
