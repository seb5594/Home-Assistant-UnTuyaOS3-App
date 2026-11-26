"""Record the traffic of one leased radio as a classic pcap file, using only the standard library.

A leased radio lives in the client app's own network namespace, so the helper cannot sniff it.
The client therefore records it locally into the shared capture folder; the helper serves the
file over HTTP (see docs/wireshark.md) so Wireshark on another computer can open it live.

The recorder sees what the kernel sees on the interface: decrypted Ethernet frames of the
associated network, not raw 802.11 frames. That is exactly what is needed to analyse the
protocol between a Home Assistant app and a Wi-Fi device. Needs NET_RAW in the client app.
"""
from pathlib import Path
import re
import socket
import struct
import threading
import time

from .protocol import CAPTURE_DIR

ETH_P_ALL = 3
PCAP_MAGIC = 0xA1B2C3D4
LINKTYPE_ETHERNET = 1
DEFAULT_SNAPLEN = 262144
DEFAULT_MAX_BYTES = 128 * 1024 * 1024
FLUSH_INTERVAL = 0.25
KEEP_FILES = 10


def capture_name(label):
    """File name like ``drone-20261126-101500.pcap``; the label is reduced to safe characters."""
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-")[:40] or "capture"
    return f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.pcap"


def prune(directory, keep=KEEP_FILES):
    """Keep only the newest ``keep`` captures so an unattended app cannot fill ``/share``."""
    files = sorted(Path(directory).glob("*.pcap"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def global_header(snaplen=DEFAULT_SNAPLEN):
    return struct.pack("<IHHiIII", PCAP_MAGIC, 2, 4, 0, 0, snaplen, LINKTYPE_ETHERNET)


def packet_record(data, timestamp, snaplen=DEFAULT_SNAPLEN):
    seconds = int(timestamp)
    return struct.pack("<IIII", seconds, int((timestamp - seconds) * 1_000_000), min(len(data), snaplen), len(data)) \
        + data[:snaplen]


class PcapRecorder:
    """Background thread that writes every frame of ``interface`` into a pcap file until stopped."""

    def __init__(self, interface, label="capture", directory=CAPTURE_DIR, max_bytes=DEFAULT_MAX_BYTES):
        self.interface, self.max_bytes = interface, max_bytes
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        prune(self.directory, KEEP_FILES - 1)
        self.path = self.directory / capture_name(label)
        self.packets = 0
        self.error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pcap-recorder", daemon=True)

    def start(self):
        # Open the socket here so a missing NET_RAW or interface surfaces in the caller, not in the thread.
        self._socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        try:
            self._socket.bind((self.interface, 0))
        except OSError:
            self._socket.close()
            raise
        self._socket.settimeout(0.5)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(5)

    def _run(self):
        written = len(global_header())
        last_flush = time.monotonic()
        try:
            with self.path.open("wb") as file, self._socket:
                file.write(global_header())
                while not self._stop.is_set() and written < self.max_bytes:
                    try:
                        data = self._socket.recv(DEFAULT_SNAPLEN)
                    except socket.timeout:
                        data = b""
                    if data:
                        record = packet_record(data, time.time())
                        file.write(record)
                        written += len(record)
                        self.packets += 1
                    if time.monotonic() - last_flush >= FLUSH_INTERVAL:
                        file.flush()  # Lets a live viewer follow the file with at most a short delay.
                        last_flush = time.monotonic()
        except OSError as exc:
            self.error = exc
