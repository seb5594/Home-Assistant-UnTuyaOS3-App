"""One fixed upstream command in a PTY, with live output, timeout and scoped cleanup."""
import codecs
import errno
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import threading
import time
from wifi import cleanup, discover, same_device

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


class Runner:
    def __init__(self, options, journal, fatal, root="/opt/untuyaos3"):
        self.options, self.journal, self.fatal = options, journal, fatal
        self.root = Path(root)
        self.lock = threading.RLock()
        self.state, self.exit_code, self.adapter = "starting", None, None
        self.process, self.master, self.thread = None, None, None
        self.cancelled = threading.Event()

    def preflight(self):
        self.adapter = discover(self.options["interface"], self.journal.emit)
        self.state = "ready"

    def status(self):
        with self.lock:
            return {"state": self.state, "exit_code": self.exit_code,
                    "adapter": self.adapter.as_dict() if self.adapter else None}

    def start(self):
        with self.lock:
            if self.state not in ("ready", "finished", "cancelled", "failed") or self.fatal.is_set():
                raise ValueError("A run is already active or the app is shutting down")
            try:
                current = discover(self.options["interface"], self.journal.emit)
                if current.phy != self.adapter.phy:
                    raise RuntimeError("Assigned radio changed; restart both apps")
                self.adapter = current
            except Exception as exc:
                self.state = "failed"
                self.journal.emit("critical", f"Preflight failed before starting: {exc}")
                self.fatal.set()
                raise ValueError("Wi-Fi preflight failed; app is stopping") from exc
            self.cancelled.clear()
            self.state, self.exit_code = "running", None
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def input(self, choice):
        if not isinstance(choice, str) or not re.fullmatch(r"[0-9]{1,5}", choice):
            raise ValueError("Enter the numeric choice requested by UnTuyaOS3")
        with self.lock:
            if self.state != "running" or self.master is None:
                raise ValueError("No interactive run is ready")
            os.write(self.master, (choice + "\n").encode())
            self.journal.emit("info", "Sent numeric menu choice to UnTuyaOS3")

    def cancel(self):
        with self.lock:
            self.cancelled.set()
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                self.journal.emit("warning", "Cancellation requested; interrupting flashing can leave a device unusable")

    def _run(self):
        slave = None
        started, heartbeat, terminating = time.monotonic(), time.monotonic(), None
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            import fcntl
            import struct
            import termios
            self.master, slave = os.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 120, 0, 0))
            env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
            env.update(PYTHONUNBUFFERED="1", TERM="dumb", LC_ALL="C.UTF-8",
                       UNTUYAOS3_SKIP_INSTALL="1", UNTUYAOS3_ALLOWED_IFACE=self.adapter.name,
                       UNTUYAOS3_ALLOWED_PHY=self.adapter.phy, UNTUYAOS3_ALLOWED_IFINDEX=str(self.adapter.ifindex))
            args = ["bash", str(self.root / "UnTuyaOS3.sh"), "--verbose", "--interface", self.adapter.name]
            self.journal.emit("info", "Starting pinned UnTuyaOS3.sh with verbose TX/RX logging")
            with self.lock:
                if self.cancelled.is_set():
                    self.state = "cancelled"
                    return
                self.process = subprocess.Popen(args, cwd=self.root, env=env, stdin=slave, stdout=slave,
                                                stderr=slave, start_new_session=True, close_fds=True)
            os.close(slave)
            slave = None
            while True:
                now = time.monotonic()
                if now-heartbeat >= 10:
                    same_device(self.adapter)
                    self.journal.emit("info", f"Run active for {int(now-started)}s; waiting for menu input, device AP or protocol output")
                    heartbeat = now
                timed_out = now-started > self.options["run_timeout"]
                if (self.cancelled.is_set() or timed_out) and terminating is None:
                    if timed_out:
                        self.journal.emit("error", f"Run timeout reached ({self.options['run_timeout']}s)")
                    self.cancel()
                    terminating = now
                if terminating and now-terminating > 5 and self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                readable, _, _ = select.select([self.master], [], [], 0.25)
                if readable:
                    try:
                        raw = os.read(self.master, 8192)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        raw = b""
                    if not raw:
                        break
                    text = ANSI.sub("", decoder.decode(raw)).replace("\r", "")
                    if text:
                        self.journal.emit("info", text, "terminal")
                elif self.process.poll() is not None:
                    break
            self.exit_code = self.process.wait(timeout=5)
            tail = decoder.decode(b"", final=True)
            if tail:
                self.journal.emit("info", tail, "terminal")
            outcome = "cancelled" if self.cancelled.is_set() else ("finished" if self.exit_code == 0 else "failed")
            self.state = "cleaning"
            self.journal.emit("info" if self.exit_code == 0 else "error",
                              f"UnTuyaOS3 exited with status {self.exit_code}; result={outcome}")
        except Exception as exc:
            outcome = "failed"
            self.state = "cleaning"
            self.journal.emit("error", f"Run failed: {type(exc).__name__}: {exc}")
        finally:
            with self.lock:
                if self.process:
                    # Kill any leftover DHCP/scan descendants before restoring the adapter.
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.journal.emit("critical", "Process did not exit after SIGKILL; stopping app for recovery")
                        self.fatal.set()
                if slave is not None:
                    os.close(slave)
                if self.master is not None:
                    os.close(self.master)
                    self.master = None
                if not cleanup(self.adapter, self.journal.emit):
                    self.journal.emit("critical", "Cleanup incomplete; stopping app to release the radio")
                    self.fatal.set()
                self.process = None
                self.state = locals().get("outcome", "cancelled")

    def shutdown(self):
        self.cancel()
        if self.thread:
            self.thread.join(timeout=10)
