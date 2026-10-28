"""Upstream release tracking: version arithmetic, release detection and the files it rewrites."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("follow_upstream", ROOT / "tools/follow_upstream.py")
follow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(follow)

PINNED = "2" * 40
NEWER = "3" * 40
PROJECT = {"upstream_repository": "owner/upstream", "upstream_revision": PINNED, "version": "1.0.0"}


def fake_api(tags=(), comparison=None, head=NEWER):
    """Stand-in for the GitHub API that answers exactly the three calls follow_upstream makes."""
    def api(path, token=None):
        if "/tags" in path:
            return [{"name": name, "commit": {"sha": sha}} for name, sha in tags]
        if "/compare/" in path:
            return comparison
        if path.endswith("/commits/main"):
            return {"sha": head}
        return {"default_branch": "main"}
    return api


class VersionTests(unittest.TestCase):
    def test_patch_and_prerelease_counters(self):
        self.assertEqual(follow.bump_patch("1.0.0"), "1.0.1")
        self.assertEqual(follow.bump_patch("1.0.9"), "1.0.10")
        self.assertEqual(follow.bump_patch("1.0.0-beta.4"), "1.0.0-beta.5")
        with self.assertRaises(ValueError):
            follow.bump_patch("2026-10-28")

    def test_highest_numeric_release_wins_and_odd_tags_are_ignored(self):
        tags = [{"name": name, "commit": {"sha": name}} for name in ("v1.9.0", "v1.10.0", "v1.10.0-rc1", "nightly", "v1.2")]
        self.assertEqual(follow.newest_release_tag(tags), ("v1.10.0", "v1.10.0"))
        self.assertIsNone(follow.newest_release_tag([{"name": "nightly", "commit": {"sha": "x"}}]))


class CheckTests(unittest.TestCase):
    def test_newer_release_is_an_update(self):
        api = fake_api(tags=[("v1.0.1", PINNED), ("v1.1.0", NEWER)], comparison={"status": "ahead", "ahead_by": 4})
        found = follow.check(PROJECT, "release", api)
        self.assertEqual((found["update"], found["revision"], found["label"]), ("true", NEWER, "v1.1.0"))
        self.assertIn("2222222...3333333", found["compare_url"])

    def test_release_older_than_the_pinned_commit_is_not_an_update(self):
        # A pin can sit on unreleased upstream work; an older tag must never move it backwards.
        api = fake_api(tags=[("v1.0.1", NEWER)], comparison={"status": "behind", "ahead_by": 0})
        self.assertEqual(follow.check(PROJECT, "release", api)["update"], "false")

    def test_pinned_release_and_missing_releases_do_nothing(self):
        self.assertEqual(follow.check(PROJECT, "release", fake_api(tags=[("v1.0.1", PINNED)]))["update"], "false")
        self.assertEqual(follow.check(PROJECT, "release", fake_api())["update"], "false")

    def test_head_tracking_uses_the_default_branch(self):
        api = fake_api(comparison={"status": "ahead", "ahead_by": 2})
        found = follow.check(PROJECT, "head", api)
        self.assertEqual((found["update"], found["revision"], found["label"], found["kind"]), ("true", NEWER, "3333333", "head"))
        self.assertEqual(follow.check(PROJECT, "head", fake_api(head=PINNED))["update"], "false")


class RewriteTests(unittest.TestCase):
    def test_project_json_keeps_its_layout(self):
        text = (ROOT / "project.json").read_text(encoding="utf-8")
        updated = follow.pinned_project_text(text, NEWER, "1.0.1")
        data = json.loads(updated)
        self.assertEqual((data["upstream_revision"], data["version"]), (NEWER, "1.0.1"))
        self.assertEqual(data["protocol"], json.loads(text)["protocol"])
        self.assertEqual(len(updated.splitlines()), len(text.splitlines()))

    def test_changelog_entry_goes_on_top(self):
        text = "# Changelog\n\n## 1.0.0\n\n- First release.\n"
        updated = follow.changelog_with_entry(text, "1.0.1", "Update UnTuyaOS3.")
        self.assertTrue(updated.startswith("# Changelog\n\n## 1.0.1\n\n- Update UnTuyaOS3.\n\n## 1.0.0"))
        with self.assertRaises(ValueError):
            follow.changelog_with_entry("no heading", "1.0.1", "x")

    def test_pull_request_text_tells_the_reviewer_what_to_do(self):
        found = {"reason": "4 new upstream commit(s) up to v1.1.0", "compare_url": "https://example.test/compare"}
        body = follow.pull_request_body(PROJECT, found, False, "Upstream context changed")
        for expected in ("no longer apply", "Upstream context changed", "https://example.test/compare", "hardware"):
            self.assertIn(expected, body)
        self.assertIn("apply cleanly", follow.pull_request_body(PROJECT, found, True, ""))


if __name__ == "__main__":
    unittest.main()
