"""NetworkManager checks must parse busctl's actual method/property JSON shapes."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "untuyaos3/app"))
import wifi

spec = importlib.util.spec_from_file_location("broker_bus_test", ROOT / "untuyaos3_wifi/app/broker.py")
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)

DEVICE = "/org/freedesktop/NetworkManager/Devices/7"
ACTIVE = "/org/freedesktop/NetworkManager/ActiveConnection/4"


def replies(managed=False, state=30, active="/"):
    return [json.dumps(reply) for reply in (
        {"type": "o", "data": [DEVICE]},  # A method reply wraps its output arguments.
        {"type": "b", "data": managed},  # A property carries its scalar directly.
        {"type": "u", "data": state},
        {"type": "o", "data": active},
    )]


class BusctlTests(unittest.TestCase):
    def property(self, name):
        return wifi.bus("get-property", wifi.NM, DEVICE, wifi.NM + ".Device", name)

    def test_scalar_properties_keep_their_native_value_and_type(self):
        for name, signature, value in (("Managed", "b", False), ("Managed", "b", True),
                                       ("State", "u", 10), ("State", "u", 30),
                                       ("ActiveConnection", "o", "/"), ("ActiveConnection", "o", ACTIVE)):
            with self.subTest(name=name, value=value), patch(
                "wifi.command", return_value=json.dumps({"type": signature, "data": value})
            ):
                actual = self.property(name)
                self.assertEqual(actual, value)
                self.assertIs(type(actual), type(value))

    def test_method_reply_unwraps_one_complete_object_path(self):
        with patch("wifi.command", return_value=json.dumps({"type": "o", "data": [DEVICE]})):
            self.assertEqual(wifi.bus("call", wifi.NM, "/org/freedesktop/NetworkManager", wifi.NM,
                                      "GetDeviceByIpIface", "s", "wlp2s0"), DEVICE)

    def test_idle_adapter_checks_use_real_busctl_json_without_mutations(self):
        for managed in (False, True):
            with patch("wifi.command", side_effect=replies(managed=managed)) as reads, \
                    patch.object(broker, "command") as changes:
                self.assertIs(broker.nm_properties("wlp2s0"), managed)
                self.assertEqual(reads.call_count, 4)
                changes.assert_not_called()
        with patch("wifi.command", side_effect=replies(state=10)):
            wifi.nm_unmanaged("wlp2s0")

    def test_active_connection_path_is_not_truncated_to_root(self):
        with patch("wifi.command", side_effect=replies(state=30, active=ACTIVE)), \
                patch.object(broker, "command") as changes:
            with self.assertRaisesRegex(wifi.PreflightError, "not idle"):
                broker.nm_properties("wlp2s0")
            changes.assert_not_called()

    def test_bad_property_responses_fail_closed_with_property_context(self):
        invalid = ("not-json", "null", "[]", "{}", '{"type":"b"}',
                   '{"type":"b","data":[false]}', '{"type":"b","data":"false"}',
                   '{"type":"b","data":0}', '{"type":"u","data":30}')
        for output in invalid:
            with self.subTest(output=output), patch("wifi.command", return_value=output):
                with self.assertRaisesRegex(wifi.PreflightError, "Managed"):
                    self.property("Managed")

    def test_method_return_cardinality_is_checked(self):
        for values in ([], [DEVICE, DEVICE], DEVICE, None):
            with self.subTest(values=values), patch(
                "wifi.command", return_value=json.dumps({"type": "o", "data": values})
            ):
                with self.assertRaisesRegex(wifi.PreflightError, "GetDeviceByIpIface"):
                    wifi.bus("call", wifi.NM, "/org/freedesktop/NetworkManager", wifi.NM,
                             "GetDeviceByIpIface", "s", "wlp2s0")


if __name__ == "__main__":
    unittest.main()
