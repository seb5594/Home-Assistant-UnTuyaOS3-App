"""Follow new releases of the UnTuyaOS3 project this repository packages.

    follow_upstream.py check [--track release|head]
        Compare the pinned revision with the newest upstream release (default) or with the
        head of its default branch. Prints key=value lines and appends them to $GITHUB_OUTPUT:
        update, revision, label, kind, compare_url.

    follow_upstream.py apply --revision SHA --label LABEL [--reason TEXT] [--body-file FILE]
        Pin that revision in project.json, raise the app version by one patch, add a changelog
        entry to the app and regenerate the build contexts. Checks that the reviewed patches
        (untuyaos3/integration/patch_upstream.py) still apply to the new revision and writes a
        pull request description to FILE.

The scheduled workflow .github/workflows/upstream-release.yml runs both steps and opens a
pull request against dev. Nothing is merged or published automatically: the pull request
still needs the privilege review and a hardware test described in CONTRIBUTING.md.
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
CODELOAD = "https://codeload.github.com"
APPS = ("untuyaos3",)
RELEASE_TAG = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
SHA = re.compile(r"[0-9a-f]{40}")


def github(path, token=None):
    """GET a GitHub REST API path and return the decoded JSON."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "untuyaos3-follow-upstream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=30) as reply:
        return json.load(reply)


def newest_release_tag(tags):
    """The highest x.y.z tag as (name, commit sha), or None. Pre-release names are ignored."""
    releases = [(tuple(map(int, match.groups())), tag) for tag in tags if (match := RELEASE_TAG.fullmatch(tag["name"]))]
    if not releases:
        return None
    _, tag = max(releases, key=lambda item: item[0])
    return tag["name"], tag["commit"]["sha"]


def bump_patch(version):
    """1.0.0 -> 1.0.1 and 1.0.0-beta.4 -> 1.0.0-beta.5. Anything else is refused."""
    if match := re.fullmatch(r"(\d+\.\d+\.)(\d+)", version):
        return f"{match[1]}{int(match[2]) + 1}"
    if match := re.fullmatch(r"(\d+\.\d+\.\d+-[a-z]+\.)(\d+)", version):
        return f"{match[1]}{int(match[2]) + 1}"
    raise ValueError(f"Cannot raise version {version!r}")


def check(project, track="release", api=github, token=None):
    """Decide whether upstream moved on. Returns a dict with the outputs described above."""
    repository, pinned = project["upstream_repository"], project["upstream_revision"]
    if track == "release":
        found = newest_release_tag(api(f"/repos/{repository}/tags?per_page=100", token))
        if not found:
            return {"update": "false", "reason": "upstream has no release tags"}
        label, target = found
    else:
        branch = api(f"/repos/{repository}", token)["default_branch"]
        target = api(f"/repos/{repository}/commits/{branch}", token)["sha"]
        label = target[:7]
    if target == pinned:
        return {"update": "false", "reason": f"already pinned to {label}"}
    comparison = api(f"/repos/{repository}/compare/{pinned}...{target}", token)
    if comparison["status"] != "ahead":
        # A release older than the pinned commit (we may track unreleased fixes) is not an update.
        return {"update": "false", "reason": f"{label} is {comparison['status']} relative to the pinned revision"}
    return {"update": "true", "revision": target, "label": label, "kind": track,
            "compare_url": f"https://github.com/{repository}/compare/{pinned[:7]}...{target[:7]}",
            "reason": f"{comparison['ahead_by']} new upstream commit(s) up to {label}"}


def pinned_project_text(text, revision, version):
    """project.json with a new upstream revision and app version; formatting stays untouched."""
    for key, value in (("upstream_revision", revision), ("version", version)):
        text, count = re.subn(rf'("{key}":\s*)"[^"]*"', lambda match: f'{match[1]}"{value}"', text, count=1)
        if count != 1:
            raise ValueError(f"project.json has no {key}")
    return text


