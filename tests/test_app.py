import contextlib
from http.client import HTTPConnection
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "untuyaos3/app"))
sys.path.insert(1, str(ROOT / "untuyaos3_wifi/app"))
import wifi
import protocol
import dhcp
import server
from journal import Journal
from runner import Runner

spec = importlib.util.spec_from_file_location("broker", ROOT / "untuyaos3_wifi/app/broker.py")
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)

IW = "phy#0\n\tInterface wlan1\n\t\tifindex 4\n\t\ttype managed\n"
INFO = "Wiphy phy0\n\tSupported interface modes:\n\t\t * managed\n\t\t * AP\n\tBand 1:\n"
CANDIDATE = {"name": "wlan1", "phy": "phy0", "type": "managed"}


class DiscoveryTests(unittest.TestCase):
    def run_fake(self, *, flags=None, addresses=None, master=None, routes=None, info=INFO, link="Not connected."):
        def run(*args):
            if args[:2] == ("iw", "phy"):
                return info
            if args[:3] == ("ip", "-j", "address"):
                return json.dumps([{"ifindex": 4, "flags": flags or [], "addr_info": addresses or [], "master": master}])
            if args[0] == "ip":
                return json.dumps(routes or [])
            return link
        return run

    def test_free_ap_adapter_is_accepted_without_mutations(self):
        calls = []
        run = self.run_fake()
        def traced(*args):
            calls.append(args)
            return run(*args)
        adapter = wifi.inspect(CANDIDATE, [CANDIDATE], run=traced)
        self.assertEqual(adapter.name, "wlan1")
        self.assertFalse(any("set" in c or "flush" in c or "disconnect" in c for c in calls))

    def test_rejects_host_management_radio_routes_and_shared_phy(self):
        cases = [
            self.run_fake(flags=["UP"]),
            self.run_fake(addresses=[{"local": "192.168.1.5"}]),
            self.run_fake(master="br0"),
            self.run_fake(routes=[{"dst": "default", "dev": "wlan1"}]),
            self.run_fake(routes=[{"nexthops": [{"dev": "wlan1"}]}]),
            self.run_fake(link="Connected to 00:11:22:33:44:55"),
        ]
        for run in cases:
            with self.subTest(run=run), self.assertRaises(wifi.PreflightError):
                wifi.inspect(CANDIDATE, [CANDIDATE], run=run)
        with self.assertRaises(wifi.PreflightError):
            wifi.inspect(CANDIDATE, [CANDIDATE, {**CANDIDATE, "name": "wlan1-ap"}], run=self.run_fake())

    def test_ap_exact_mode_required(self):
        for modes in ("managed", "managed\n\t\t * AP/VLAN", "managed\n\t\t * P2P-GO"):
            with self.subTest(modes=modes), self.assertRaises(wifi.PreflightError):
                wifi.inspect(CANDIDATE, [CANDIDATE], run=self.run_fake(info=INFO.replace("managed\n\t\t * AP", modes)))

    def test_host_idle_up_is_allowed_but_associated_is_not(self):
        wifi.inspect(CANDIDATE, [CANDIDATE], run=self.run_fake(flags=["UP"]), allow_up=True)
        with self.assertRaises(wifi.PreflightError):
            wifi.inspect(CANDIDATE, [CANDIDATE], run=self.run_fake(flags=["UP"], link="Connected"), allow_up=True)

    def test_networkmanager_missing_or_active_fails_closed(self):
        with patch("wifi.bus", side_effect=[str("/device/1"), True, 100, "/active/1"]):
            with self.assertRaises(wifi.PreflightError):
                wifi.nm_unmanaged("wlan1")
        with patch("wifi.bus", side_effect=wifi.PreflightError("bus unavailable")):
            with self.assertRaises(wifi.PreflightError):
                wifi.nm_unmanaged("wlan1")

    def test_no_adapter_startup_and_no_automatic_fallback(self):
        with patch("wifi.command", return_value=""):
            with self.assertRaises(wifi.PreflightError):
                wifi.discover("wlan1", lambda *_: None)
        with patch("wifi.command", return_value=IW):
            with self.assertRaises(wifi.PreflightError):
                wifi.discover("wlan9", lambda *_: None)

    def test_cleanup_refuses_replaced_adapter(self):
        with patch("wifi.same_device", side_effect=wifi.PreflightError("replaced")), patch("wifi.command") as run:
            self.assertFalse(wifi.cleanup(wifi.Adapter("wlan1", "phy0", 4), lambda *_: None))
            run.assert_not_called()


