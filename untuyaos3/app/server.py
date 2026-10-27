"""Ingress-only HTTP UI; fixed upstream command, numeric menu input and live event polling."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import sys
import threading
from urllib.parse import parse_qs, urlsplit
import zipfile

from journal import Journal
from devices import Devices
from protocol import validate_options
from request_body import RequestBodyError, read_body
from runner import Runner

STATIC = Path(__file__).parent / "static"
MAGIC = {"T1": (0, bytes.fromhex("4d4d4d00")), "BK7231N": (0, bytes.fromhex("55aa55aa")),
         "RTL8720CF": (32, bytes.fromhex("68513ef83e396b12ba059a900f36b6d3"))}
MAX_UPLOAD = 32 * 1024 * 1024


def firmware_valid(platform, data):
    offset, magic = MAGIC[platform]
    return data[offset:offset+len(magic)] == magic


def prepare_firmware(root, data):
    source = root / "custom-firmware"
    target = data / "firmware"
    target.mkdir(exist_ok=True)
    if not source.is_symlink():
        for platform in MAGIC:
            destination = target / platform
            destination.mkdir(exist_ok=True)
            for file in (source / platform).glob("*"):
                if file.is_file() and not (destination / file.name).exists():
                    shutil.copyfile(file, destination / file.name)
        shutil.rmtree(source)
        source.symlink_to(target, target_is_directory=True)
    return target


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, runner, journal, firmware, devices=None):
        super().__init__(address, Handler)
        self.runner, self.journal, self.firmware = runner, journal, firmware
        self.devices = devices
        self.csrf = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    server_version = "UnTuyaOS3"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass  # No access logs containing ingress tokens or browser query strings.

    def reply(self, code, body, content_type="application/json"):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def trusted(self):
        # Never trust forwarded addresses or a caller-provided user header.
        if self.client_address[0] != "172.30.32.2":
            self.reply(403, {"error": "Home Assistant Ingress access required"})
            return False
        return True

    def do_GET(self):
        if not self.trusted():
            return
        parsed = urlsplit(self.path)
        if parsed.path in ("/", "/index.html"):
            page = (STATIC / "index.html").read_text(encoding="utf-8").replace("__CSRF__", self.server.csrf)
            page = page.replace("__VERSION__", json.loads(Path(__file__).with_name("build_info.json").read_text())["version"])
            return self.reply(200, page, "text/html; charset=utf-8")
        if parsed.path in ("/app.js", "/style.css"):
            mime = "text/javascript" if parsed.path.endswith(".js") else "text/css"
            return self.reply(200, (STATIC / parsed.path[1:]).read_bytes(), mime + "; charset=utf-8")
        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            try:
                after = max(0, int(query.get("after", ["0"])[0]))
            except (ValueError, IndexError):
                return self.reply(400, {"error": "Invalid cursor"})
            devices = self.server.devices.status() if self.server.devices else {}
            return self.reply(200, {**self.server.journal.snapshot(after, query.get("generation", [None])[0]),
                                   **self.server.runner.status(), **devices})
        if parsed.path == "/api/firmware":
            return self.reply(200, {"files": {platform: sorted(f.name for f in (self.server.firmware / platform).glob("*.bin"))
                                             for platform in MAGIC}})
        if parsed.path == "/api/logs":
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(self.server.journal.data.glob("app.log*")):
                    # Rotation may race a download; collect the files still available.
                    try:
                        archive.writestr(file.name, file.read_bytes())
                    except FileNotFoundError:
                        pass
            return self.reply(200, output.getvalue(), "application/zip")
        self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if not self.trusted():
            return
        if not hmac.compare_digest(self.headers.get("X-CSRF-Token", "").encode("utf-8"), self.server.csrf.encode("utf-8")):
            return self.reply(403, {"error": "Invalid request token; reload the app"})
        path = urlsplit(self.path).path
        if path not in ("/api/start", "/api/input", "/api/cancel", "/api/firmware", "/api/logs/clear", "/api/adapters/refresh", "/api/adapters/select"):
            return self.reply(404, {"error": "Not found"})
        try:
            limit = MAX_UPLOAD if path == "/api/firmware" else 2048
            body, framing = read_body(self.headers, self.rfile, limit)
            self.server.journal.emit("info", f"UI request {path}: {len(body)} bytes received via {framing}")
            if path == "/api/firmware":
                return self.upload(body)
            request = json.loads(body)
            if not isinstance(request, dict):
                raise ValueError("Expected a JSON object")
            if path == "/api/start":
                (self.server.devices or self.server.runner).start()
            elif path == "/api/input":
                self.server.runner.input(request.get("choice"))
            elif path == "/api/cancel":
                self.server.runner.cancel()
            elif path == "/api/logs/clear":
                return self.reply(200, {"ok": True, "generation": self.server.journal.clear()})
            elif path in ("/api/adapters/refresh", "/api/adapters/select"):
                if self.server.devices is None:
                    raise ValueError("Adapter discovery is not available")
                if path.endswith("refresh"):
                    self.server.devices.refresh()
                else:
                    self.server.devices.choose(request.get("interface"))
            self.reply(200, {"ok": True})
        except RequestBodyError as exc:
            self.close_connection = True
            self.server.journal.emit("warning", f"UI request {path} rejected (HTTP {exc.status}): {exc}")
            self.reply(exc.status, {"error": str(exc)})
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            self.server.journal.emit("warning", f"UI operation failed: {type(exc).__name__}: {exc}")
            self.reply(400, {"error": str(exc)})

    def upload(self, data):
        import re
        platform = self.headers.get("X-Firmware-Platform", "")
        name = self.headers.get("X-Firmware-Name", "")
        if platform not in MAGIC or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.bin", name):
            raise ValueError("Choose a platform and a .bin filename using letters, digits, dots, hyphens or underscores")
        if not firmware_valid(platform, data):
            raise ValueError("Firmware signature does not match the selected platform (UG image required)")
        with self.server.runner.lock:
            if self.server.runner.state == "running":
                raise ValueError("Wait for the active run to finish before uploading firmware")
            folder = self.server.firmware / platform
            if len(list(folder.glob("*.bin"))) >= 30:
                raise ValueError("Firmware limit reached (30 per platform)")
            target = folder / name
            if target.exists():
                raise ValueError("That filename already exists; use a new name")
            with target.open("xb") as file:
                file.write(data)
            self.server.journal.emit("info", f"Stored firmware: {platform}/{name} ({len(data)} bytes; UG signature checked)")
        self.reply(201, {"ok": True})


def main():
    data, root = Path("/data"), Path("/opt/untuyaos3")
    journal = Journal(data / "logs")
    fatal = threading.Event()
    runner, devices, server = None, None, None
    requested_stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: requested_stop.set())
    try:
        options = json.loads((data / "options.json").read_text())
        validate_options(options)
        timeout = options.get("run_timeout", 1800)
        if type(timeout) is not int or not 60 <= timeout <= 7200:
            raise ValueError("run_timeout must be 60..7200 seconds")
        options["run_timeout"] = timeout
        journal.emit("info", "App starting with fresh logs; select Wi-Fi in the Web UI; isolated network; no host API access")
        journal.emit("info", "Pinned upstream revision: " + (root / "UPSTREAM_COMMIT").read_text().strip())
        firmware = prepare_firmware(root, data)
        runner = Runner(options, journal, fatal, root)
        devices = Devices(options, runner, journal, fatal, data)
        server = Server(("0.0.0.0", 8099), runner, journal, firmware, devices)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threading.Thread(target=devices.initialize, daemon=True).start()
        journal.emit("info", "Ingress ready. Open Web UI to select or refresh adapters, then start a session")
        while not requested_stop.wait(0.25):
            if fatal.is_set():
                raise RuntimeError("Fatal adapter/lease error; app must stop")
        journal.emit("info", "Home Assistant requested app shutdown")
        result = 0
    except Exception as exc:
        journal.emit("critical", f"Startup/runtime failure: {type(exc).__name__}: {exc}")
        journal.emit("critical", "App stopping. Diagnostics remain in Home Assistant app logs and persistent /data/logs.")
        result = 1
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if runner:
            runner.shutdown()
        if devices:
            devices.close()
        journal.close()
    return result


if __name__ == "__main__":
    sys.exit(main())
