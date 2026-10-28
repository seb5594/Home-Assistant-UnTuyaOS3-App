"""Run the one fixed upstream command in a PTY, with live output, a timeout and scoped cleanup.

A session has four phases: bring up the private Wi-Fi controller, start UnTuyaOS3.sh on a
pseudo terminal, pump its output to the journal until it ends (or is cancelled / times out),
and finally undo everything again. The cleanup phase always runs, whatever went wrong.
"""
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
import tempfile
import secrets
from wifi import cleanup, discover, same_device
from supplicant import Supplicant

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
HEALTH_CHECK_SECONDS = 1   # How often the adapter identity is verified while a session runs.
HEARTBEAT_SECONDS = 10     # How often a "still waiting" line is logged.
KILL_GRACE_SECONDS = 5     # Time between SIGTERM and SIGKILL when stopping the script.
TERMINAL_SIZE = (32, 120)  # Rows, columns reported to the script.
# Exit codes of the patched ap-ota.py that mean something other than "failed".
RESULT_BY_EXIT_CODE = {0: "finished", 3: "unconfirmed"}


class Runner:
    """State machine for one UnTuyaOS3 session at a time (see :attr:`state`).

    States: select_adapter -> ready -> assigning -> running -> cleaning -> releasing ->
    finished | unconfirmed | cancelled | failed. The Web UI only reads these names.
    """

    def __init__(self, options, journal, fatal, root="/opt/untuyaos3", runtime="/run"):
        self.options, self.journal, self.fatal = options, journal, fatal
        self.root = Path(root)
        self.runtime = Path(runtime)
        self.lock = threading.RLock()
        self.state, self.exit_code, self.adapter = "starting", None, None
        self.process, self.master, self.thread = None, None, None
        self.cancelled = threading.Event()
        self.completed = None

    def preflight(self):
        """Look up the leased radio inside this app's namespace and mark the runner ready."""
        self.adapter = discover(self.options["interface"], self.journal.emit)
        self.state = "ready"

    def status(self):
        """Snapshot for the Web UI."""
        with self.lock:
            return {"state": self.state, "exit_code": self.exit_code,
                    "adapter": self.adapter.as_dict() if self.adapter else None}

    def start(self):
        """Begin a session in a background thread, after re-checking that the radio is still ours."""
        with self.lock:
            if self.state not in ("ready", "finished", "unconfirmed", "cancelled", "failed") or self.fatal.is_set():
                raise ValueError("A run is already active or the app is shutting down")
            try:
                current = discover(self.options["interface"], self.journal.emit)
                if current.phy != self.adapter.phy:
                    raise RuntimeError("Assigned radio changed; restart both apps")
                self.adapter = current
            except Exception as exc:
                self.state = "failed"
                self.journal.emit("error", f"Preflight failed before starting: {exc}")
                raise ValueError("Wi-Fi preflight failed; release/recovery is required before retrying") from exc
            self.cancelled.clear()
            self.state, self.exit_code = "running", None
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def input(self, choice):
        """Forward a numeric menu choice to the script. Anything but digits is refused."""
        if not isinstance(choice, str) or not re.fullmatch(r"[0-9]{1,5}", choice):
            raise ValueError("Enter the numeric choice requested by UnTuyaOS3")
        with self.lock:
            if self.state != "running" or self.master is None:
                raise ValueError("No interactive run is ready")
            os.write(self.master, (choice + "\n").encode())
            self.journal.emit("info", "Sent numeric menu choice to UnTuyaOS3")

    def cancel(self):
        """Ask the script's process group to stop. Cleanup still runs afterwards."""
        with self.lock:
            self.cancelled.set()
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                self.journal.emit("warning", "Cancellation requested; interrupting flashing can leave a device unusable")

    def _session_environment(self, session_dir, control_path):
        """Environment of the script: only what it needs, plus the identity of the approved radio."""
        env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
        env.update(PYTHONUNBUFFERED="1", TERM="dumb", LC_ALL="C.UTF-8",
                   UNTUYAOS3_SKIP_INSTALL="1", UNTUYAOS3_ALLOWED_IFACE=self.adapter.name,
                   UNTUYAOS3_ALLOWED_PHY=self.adapter.phy, UNTUYAOS3_ALLOWED_IFINDEX=str(self.adapter.ifindex))
        env["UNTUYAOS3_WPA_CONTROL"] = control_path
        env["UNTUYAOS3_RUN_DIR"] = session_dir
        env["UNTUYAOS3_RUN_ID"] = secrets.token_hex(16)
        return env

    def _run(self):
        slave = None
        connection = None
        session = None
        outcome = "cancelled"  # Stays this way if the session is cancelled before the script starts.
        started, heartbeat, health, terminating = time.monotonic(), time.monotonic(), time.monotonic(), None
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            import fcntl
            import struct
            import termios
            session = tempfile.TemporaryDirectory(prefix="untuya-session-", dir=self.runtime)
            connection = Supplicant(self.adapter, self.options.get("original_power_save"),
                                    self.journal.emit, self.cancelled)
            control_path = connection.start()
            self.master, slave = os.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", *TERMINAL_SIZE, 0, 0))
            env = self._session_environment(session.name, control_path)
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
                if now-health >= HEALTH_CHECK_SECONDS:
                    same_device(self.adapter)
                    health = now
                if now-heartbeat >= HEARTBEAT_SECONDS:
                    same_device(self.adapter)
                    if connection.process.poll() is not None:
                        raise RuntimeError("Wi-Fi supplicant stopped unexpectedly; ending this run")
                    self.journal.emit("info", f"Run active for {int(now-started)}s; waiting for menu input, device AP or protocol output")
                    heartbeat = now
                timed_out = now-started > self.options["run_timeout"]
                if (self.cancelled.is_set() or timed_out) and terminating is None:
                    if timed_out:
                        self.journal.emit("error", f"Run timeout reached ({self.options['run_timeout']}s)")
                    self.cancel()
                    terminating = now
                if terminating and now-terminating > KILL_GRACE_SECONDS and self.process.poll() is None:
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
            outcome = "cancelled" if self.cancelled.is_set() else RESULT_BY_EXIT_CODE.get(self.exit_code, "failed")
            self.state = "cleaning"
            self.journal.emit("warning" if outcome == "unconfirmed" else "info" if self.exit_code == 0 else "error",
                              f"UnTuyaOS3 exited with status {self.exit_code}; result={outcome}")
        except Exception as exc:
            outcome = "failed"
            self.state = "cleaning"
            self.journal.emit("error", f"Run failed: {type(exc).__name__}: {exc}")
        finally:
            with self.lock:
                present = True
                try:
                    same_device(self.adapter)
                except Exception:
                    present = False
                    self.journal.emit("error", "Wi-Fi adapter disappeared or was replaced. Run stopped; reconnect it and refresh adapters after recovery")
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
                if connection:
                    try:
                        connection.close()
                    except Exception as exc:
                        self.journal.emit("critical", f"Wi-Fi connection cleanup failed: {exc}")
                        if present:
                            self.fatal.set()
                if present and not cleanup(self.adapter, self.journal.emit):
                    try:
                        same_device(self.adapter)
                    except Exception:
                        self.journal.emit("error", "Adapter vanished during cleanup; keeping recovery diagnostics available")
                    else:
                        self.journal.emit("critical", "Cleanup incomplete; stopping app to release the radio")
                        self.fatal.set()
                if session:
                    try:
                        session.cleanup()
                        self.journal.emit("info", "Removed private session files, including the DHCP-derived OTA target")
                    except OSError as exc:
                        self.journal.emit("critical", f"Session file cleanup failed: {exc}")
                        self.fatal.set()
                self.process = None
                self.state = "releasing"
            if self.completed:
                try:
                    self.completed()
                except Exception as exc:
                    self.journal.emit("error", f"Adapter release pending: {exc}")
            self.state = outcome

    def shutdown(self):
        """Stop a running session and wait briefly for its cleanup."""
        self.cancel()
        if self.thread:
            self.thread.join(timeout=10)
