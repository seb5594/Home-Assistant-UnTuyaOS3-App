# Generated base module from untuyaos3/app; do not edit.
"""Own one foreground nl80211 supplicant inside the app's isolated namespace."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import threading
import time

from wifi import command, same_device


class Control:
    """Client for wpa_supplicant's control socket (one request, one reply)."""
    def __init__(self, path):
        self.directory = tempfile.TemporaryDirectory(prefix="client-", dir=Path(path).parent)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.settimeout(3)
        try:
            self.socket.bind(str(Path(self.directory.name) / "socket"))
            self.socket.connect(str(path))
        except BaseException:
            self.close()
            raise

    def request(self, message):
        self.socket.send(message.encode("utf-8"))
        return self.socket.recv(65536).decode("utf-8", "replace").strip()

    def close(self):
        """Close the socket and remove its private client directory."""
        self.socket.close()
        self.directory.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Supplicant:
    """One foreground wpa_supplicant bound to the leased adapter, with power-saving handled safely."""
    def __init__(self, adapter, original_power_save, log, cancelled, new_session=True):
        self.adapter, self.original_power_save = adapter, original_power_save
        self.log, self.cancelled = log, cancelled
        self.directory = self.process = self.reader = None
        self.power_changed = False
        self.new_session = new_session

    def start(self):
        """Bring the interface up, launch wpa_supplicant and wait for its control socket. Returns the socket path."""
        same_device(self.adapter)
        command("ip", "link", "set", "dev", self.adapter.name, "up")
        if self.original_power_save == "on":
            # Mark before mutation so even a timeout attempts restoration.
            self.power_changed = True
            command("iw", "dev", self.adapter.name, "set", "power_save", "off")
            self.log("info", f"Temporarily disabled power saving on {self.adapter.name}", "wifi")
        elif self.original_power_save is None:
            self.log("warning", "Power saving unchanged: original state could not be read", "wifi")
        self.directory = tempfile.TemporaryDirectory(prefix="untuya-wpa-", dir="/run")
        root = Path(self.directory.name)
        config = root / "wpa.conf"
        config.write_text(f"ctrl_interface={root}\nupdate_config=0\nap_scan=1\n", encoding="utf-8")
        config.chmod(0o600)
        self.control_path = root / self.adapter.name
        self.process = subprocess.Popen(
            ["wpa_supplicant", "-Dnl80211", "-i", self.adapter.name, "-c", str(config), "-t"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", start_new_session=self.new_session, close_fds=True)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        for _ in range(50):
            if self.cancelled.is_set():
                raise RuntimeError("Session cancelled while preparing Wi-Fi")
            if self.process.poll() is not None:
                raise RuntimeError(f"wpa_supplicant exited during startup ({self.process.returncode})")
            if self.control_path.exists():
                with Control(self.control_path) as control:
                    if control.request("PING") == "PONG":
                        self.log("info", "Private nl80211 supplicant ready; no network configured yet", "wifi")
                        return str(self.control_path)
            time.sleep(0.1)
        raise RuntimeError("wpa_supplicant control socket did not become ready")

    def _read(self):
        for line in self.process.stdout:
            self.log("info", line.rstrip(), "wifi")

    def close(self):
        """Stop the supplicant, remove its files and restore the original power-saving state."""
        try:
            if self.process:
                try:
                    if self.new_session:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    else:
                        self.process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if self.new_session:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    else:
                        self.process.kill()
                    self.process.wait(timeout=3)
                if self.reader:
                    self.reader.join(timeout=2)
                self.process.stdout.close()
        finally:
            if self.directory:
                self.directory.cleanup()
            if self.power_changed:
                same_device(self.adapter)
                command("iw", "dev", self.adapter.name, "set", "power_save", self.original_power_save)
                self.log("info", f"Restored {self.adapter.name} power saving: {self.original_power_save}", "wifi")
