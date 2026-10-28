"""Dynamic DHCP-to-OTA endpoint and scoped cleanup regressions; no host networking."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "untuyaos3/app"))
import dhcp
import ota_target
import wifi


def environment(subnet=175):
    return {"interface": "wlan1", "UNTUYAOS3_ALLOWED_IFACE": "wlan1", "UNTUYAOS3_ALLOWED_PHY": "phy8",
            "UNTUYAOS3_ALLOWED_IFINDEX": "405", "UNTUYAOS3_RUN_ID": "a"*32,
            "ip": f"192.168.{subnet}.100", "subnet": "255.255.255.0",
            "serverid": f"192.168.{subnet}.1", "router": f"192.168.{subnet}.1"}


class LeaseTargetTests(unittest.TestCase):
    def test_175_and_original_176_use_their_own_dhcp_target(self):
        for subnet in (175, 176):
            self.assertEqual(dhcp.lease_details(environment(subnet), []),
                             (f"192.168.{subnet}.100/24", f"192.168.{subnet}.1"))

    def test_offlink_ambiguous_self_public_or_overlapping_targets_fail(self):
        base = environment()
        for changed in ({"serverid": "192.168.176.1"}, {"router": "192.168.175.2"},
                        {"serverid": base["ip"], "router": base["ip"]},
                        {"ip": "8.8.8.2", "serverid": "8.8.8.1", "router": "8.8.8.1"},
                        {"ip": "169.254.1.2", "serverid": "169.254.1.1", "router": "169.254.1.1"},
                        {"interface": "eth0"}, {"subnet": "255.255.0.0"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                dhcp.lease_details({**base, **changed}, [])
        with self.assertRaisesRegex(ValueError, "overlaps"):
            dhcp.lease_details(base, [{"dst": "192.168.175.0/24", "dev": "eth0"}])

    @unittest.skipUnless(sys.platform == "linux", "Linux private runtime directory permissions")
    def test_dhcp_hook_to_ota_target_and_deconfig_clears_record(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            runtime = Path(directory)
            with tempfile.TemporaryDirectory(prefix="untuya-session-", dir=runtime) as session:
                env = {**environment(), "UNTUYAOS3_RUN_DIR": session}
                with patch.object(ota_target, "RUNTIME", runtime), patch.dict(dhcp.os.environ, env, clear=True), \
                     patch.object(dhcp, "same_device"), patch.object(dhcp, "command", return_value="[]") as configure, \
                     patch.object(sys, "argv", ["dhcp.py", "bound"]):
                    dhcp.main()
                    configure.assert_any_call("ip", "-4", "address", "replace", "192.168.175.100/24", "dev", "wlan1")
                    self.assertFalse(any("default" in call.args or "resolv" in str(call.args) for call in configure.call_args_list))
                    def run(*args):
                        if "address" in args:
                            return json.dumps([{"addr_info": [{"local": env["ip"], "prefixlen": 24}]}])
                        return json.dumps([{"dev": "wlan1"}])
                    self.assertEqual(ota_target.load_target(env, run=run, guard=lambda _: None), "192.168.175.1")
                    with self.assertRaisesRegex(ValueError, "different session"):
                        ota_target.load_target({**env, "UNTUYAOS3_RUN_ID": "b"*32}, run=run, guard=lambda _: None)
                    with self.assertRaisesRegex(ValueError, "directly reachable"):
                        ota_target.load_target(env, run=lambda *args: run(*args) if "address" in args else '[{"dev":"eth0","gateway":"172.30.32.1"}]', guard=lambda _: None)
                    with patch.object(sys, "argv", ["dhcp.py", "deconfig"]):
                        dhcp.main()
                    self.assertFalse((Path(session) / "target.json").exists())
                    with self.assertRaises(FileNotFoundError):
                        ota_target.load_target(env, run=run, guard=lambda _: None)

    def test_unexpected_protocol_response_does_not_bypass_expected_stage(self):
        with self.assertRaisesRegex(RuntimeError, "0x0C; expected 0x16"):
            ota_target.expect_frame_type(Mock(type=0x0C), 0x16)
        ota_target.expect_frame_type(Mock(type=0x16), 0x16)


class CleanupTests(unittest.TestCase):
    def test_cleanup_removes_and_verifies_only_the_selected_interfaces_state(self):
        calls = []
        def run(*args):
            calls.append(args)
            if args[-1] == "link":
                return "Not connected."
            if "address" in args and "show" in args:
                return '[{"flags":[], "addr_info":[]}]'
            if "route" in args and "show" in args:
                return '[{"dst":"default","dev":"eth0"},{"dst":"172.30.32.0/23","dev":"eth0"}]'
            return ""
        with patch.object(wifi, "same_device"), patch.object(wifi, "command", side_effect=run):
            self.assertTrue(wifi.cleanup(wifi.Adapter("wlan1", "phy8", 405), lambda *_: None))
        self.assertIn(("ip", "-6", "address", "flush", "dev", "wlan1"), calls)
        for family in ("-4", "-6"):
            self.assertIn(("ip", family, "route", "flush", "table", "all", "dev", "wlan1"), calls)
        self.assertTrue(all("wlan1" in call for call in calls if "set" in call or "flush" in call or "disconnect" in call))

    def test_cleanup_detects_remaining_ipv6_or_routes(self):
        for survivor in ("address", "route"):
            def run(*args):
                if args[-1] == "link":
                    return "Not connected."
                if "address" in args and "show" in args:
                    return json.dumps([{"addr_info": [{"local": "fe80::1"}] if survivor == "address" else []}])
                if "route" in args and "show" in args:
                    return '[{"dev":"wlan1"}]' if survivor == "route" else "[]"
                return ""
            with self.subTest(survivor=survivor), patch.object(wifi, "same_device"), patch.object(wifi, "command", side_effect=run):
                self.assertFalse(wifi.cleanup(wifi.Adapter("wlan1", "phy8", 405), lambda *_: None))
