"""Bound framing overhead independently from the decoded payload's size."""
from email.message import Message
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "untuyaos3/app"))
from request_body import RequestBodyError, read_body


class RequestBodyTests(unittest.TestCase):
    def test_excessive_chunk_metadata_is_bounded_even_for_small_payloads(self):
        headers = Message()
        headers["Transfer-Encoding"] = "chunked"
        chunk = b"1;" + b"x" * 1000 + b"\r\n \r\n"
        with self.assertRaisesRegex(RequestBodyError, "framing overhead"):
            read_body(headers, io.BytesIO(chunk * 300 + b"0\r\n\r\n"), 2048)


if __name__ == "__main__":
    unittest.main()
