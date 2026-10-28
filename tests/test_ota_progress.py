"""Transmission is separate from device confirmation and successful boot."""
import contextlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "untuyaos3/app"))
from ota_progress import TransferProgress


class ProgressTests(unittest.TestCase):
    def test_reported_table_lamp_full_transfer_is_unconfirmed_not_failed(self):
        transfer = TransferProgress(432292)
        for offset in range(0, transfer.total, 1024):
            transfer.record(offset, min(1024, transfer.total-offset))
        self.assertTrue(transfer.complete)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(transfer.incomplete_result(), 3)
        self.assertIn("not confirmed", output.getvalue())
        self.assertIn("Kickstart", output.getvalue())

    def test_duplicates_and_last_block_alone_do_not_imply_complete(self):
        transfer = TransferProgress(100)
        for offset, length in ((90, 10), (0, 10), (0, 10)):
            transfer.record(offset, length)
        self.assertFalse(transfer.complete)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(transfer.incomplete_result(), 1)
        self.assertIn("20/100", output.getvalue())
        transfer.record(10, 80)
        self.assertTrue(transfer.complete)

    def test_invalid_ranges_are_rejected(self):
        transfer = TransferProgress(10)
        for offset, length in ((-1, 1), (0, 0), (9, 2), (10, 1)):
            with self.assertRaises(ValueError):
                transfer.record(offset, length)
