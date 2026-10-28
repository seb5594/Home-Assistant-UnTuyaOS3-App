"""Select host radios through authenticated IPC; acquire one only when a session starts."""
import json
import os
from pathlib import Path
import threading

from lease import Lease, helper_state, inventory
from protocol import APP_VERSION, SOCKET, validate_interface

# Text for the Web UI's helper card, keyed by helper state.
HELPER_MESSAGES = {
    "unknown": "Looking for the Wi-Fi Helper…",
    "ready": "Connected to the Wi-Fi Helper.",
    "unreachable": "The Wi-Fi Helper is not running. Start it from its app page; this page notices it automatically.",
    "not_configured": "No pairing secret is set yet. Generate one below, paste the same value into the Configuration "
                      "tab of both apps and restart both.",
    "pairing": "The helper rejected the pairing secret. Both apps need exactly the same value in their Configuration "
               "tab. Restart both after changing it.",
    "protocol": "The helper speaks a different protocol version. Update both apps to the same release and restart them.",
}
# Runner states in which no session is using (or about to use) the radio.
IDLE_STATES = ("starting", "select_adapter", "ready", "finished", "unconfirmed", "cancelled", "failed")


class Devices:
    """Adapter inventory and selection, plus the lease that is held while a session runs."""

    def __init__(self, options, runner, journal, fatal, data=Path("/data")):
        self.options, self.runner, self.journal, self.fatal = options, runner, journal, fatal
        self.data = Path(data)
        self.operation = threading.Lock()
        self.lease = None
        self.selected = None
        self.adapters, self.usb_devices = [], []
        self.host = {}
        self.recovery_pending = ""
        self.error = ""
        self.helper = {"state": "unknown", "version": None, "message": HELPER_MESSAGES["unknown"]}
        self._attempted_socket = None  # Identity of the helper socket we already tried to talk to.
        self.runner.state = "select_adapter"
        self.runner.completed = self.finished
        self.preferred = None
        try:
            self.preferred = validate_interface(json.loads((self.data / "selected-adapter.json").read_text())["interface"])
        except (OSError, ValueError, KeyError):
            pass

    def status(self):
        return {"selected_adapter": self.selected, "adapters": self.adapters, "usb_devices": self.usb_devices,
                "adapter_error": self.error, "recovery_pending": self.recovery_pending, "host": self.host,
                "selection_locked": self.lease is not None, "adapter_busy": self.operation.locked(),
                "helper": {**self.helper, "expected_version": APP_VERSION}}

    def refresh(self):
        """Ask the helper for adapters and USB devices; auto-select the only eligible one."""
        if not self.operation.acquire(blocking=False):
            raise ValueError("An adapter operation is already in progress")
        try:
            result = inventory(self.options)
            self.adapters, self.usb_devices = result["adapters"], result["usb_devices"]
            self.host = result.get("host", {})
            self.recovery_pending = result.get("recovery_pending", "")
            self.error = self.recovery_pending
            self.helper = self._connected_helper(result.get("helper"))
            if not self.lease:
                eligible = [entry["name"] for entry in self.adapters if entry.get("eligible")]
                self.selected = next((name for name in (self.selected, self.preferred) if name in eligible), None)
                if self.selected is None and len(eligible) == 1:
                    self.selected = eligible[0]
                    self.journal.emit("info", f"Only one eligible Wi-Fi adapter: {self.selected} selected automatically")
                if self.runner.state in ("starting", "select_adapter", "ready"):
                    self.runner.state = "ready" if self.selected else "select_adapter"
                if not eligible and not self.error:
                    self.error = "No free AP-capable adapter is ready. Review adapter and USB diagnostics, then refresh"
            self.journal.emit("info", "Adapter inventory: " + json.dumps(result))
            return self.status()
        except Exception as exc:
            self.error = str(exc)
            self.helper = self._failed_helper(exc)
            self.journal.emit("error", f"Adapter discovery failed: {exc}")
            raise
        finally:
            self.operation.release()

    @staticmethod
    def _connected_helper(info):
        """Helper card data after a successful inventory; a different release is only a soft warning."""
        version = info.get("version") if isinstance(info, dict) else None
        if version and version != APP_VERSION:
            return {"state": "outdated", "version": version,
                    "message": f"Helper {version} and this app {APP_VERSION} differ. "
                               "Update both apps to the same release."}
        return {"state": "ready", "version": version, "message": HELPER_MESSAGES["ready"]}

    @staticmethod
    def _failed_helper(error):
        state = helper_state(error)
        return {"state": state, "version": None, "message": HELPER_MESSAGES.get(state, str(error))}

    def poll_helper(self, socket_path=SOCKET):
        """One watcher tick: connect to a newly started helper, or notice that it went away.

        Only the socket file is inspected here, so a stopped helper costs nothing and the
        logs stay quiet. A stale socket that already failed is not retried until a new
        helper replaces it (different inode or timestamp).
        """
        if self.lease or self.operation.locked() or self.runner.state not in IDLE_STATES:
            return
        try:
            info = os.stat(socket_path)
            stamp = (info.st_ino, info.st_mtime_ns)
        except OSError:
            stamp = None
        connected = self.helper["state"] in ("ready", "outdated")
        if stamp is None:
            self._attempted_socket = None
            if connected:
                self._helper_stopped()
        elif stamp != self._attempted_socket and not connected:
            self._attempted_socket = stamp
            self.initialize()

    def watch_helper(self, stop, interval=3.0):
        """Background loop for :meth:`poll_helper`; ends when ``stop`` is set."""
        while not stop.wait(interval):
            self.poll_helper()

    def _helper_stopped(self):
        if not self.operation.acquire(blocking=False):
            return
        try:
            self.helper = {"state": "unreachable", "version": None, "message": HELPER_MESSAGES["unreachable"]}
            self.adapters, self.usb_devices, self.selected = [], [], None
            self.error = self.helper["message"]
            self.runner.state = "select_adapter"
            self.journal.emit("warning", "Wi-Fi Helper stopped; waiting for it to come back")
        finally:
            self.operation.release()

    def initialize(self):
        try:
            self.refresh()
        except Exception:
            pass  # Keep Ingress available so the user can start the helper and retry.

    def choose(self, name):
        """Remember the user's adapter choice (only eligible adapters, never during a session)."""
        validate_interface(name)
        if not self.operation.acquire(blocking=False):
            raise ValueError("An adapter operation is already in progress")
        try:
            if self.runner.state in ("running", "assigning", "cleaning", "releasing"):
                raise ValueError("Wait until the active session and adapter return have finished")
            if self.lease:
                raise ValueError("Wait for adapter return before choosing another")
            if not any(entry.get("eligible") and entry["name"] == name for entry in self.adapters):
                raise ValueError("That adapter is not eligible. Refresh adapters and review its rejection reason")
            temporary = self.data / "selected-adapter.json.tmp"
            temporary.write_text(json.dumps({"interface": name}))
            temporary.replace(self.data / "selected-adapter.json")
            self.selected = self.preferred = name
            self.runner.state = "ready"
            self.journal.emit("info", f"Selected Wi-Fi adapter: {name}; host state will be checked again before assignment")
        finally:
            self.operation.release()

    def start(self):
        """Lease the selected radio from the helper, then start the session."""
        if not self.operation.acquire(blocking=False):
            raise ValueError("An adapter operation is already in progress")
        release_after_error = False
        try:
            if self.runner.state in ("running", "assigning", "cleaning", "releasing"):
                raise ValueError("A session or adapter operation is already active")
            if not self.selected:
                raise ValueError("Choose an eligible Wi-Fi adapter first")
            if self.recovery_pending:
                raise ValueError("Previous radio recovery is pending. Refresh adapters after reconnecting the device")
            if not self.lease:
                self.runner.state = "assigning"
                try:
                    self.lease = Lease(self.options, self.journal, self.fatal, self.selected)
                except Exception:
                    self.runner.state = "select_adapter"
                    raise
                self.runner.options["interface"] = self.selected
                self.runner.options["original_power_save"] = self.lease.power_save
                try:
                    self.runner.preflight()
                    if self.runner.adapter.phy != self.lease.phy:
                        raise RuntimeError("Assigned physical radio does not match the helper acknowledgement")
                except Exception:
                    self.fatal.set()
                    raise
            try:
                self.runner.start()
            except Exception:
                # A radio can disappear between preflight and process start.
                # Run the same return path after releasing the operation lock.
                release_after_error = True
                raise
        finally:
            self.operation.release()
            if release_after_error:
                self.finished()

    def close(self):
        """Drop the helper connection (the helper then returns the radio by itself)."""
        if self.lease:
            self.lease.close()

    def finished(self):
        """Called after a session: give the radio back and refresh the inventory."""
        with self.operation:
            if self.lease:
                lease, self.lease = self.lease, None
                try:
                    lease.release(self.runner.adapter)
                    self.runner.adapter = None
                except Exception as exc:
                    self.error = "Radio recovery pending: " + str(exc)
                    self.runner.adapter = None
                    self.journal.emit("error", self.error)
        # Keep the UI online, including when USB disappears. The helper keeps
        # durable recovery state and refuses conflicting leases until restored.
        self.initialize()