def changelog_with_entry(text, version, note):
    """Insert a new top entry below the '# Changelog' heading."""
    heading = "# Changelog\n"
    if not text.startswith(heading):
        raise ValueError("CHANGELOG.md must start with '# Changelog'")
    return f"{heading}\n## {version}\n\n- {note}\n{text[len(heading):]}"


def patches_apply(project, revision, runner=subprocess.run):
    """Download the revision and run the reviewed patches against it. Returns (ok, message)."""
    repository = project["upstream_repository"]
    with urllib.request.urlopen(f"{CODELOAD}/{repository}/tar.gz/{revision}", timeout=120) as reply:
        archive = tarfile.open(fileobj=io.BytesIO(reply.read()), mode="r:gz")
    with tempfile.TemporaryDirectory() as directory:
        # The "data" filter (Python 3.12+) refuses links and paths that escape the directory.
        archive.extractall(directory, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        (source,) = Path(directory).iterdir()
        result = runner([sys.executable, "-I", str(ROOT / "untuyaos3/integration/patch_upstream.py"), str(source)],
                        capture_output=True, text=True)
    return result.returncode == 0, (result.stderr.strip().splitlines() or [""])[-1]


def pull_request_body(project, found, patched, message):
    """Markdown for the pull request: what changed upstream and what a reviewer has to do."""
    patches = "The reviewed patches apply cleanly." if patched else f"**The reviewed patches no longer apply:** {message}"
    return f"""Upstream [{project['upstream_repository']}](https://github.com/{project['upstream_repository']}) has moved on: {found['reason']}.

[Compare the pinned revision with the new one]({found['compare_url']}).

{patches}

## Before merging

- [ ] Read the upstream diff, especially every shell command and network call.
- [ ] Repeat the privilege review from CONTRIBUTING.md if the diff touches networking.
- [ ] Check that CI is green: it builds both images and runs the patched upstream scripts.
- [ ] Test one flash on real hardware, or say in the pull request why that is not needed.

Opened automatically by `tools/follow_upstream.py`; nothing is published until this is merged into `main`.
"""


def apply(root, found, body_file=None):
    """Write the new pin, version and changelog entries, then regenerate the generated files."""
    project_file = root / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    revision, label = found["revision"], found["label"]
    version = bump_patch(project["version"])
    project_file.write_text(pinned_project_text(project_file.read_text(encoding="utf-8"), revision, version),
                            encoding="utf-8", newline="\n")
    note = (f"Update UnTuyaOS3 to {label} (`{revision[:7]}`). "
            f"[Upstream changes]({found['compare_url']}).")
    for app in APPS:
        changelog = root / app / "CHANGELOG.md"
        changelog.write_text(changelog_with_entry(changelog.read_text(encoding="utf-8"), version, note),
                             encoding="utf-8", newline="\n")
    subprocess.run([sys.executable, str(root / "tools/sync_project.py")], check=True)
    patched, message = patches_apply(project, revision)
    if body_file:
        Path(body_file).write_text(pull_request_body(project, found, patched, message), encoding="utf-8")
    return version


def write_outputs(values):
    for key, value in values.items():
        print(f"{key}={value}")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.writelines(f"{key}={value}\n" for key, value in values.items())


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check")
    check_parser.add_argument("--track", choices=("release", "head"), default="release")
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--revision", required=True)
    apply_parser.add_argument("--label", required=True)
    apply_parser.add_argument("--reason", default="")
    apply_parser.add_argument("--body-file")
    options = parser.parse_args(arguments)
    token = os.environ.get("GITHUB_TOKEN")
    project = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
    if options.command == "check":
        write_outputs(check(project, options.track, token=token))
        return 0
    if not SHA.fullmatch(options.revision):
        parser.error("--revision must be a full 40 character commit SHA")
    found = {"revision": options.revision, "label": options.label,
             "compare_url": f"https://github.com/{project['upstream_repository']}/compare/"
                            f"{project['upstream_revision'][:7]}...{options.revision[:7]}",
             "reason": options.reason or f"new upstream revision {options.label}"}
    write_outputs({"version": apply(ROOT, found, options.body_file)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
