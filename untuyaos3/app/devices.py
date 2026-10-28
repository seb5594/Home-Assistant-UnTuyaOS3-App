"""Select host radios through authenticated IPC; acquire one only when a session starts."""
import json
from pathlib import Path
import threading

from lease import Lease, inventory
from protocol import validate_interface


class Devices:
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
        self.runner.state = "select_adapter"
        self.runner.completed = self.finished
        self.preferred = None
        try:
            self.preferred = validate_interface(json.loads((self.data / "selected-adapter.json").read_text())["interface"])
        except (OSError, ValueError, KeyError):
            pass

    def status(self):
        return {"selected_adapter": self.selected, "adapters": self.adapters, "usb_devices": self.usb_devices,
                "adapter_error": self.error, "recovery_pending": self.recovery_pending, "host": self.host, "selection_locked": self.lease is not None,
                "adapter_busy": self.operation.locked()}

    def refresh(self):
        if not self.operation.acquire(blocking=False):
            raise ValueError("An adapter operation is already in progress")
        try:
            result = inventory(self.options)
            self.adapters, self.usb_devices = result["adapters"], result["usb_devices"]
            self.host = result.get("host", {})
            self.recovery_pending = result.get("recovery_pending", "")
            self.error = self.recovery_pending
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
            self.journal.emit("error", f"Adapter discovery failed: {exc}")
            raise
        finally:
            self.operation.release()

    def initialize(self):
        try:
            self.refresh()
        except Exception:
            pass  # Keep Ingress available so the user can start the helper and retry.

    def choose(self, name):
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
        if self.lease:
            self.lease.close()

    def finished(self):
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