class LeaseTests(unittest.TestCase):
    def test_host_validation_accepts_phy_info_without_namespace_command_text(self):
        for name in ("wlp2s0", "wlp4s0f3u2u2"):
            def radio(*args):
                if args == ("iw", "dev"):
                    return IW.replace("wlan1", name)
                if args[:2] == ("iw", "phy"):
                    return INFO + "\tSupported commands:\n\t\t * new_interface\n\t\t * connect\n"
                if args[-2:] == ("get", "power_save"):
                    return "Power save: on"
                if args[0] == "ip" and args[2] in ("address", "link"):
                    return json.dumps([{"ifindex": 4, "address": "dc:e9:94:8c:9a:1b", "flags": ["UP"], "addr_info": []}])
                if args[0] == "ip":
                    return "[]"
                return "Not connected."
            def inspect(candidate, interfaces, **kwargs):
                return wifi.inspect(candidate, interfaces, run=radio, **kwargs)
            with self.subTest(name=name), patch.object(broker, "command", side_effect=radio), \
                 patch.object(broker, "inspect", side_effect=inspect), patch.object(broker, "nm_properties", return_value=True), \
                 patch.object(broker, "radio_unblocked"), patch.object(broker, "nm_set") as mutate:
                adapter, snapshot = broker.validate_host(name, lambda *_: None)
                self.assertEqual(adapter.name, name)
                self.assertEqual(snapshot["power_save"], "on")
                mutate.assert_not_called()

    def test_kernel_rejected_namespace_move_still_restores_and_fails(self):
        from types import SimpleNamespace
        adapter = wifi.Adapter("wlan1", "phy0", 4)
        snapshot = {"managed": True, "name": "wlan1", "phy": "phy0"}
        with tempfile.TemporaryDirectory() as temp, patch.object(broker, "DATA", Path(temp)), \
             patch.object(broker, "check_target"), patch.object(broker, "validate_host", return_value=(adapter, snapshot)), \
             patch.object(broker, "nm_set"), patch.object(broker, "command", return_value=IW), \
             patch.object(broker, "inspect"), patch.object(broker.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="Operation not supported")), \
             patch.object(broker, "restore") as restore:
            with self.assertRaisesRegex(wifi.PreflightError, "Namespace handover failed.*Operation not supported"):
                broker.handover(8, "wlan1", lambda *_: None)
            restore.assert_called_once_with(snapshot, unittest.mock.ANY, wait=2)

    def test_only_requested_interface_and_safe_subnet(self):
        env = {"interface": "wlan1", "UNTUYAOS3_ALLOWED_IFACE": "wlan1", "ip": "192.168.176.2", "subnet": "255.255.255.0"}
        self.assertEqual(dhcp.validate_lease(env, [{"dst": "default", "dev": "eth0"}]), "192.168.176.2/24")
        for changed in ({**env, "interface": "eth0"}, {**env, "subnet": "0.0.0.0"}, {**env, "ip": "10.0.0.2"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                dhcp.validate_lease(changed, [{"dst": "172.30.32.0/23", "dev": "eth0"}])
        with self.assertRaises(ValueError):
            dhcp.validate_lease(env, [{"dst": "192.168.176.0/24", "dev": "eth0"}])

    def test_numeric_input_only_and_config_validation(self):
        runner = Runner({}, None, threading.Event())
        for choice in ("$(id)", "1\n2", "", None, "-1"):
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                runner.input(choice)
        for options in ({}, {"interface": "wlan1", "pairing_token": "short"}):
            with self.assertRaises(ValueError):
                protocol.validate_options(options)

    @unittest.skipUnless(sys.platform == "linux", "Linux namespace/SCM_RIGHTS API")
    def test_real_fd_transport_and_namespace_type_rejection(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        with open("/proc/self/ns/net", "rb") as original:
            protocol.send(left, {"interface": "wlan1"}, original.fileno())
            data, fds = protocol.receive(right)
            self.assertEqual(data["interface"], "wlan1")
            self.assertEqual(os.fstat(fds[0]).st_ino, os.fstat(original.fileno()).st_ino)
            try:
                with self.assertRaises(ValueError):  # Cannot move a radio to the host's own namespace.
                    broker.check_target(fds[0])
            finally:
                os.close(fds[0])
        with tempfile.TemporaryFile() as file:
            with self.assertRaises(OSError):
                broker.check_target(file.fileno())

    @unittest.skipUnless(sys.platform == "linux", "Linux Unix socket transport")
    def test_mutual_authentication_and_wrong_secret(self):
        for correct in (True, False):
            left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            left.settimeout(2)
            right.settimeout(2)
            errors = []
            def helper():
                try:
                    protocol.server_authenticate(right, "wlan1", "private-" * 5)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    right.close()
            thread = threading.Thread(target=helper)
            thread.start()
            try:
                if correct:
                    protocol.client_authenticate(left, "wlan1", "private-" * 5)
                else:
                    with self.assertRaises((ValueError, ConnectionError)):
                        protocol.client_authenticate(left, "wlan1", "incorrect-" * 5)
            finally:
                left.close()
                thread.join(3)
            self.assertEqual(bool(errors), not correct)

    def test_failed_handover_restores_host_state(self):
        adapter = wifi.Adapter("wlan1", "phy0", 4)
        snapshot = {"managed": True, "name": "wlan1", "phy": "phy0"}
        with tempfile.TemporaryDirectory() as temp, patch.object(broker, "DATA", Path(temp)), \
             patch.object(broker, "check_target"), patch.object(broker, "validate_host", return_value=(adapter, snapshot)), \
             patch.object(broker, "nm_set"), patch.object(broker, "command", return_value=IW), \
             patch.object(broker, "inspect"), patch.object(broker.subprocess, "run", side_effect=OSError("driver unavailable")), \
             patch.object(broker, "restore") as restore:
            with self.assertRaises(OSError):
                broker.handover(8, "wlan1", lambda *_: None)
            restore.assert_called_once_with(snapshot, unittest.mock.ANY, wait=2)


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for platform in server.MAGIC:
            (self.root / platform).mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.journal = Journal(self.root / "logs")
        self.addCleanup(self.journal.close)
        self.runner = Runner({}, self.journal, threading.Event())
        self.runner.state = "ready"
        self.http = server.Server(("127.0.0.1", 0), self.runner, self.journal, self.root)
        self.addCleanup(self.http.server_close)
        thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.http.shutdown)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.trust = None

    def trusted(self):
        # Production still checks the real peer. Replace only the check in these HTTP tests.
        self.trust = patch.object(server.Handler, "trusted", return_value=True)
        self.trust.start()
        self.addCleanup(self.trust.stop)

    def request(self, path, data=None, headers=None):
        request = Request(self.url + path, data=data, headers=headers or {})
        try:
            with urlopen(request) as response:
                return response.status, response.read(), response.headers
        except HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def raw_post(self, path, body, headers, *, csrf=True):
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=3)
        try:
            connection.putrequest("POST", path)
            if csrf:
                connection.putheader("X-CSRF-Token", self.http.csrf)
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders(body)
            # An early 403 may close the peer before this test half-closes its
            # request. Still read and assert the actual HTTP response below.
            with contextlib.suppress(OSError):
                connection.sock.shutdown(socket.SHUT_WR)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def chunked_post(self, path, chunks, headers=None):
        connection = HTTPConnection("127.0.0.1", self.http.server_port, timeout=3)
        try:
            connection.request("POST", path, body=iter(chunks), encode_chunked=True,
                               headers={"X-CSRF-Token": self.http.csrf, **(headers or {})})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_spoofed_forwarding_headers_do_not_bypass_ingress(self):
        code, _, _ = self.request("/", headers={"X-Forwarded-For": "172.30.32.2", "X-Remote-User-Name": "admin"})
        self.assertEqual(code, 403)

    def test_csrf_and_asset_paths(self):
        self.trusted()
        self.assertEqual(self.request("/api/start", b"{}")[0], 403)
        code, body, headers = self.request("/")
        self.assertEqual(code, 200)
        self.assertIn(self.http.csrf.encode(), body)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("/../../data/options.json")[0], 404)
        self.assertEqual(self.request("/style.css")[0], 200)
        self.assertEqual(self.request("/app.js")[0], 200)

    def test_ingress_streamed_start_input_and_cancel(self):
        self.trusted()
        for path, body, method, args in (
            ("/api/start", b"{}", "start", ()),
            ("/api/input", b'{"choice":"2"}', "input", ("2",)),
            ("/api/cancel", b"{}", "cancel", ()),
        ):
            with self.subTest(path=path), patch.object(self.runner, method) as operation:
                code, result = self.chunked_post(path, [body[:1], body[1:]])
                self.assertEqual((code, result), (200, {"ok": True}))
                operation.assert_called_once_with(*args)

    def test_ingress_streamed_firmware_upload(self):
        self.trusted()
        image = bytes.fromhex("4d4d4d00") + b"x" * 64
        code, result = self.chunked_post("/api/firmware", [image[:2], image[2:]],
                                         {"X-Firmware-Platform": "T1", "X-Firmware-Name": "streamed.bin"})
        self.assertEqual((code, result), (201, {"ok": True}))
        self.assertEqual((self.root / "T1/streamed.bin").read_bytes(), image)

    def test_clear_logs_streamed_and_csrf_protected(self):
        self.trusted()
        self.journal.emit("info", "old session output", "terminal")
        old_generation = self.journal.generation
        self.assertEqual(self.request("/api/logs/clear", b"{}")[0], 403)
        code, result = self.chunked_post("/api/logs/clear", [b"{", b"}"])
        self.assertEqual(code, 200)
        self.assertNotEqual(result["generation"], old_generation)
        code, body, _ = self.request("/api/events?after=999&generation=" + old_generation)
        self.assertEqual(code, 200)
        self.assertNotIn(b"old session output", body)
        self.assertIn(b"Logs cleared", body)

    def test_adapter_controls_use_devices_and_require_csrf(self):
        from unittest.mock import Mock
        self.trusted()
        self.http.devices = Mock()
        for path, body, method, args in (
            ("/api/adapters/refresh", b"{}", "refresh", ()),
            ("/api/adapters/select", b'{"interface":"wlan1"}', "choose", ("wlan1",)),
            ("/api/start", b"{}", "start", ()),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, body)[0], 403)
                code, _ = self.chunked_post(path, [body])
                self.assertEqual(code, 200)
                getattr(self.http.devices, method).assert_called_once_with(*args)

    def test_streamed_requests_still_require_ingress_and_csrf(self):
        headers = [("Transfer-Encoding", "chunked")]
        self.assertEqual(self.raw_post("/api/start", b"2\r\n{}\r\n0\r\n\r\n", headers)[0], 403)
        self.trusted()
        self.assertEqual(self.raw_post("/api/start", b"2\r\n{}\r\n0\r\n\r\n", headers, csrf=False)[0], 403)

    def test_body_limits_apply_to_both_framing_modes_before_reading_payload(self):
        self.trusted()
        with patch.object(self.runner, "start") as start:
            for path, limit in (("/api/start", 2048), ("/api/firmware", server.MAX_UPLOAD)):
                for mode in ("Content-Length", "Transfer-Encoding"):
                    with self.subTest(path=path, mode=mode):
                        headers = [(mode, str(limit + 1) if mode == "Content-Length" else "chunked")]
                        body = b"" if mode == "Content-Length" else f"{limit + 1:x}\r\n".encode()
                        code, result = self.raw_post(path, body, headers)
                        self.assertEqual(code, 413)
                        self.assertIn(str(limit), result["error"])
            self.assertEqual(self.chunked_post("/api/start", [b"{" + b" " * 1024, b" " * 1024 + b"}"])[0], 413)
            start.assert_not_called()

    def test_control_body_exactly_at_limit_is_accepted_in_both_framing_modes(self):
        self.trusted()
        body = b"{}" + b" " * 2046
        with patch.object(self.runner, "start") as start:
            self.assertEqual(self.request("/api/start", body, {"X-CSRF-Token": self.http.csrf})[0], 200)
            self.assertEqual(self.chunked_post("/api/start", [body[:1000], body[1000:]])[0], 200)
            self.assertEqual(start.call_count, 2)

    def test_invalid_or_ambiguous_body_framing_is_rejected_and_logged(self):
        self.trusted()
        cases = [
            ([("Content-Length", "2"), ("Transfer-Encoding", "chunked")], b"", 400),
            ([("Content-Length", "2"), ("Content-Length", "2")], b"", 400),
            ([("Content-Length", "-1")], b"", 400),
            ([("Content-Length", "3")], b"{}", 400),
            ([("Transfer-Encoding", "gzip, chunked")], b"", 400),
            ([("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")], b"", 400),
            ([], b"", 411),
            ([("Transfer-Encoding", "chunked")], b"+2\r\n{}\r\n0\r\n\r\n", 400),
            ([("Transfer-Encoding", "chunked")], b"2\n{}\r\n0\r\n\r\n", 400),
            ([("Transfer-Encoding", "chunked")], b"2\r\n{}xx0\r\n\r\n", 400),
            ([("Transfer-Encoding", "chunked")], b"4\r\n{}", 400),
            ([("Transfer-Encoding", "chunked")], b"2\r\n{}\r\n0\r\n", 400),
            ([("Transfer-Encoding", "chunked")], b"0\r\ninvalid-trailer\r\n\r\n", 400),
            ([("Transfer-Encoding", "chunked")], b"f" * 1025 + b"\r\n", 400),
            ([("Transfer-Encoding", "chunked")], b"0\r\n" + (b"X: " + b"x" * 995 + b"\r\n") * 9 + b"\r\n", 400),
        ]
        with patch.object(self.runner, "start") as start:
            for headers, body, status in cases:
                with self.subTest(headers=headers, body=body):
                    self.assertEqual(self.raw_post("/api/start?private-query", body, headers)[0], status)
            start.assert_not_called()
        events = self.journal.snapshot(0)["events"]
        self.assertGreaterEqual(sum(e["level"] == "warning" for e in events), len(cases))
        self.assertFalse(any(self.http.csrf in e["text"] or "private-query" in e["text"] for e in events))

    def test_chunk_extensions_and_trailers_do_not_modify_request_headers(self):
        self.trusted()
        with patch.object(self.runner, "start") as start:
            body = b'2;extension=ignored\r\n{}\r\n0\r\nX-CSRF-Token: ignored\r\n\r\n'
            self.assertEqual(self.raw_post("/api/start", body, [("Transfer-Encoding", "Chunked")])[0], 200)
            start.assert_called_once_with()

    def test_firmware_signature_filename_and_active_run(self):
        self.trusted()
        headers = {"X-CSRF-Token": self.http.csrf, "X-Firmware-Platform": "T1", "X-Firmware-Name": "test.bin"}
        self.assertEqual(self.request("/api/firmware", b"not a UG image", headers)[0], 400)
        image = bytes.fromhex("4d4d4d00") + b"x"*64
        self.assertEqual(self.request("/api/firmware", image, {**headers, "X-Firmware-Name": "../test.bin"})[0], 400)
        self.assertEqual(self.request("/api/firmware", image, headers)[0], 201)
        self.assertEqual((self.root / "T1/test.bin").read_bytes(), image)
        self.runner.state = "running"
        self.assertEqual(self.request("/api/firmware", image, {**headers, "X-Firmware-Name": "second.bin"})[0], 400)

    def test_live_log_and_download_are_available(self):
        self.trusted()
        self.journal.emit("error", "adapter unavailable")
        code, body, _ = self.request("/api/events?after=0")
        self.assertEqual(code, 200)
        self.assertIn(b"adapter unavailable", body)
        code, body, headers = self.request("/api/logs")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertTrue(body.startswith(b"PK"))


