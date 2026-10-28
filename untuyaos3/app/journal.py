# Copy of shared/journal.py, maintained by tools/sync_project.py. Edit the original.
"""Bounded live event history plus persistent, rotating plain-text logs.

Every message goes to three places: an in-memory ring buffer that the Web UI polls, a
rotating file under /data/logs and stdout (which Home Assistant shows in the Log tab).
"""
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import re
import sys
import threading
import time
import uuid

LOG_FILE_BYTES = 2 * 1024 * 1024  # Three files of this size are kept (6 MiB per app).
LOG_FILE_BACKUPS = 2
HISTORY_BYTES = 2 * 1024 * 1024   # What a reconnecting browser can replay.
HISTORY_EVENTS = 4000


class Journal:
    """Thread-safe log hub. A new instance starts with fresh log files on purpose."""

    def __init__(self, data):
        self.lock = threading.RLock()
        self.events = deque()
        self.seq = 0
        self.history_bytes = 0
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.generation = uuid.uuid4().hex
        self._remove_files()
        self.logger = logging.Logger("untuyaos3")
        formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
        formatter.converter = time.gmtime
        self.disk = RotatingFileHandler(self.data / "app.log", maxBytes=LOG_FILE_BYTES,
                                        backupCount=LOG_FILE_BACKUPS, encoding="utf-8", delay=True)
        for handler in (self.disk, logging.StreamHandler(sys.stdout)):
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _remove_files(self):
        """Delete only this app's own log files (app.log and its rotations), nothing else."""
        for path in self.data.iterdir():
            if re.fullmatch(r"app\.log(?:\.[0-9]+)?", path.name) and (path.is_file() or path.is_symlink()):
                path.unlink()

    def clear(self):
        """Clear this app's saved and in-memory logs, without resetting event IDs."""
        with self.lock:
            self.disk.acquire()
            try:
                if self.disk.stream:
                    self.disk.flush()
                    self.disk.stream.close()
                    self.disk.stream = None
                self._remove_files()
                self.events.clear()
                self.history_bytes = 0
                self.generation = uuid.uuid4().hex
            finally:
                self.disk.release()
            self.emit("info", "Logs cleared; active session continues")
            return self.generation

    def emit(self, level, text, channel="diagnostic"):
        """Record one message. ``channel`` separates raw terminal output from diagnostics."""
        with self.lock:
            self.seq += 1
            self.events.append({"id": self.seq, "time": datetime.now(timezone.utc).isoformat(),
                                "level": level, "channel": channel, "text": text})
            self.history_bytes += len(text.encode("utf-8"))
            while (self.history_bytes > HISTORY_BYTES or len(self.events) > HISTORY_EVENTS) and len(self.events) > 1:
                self.history_bytes -= len(self.events.popleft()["text"].encode("utf-8"))
            self.logger.log(getattr(logging, level.upper(), logging.INFO), "[%s] %s", channel, text)

    def snapshot(self, after, generation=None):
        """Events newer than the ``after`` cursor, plus what the browser needs to stay in sync."""
        with self.lock:
            if after > self.seq or (generation is not None and generation != self.generation):
                after = 0  # A browser may still carry the cursor from a previous app process.
            first = self.events[0]["id"] if self.events else self.seq + 1
            return {"events": [e for e in self.events if e["id"] > after],
                    "cursor": self.seq, "generation": self.generation, "gap": after > 0 and after < first-1}

    def close(self):
        for handler in self.logger.handlers:
            handler.close()
