"""Bounded live event history plus persistent, rotating plain-text logs."""
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
import logging
import sys
import threading


class Journal:
    def __init__(self, data):
        self.lock = threading.Lock()
        self.events = deque()
        self.seq = 0
        self.history_bytes = 0
        self.data = Path(data)
        self.data.mkdir(parents=True, exist_ok=True)
        self.logger = logging.Logger("untuyaos3")
        formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
        formatter.converter = __import__("time").gmtime
        disk = RotatingFileHandler(self.data / "app.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
        for handler in (disk, logging.StreamHandler(sys.stdout)):
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def emit(self, level, text, channel="diagnostic"):
        with self.lock:
            self.seq += 1
            self.events.append({"id": self.seq, "time": datetime.now(timezone.utc).isoformat(),
                                "level": level, "channel": channel, "text": text})
            self.history_bytes += len(text.encode("utf-8"))
            while (self.history_bytes > 2*1024*1024 or len(self.events) > 4000) and len(self.events) > 1:
                self.history_bytes -= len(self.events.popleft()["text"].encode("utf-8"))
            self.logger.log(getattr(logging, level.upper(), logging.INFO), "[%s] %s", channel, text)

    def snapshot(self, after):
        with self.lock:
            first = self.events[0]["id"] if self.events else self.seq + 1
            return {"events": [e for e in self.events if e["id"] > after],
                    "cursor": self.seq, "gap": after > 0 and after < first-1}

    def close(self):
        for handler in self.logger.handlers:
            handler.close()