@unittest.skipUnless(sys.platform == "linux", "Linux PTY and process groups")
class PtyTests(unittest.TestCase):
    def run_script(self, script, timeout=5):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "UnTuyaOS3.sh").write_text(script)
        with contextlib.redirect_stdout(io.StringIO()):
            journal = Journal(root / "logs")
        self.addCleanup(journal.close)
        runner = Runner({"interface": "wlan1", "run_timeout": timeout}, journal, threading.Event(), root, runtime=root)
        runner.adapter = wifi.Adapter("wlan1", "phy0", 4)
        runner.state = "ready"
        mocks = [
            patch("runner.discover", return_value=runner.adapter),
            patch("runner.same_device"),
            patch("runner.cleanup", return_value=True),
            patch("runner.Supplicant", return_value=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(
                start=lambda: "/run/fake-wpa", process=__import__("unittest.mock", fromlist=["Mock"]).Mock(poll=lambda: None))),
        ]
        for mock in mocks:
            mock.start()
            self.addCleanup(mock.stop)
        self.addCleanup(runner.shutdown)
        runner.start()
        return runner, journal

    def wait(self, predicate):
        deadline = time.monotonic()+8
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(predicate())

    def test_real_interactive_prompt_stdout_stderr_and_exit(self):
        runner, journal = self.run_script('printf "Enter choice: "; read -r choice; echo "selected=$choice"; echo diagnostic >&2; exit 7\n')
        self.wait(lambda: any("Enter choice" in e["text"] for e in journal.snapshot(0)["events"]))
        runner.input("2")
        runner.thread.join(5)
        self.assertEqual(runner.state, "failed")
        self.assertEqual(runner.exit_code, 7)
        output = "".join(e["text"] for e in journal.snapshot(0)["events"] if e["channel"] == "terminal")
        self.assertIn("selected=2", output)
        self.assertIn("diagnostic", output)
        self.assertFalse(list(runner.runtime.glob("untuya-session-*")))

    def test_timeout_and_repeated_start_exclusion(self):
        runner, _ = self.run_script('sleep 20\n', timeout=0.3)
        with self.assertRaises(ValueError):
            runner.start()
        runner.thread.join(8)
        self.assertEqual(runner.state, "cancelled")
        self.assertIsNone(runner.process)
        self.assertFalse(list(runner.runtime.glob("untuya-session-*")))

    def test_hardware_disappearance_stops_run_without_killing_ingress(self):
        from unittest.mock import Mock
        runner, _ = self.run_script('sleep 20\n')
        with patch("runner.same_device", side_effect=wifi.PreflightError("removed")):
            runner.completed = Mock()
            runner.thread.join(5)
            self.assertEqual(runner.state, "failed")
            self.assertFalse(runner.fatal.is_set())
            runner.completed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
