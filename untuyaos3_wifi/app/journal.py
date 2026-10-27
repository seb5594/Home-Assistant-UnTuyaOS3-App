"""Bounded live event history plus persistent, rotating plain-text logs."""
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import re
import sys
import threading
import uuid


class Journal:
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
        formatter.converter = __import__("time").gmtime
        self.disk = RotatingFileHandler(self.data / "app.log", maxBytes=2*1024*1024, backupCount=2,
                                        encoding="utf-8", delay=True)
        for handler in (self.disk, logging.StreamHandler(sys.stdout)):
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _remove_files(self):
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
        with self.lock:
            self.seq += 1
            self.events.append({"id": self.seq, "time": datetime.now(timezone.utc).isoformat(),
                                "level": level, "channel": channel, "text": text})
            self.history_bytes += len(text.encode("utf-8"))
            while (self.history_bytes > 2*1024*1024 or len(self.events) > 4000) and len(self.events) > 1:
                self.history_bytes -= len(self.events.popleft()["text"].encode("utf-8"))
            self.logger.log(getattr(logging, level.upper(), logging.INFO), "[%s] %s", channel, text)

    def snapshot(self, after, generation=None):
        with self.lock:
            if after > self.seq or (generation is not None and generation != self.generation):
                after = 0  # A browser may still carry the cursor from a previous app process.
            first = self.events[0]["id"] if self.events else self.seq + 1
            return {"events": [e for e in self.events if e["id"] > after],
                    "cursor": self.seq, "generation": self.generation, "gap": after > 0 and after < first-1}

    def close(self):
        for handler in self.logger.handlers:
            handler.close()
