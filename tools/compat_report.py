"""Turn device report issues into rows for docs/compatibility.md.

    gh issue list --label compatibility --state all --limit 200 \\
        --json number,title,body,url > issues.json
    python tools/compat_report.py issues.json

The output is a Markdown table you can paste into docs/compatibility.md. The device report
issue form (.github/ISSUE_TEMPLATE/device-report.yml) renders every answer below a
"### <label>" heading; this script reads exactly those headings, so keep the labels in sync.
"""
import json
import re
import sys

COLUMNS = ("Device", "Chip", "Original firmware", "Result", "Wi-Fi adapter")
NO_RESPONSE = "_No response_"


def parse_form(body):
    """{label: answer} from an issue body written by an issue form."""
    answers = {}
    for label, text in re.findall(r"^### (.+?)\s*\n(.*?)(?=^### |\Z)", body or "", re.S | re.M):
        text = text.strip()
        answers[label.strip()] = "" if text == NO_RESPONSE else text
    return answers


def table_row(issue):
    """One Markdown table row for an issue; None if it is not a device report."""
    answers = parse_form(issue.get("body"))
    if "Device" not in answers or "How far did you get?" not in answers:
        return None
    cells = [answers["Device"], answers.get("Chip / platform", ""), answers.get("Original firmware version", ""),
             answers["How far did you get?"], answers.get("Wi-Fi adapter", "")]
    report = f"[#{issue['number']}]({issue['url']})" if issue.get("url") else f"#{issue['number']}"
    return "| " + " | ".join(cell.replace("|", "/").replace("\n", " ") for cell in cells) + f" | {report} |"


def table(issues):
    header = "| " + " | ".join((*COLUMNS, "Report")) + " |\n|" + " --- |" * (len(COLUMNS) + 1)
    rows = [row for issue in sorted(issues, key=lambda item: item["number"]) if (row := table_row(issue))]
    return "\n".join([header, *rows]) + "\n"


def main(arguments):
    if len(arguments) != 1:
        print(__doc__)
        return 2
    with open(arguments[0], encoding="utf-8") as file:
        print(table(json.load(file)), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
