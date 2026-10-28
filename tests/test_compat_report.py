"""The compatibility table is built from what the device report form writes."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compat_report", ROOT / "tools/compat_report.py")
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

BODY = """### Device

LSC Smart Floor Lamp

### Chip / platform

T1

### Original firmware version

1.2.1

### How far did you get?

Fully worked - new firmware runs and the device is usable

### Milestones you saw

- [x] The device AP was found and joined
- [ ] DHCP worked

### Wi-Fi adapter

Atheros AR9271 (0cf3:9271) | ath9k_htc

### Module name or chip marking (optional)

_No response_
"""


class CompatReportTests(unittest.TestCase):
    def test_answers_are_read_by_their_heading(self):
        answers = compat.parse_form(BODY)
        self.assertEqual(answers["Device"], "LSC Smart Floor Lamp")
        self.assertEqual(answers["Module name or chip marking (optional)"], "")
        self.assertIn("- [x] The device AP", answers["Milestones you saw"])

    def test_row_and_table(self):
        issue = {"number": 7, "url": "https://example.test/7", "body": BODY}
        row = compat.table_row(issue)
        self.assertTrue(row.startswith("| LSC Smart Floor Lamp | T1 | 1.2.1 | Fully worked"))
        self.assertIn("Atheros AR9271 (0cf3:9271) / ath9k_htc", row, "a pipe must not break the table")
        self.assertTrue(row.endswith("| [#7](https://example.test/7) |"))
        self.assertEqual(compat.table([issue]).count("\n"), 3)

    def test_other_issues_are_ignored(self):
        self.assertIsNone(compat.table_row({"number": 1, "body": "Dependency Dashboard"}))
        self.assertIsNone(compat.table_row({"number": 2, "body": None}))

    def test_form_labels_match_the_issue_template(self):
        template = (ROOT / ".github/ISSUE_TEMPLATE/device-report.yml").read_text(encoding="utf-8")
        for label in ("Device", "Chip / platform", "Original firmware version", "How far did you get?", "Wi-Fi adapter"):
            self.assertIn(f"label: {label}", template)


if __name__ == "__main__":
    unittest.main()
