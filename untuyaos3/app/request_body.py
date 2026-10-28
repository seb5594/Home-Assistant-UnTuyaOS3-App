"""Bounded HTTP request bodies, including Home Assistant's streamed Ingress POSTs."""
import re

MAX_LINE = 1024
MAX_CHUNK_METADATA = 256 * 1024
MAX_TRAILERS = 8192


class RequestBodyError(ValueError):
    """A request body was malformed or too large; carries the HTTP status to answer with."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def read_body(headers, stream, limit):
    """Return (payload, framing); never read beyond the endpoint's payload limit.

    Reject ambiguous framing. Trailers are bounded and discarded, never merged
    into authentication or firmware headers. The caller closes rejected requests.
    """
    lengths = headers.get_all("Content-Length", [])
    encodings = headers.get_all("Transfer-Encoding", [])
    if encodings:
        if lengths:
            raise RequestBodyError("Content-Length and Transfer-Encoding cannot be combined")
        if len(encodings) != 1 or encodings[0].strip().lower() != "chunked":
            raise RequestBodyError("Only chunked request transfer encoding is supported")
        return _read_chunked(stream, limit), "chunked"
    if not lengths:
        raise RequestBodyError("Content-Length or chunked transfer encoding is required", 411)
    if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
        raise RequestBodyError("Invalid or duplicate Content-Length")
    length = int(lengths[0])
    _check_size(length, limit)
    return _read_exact(stream, length), "content-length"


def _check_size(size, limit):
    if size > limit:
        raise RequestBodyError(f"Request body exceeds {limit} bytes", 413)


def _read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise RequestBodyError("Incomplete request body")
    return data


def _line(stream):
    line = stream.readline(MAX_LINE + 1)
    if len(line) > MAX_LINE or not line.endswith(b"\r\n"):
        raise RequestBodyError("Invalid or incomplete chunk framing")
    return line


def _read_chunked(stream, limit):
    body = bytearray()
    metadata = 0
    while True:
        line = _line(stream)
        metadata += len(line) + 2  # Also account for each chunk's trailing CRLF.
        if metadata > MAX_CHUNK_METADATA:
            raise RequestBodyError("Chunk framing overhead exceeds the request limit")
        size_text = line[:-2].split(b";", 1)[0]
        if not re.fullmatch(rb"[0-9a-fA-F]{1,16}", size_text):
            raise RequestBodyError("Invalid chunk size")
        size = int(size_text, 16)
        _check_size(len(body) + size, limit)
        if size == 0:
            _discard_trailers(stream)
            return bytes(body)
        body.extend(_read_exact(stream, size))
        if _read_exact(stream, 2) != b"\r\n":
            raise RequestBodyError("Invalid chunk terminator")


def _discard_trailers(stream):
    total = 0
    while True:
        line = _line(stream)
        total += len(line)
        if total > MAX_TRAILERS:
            raise RequestBodyError("Request trailers exceed the size limit")
        if line == b"\r\n":
            return
        name, separator, value = line[:-2].partition(b":")
        if not separator or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
            raise RequestBodyError("Invalid request trailer")
        if any(byte < 32 and byte != 9 or byte == 127 for byte in value):
            raise RequestBodyError("Invalid request trailer value")
