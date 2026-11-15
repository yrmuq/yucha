#!/usr/bin/env python3
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Refresh stable assets after automation-only changes without moving the tag."""

import json
import os
import re
import subprocess
from pathlib import Path


def validate(release, version, changed):
    tag = "v" + version
    if (re.fullmatch(r"[0-9]+\.[0-9]+\.0", version) is None
            or release["tag_name"] != tag or release["draft"] or release["prerelease"]):
        raise SystemExit("Only an existing stable release can be refreshed")
    allowed = (".github/", "chit/", "tests/", "packaging/release/")
    if any(path != "README.md" and not path.startswith(allowed) for path in changed):
        raise SystemExit("Application and packaging sources must match the stable tag")
    return tag


def main():
    if os.environ["GITHUB_REF"] != "refs/heads/main":
        raise SystemExit("Stable assets can only be refreshed from main")
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ["GITHUB_SHA"]
    current = subprocess.check_output(
        ["gh", "api", "repos/" + repo + "/git/ref/heads/main", "--jq", ".object.sha"], text=True).strip()
    if current != sha:
        raise SystemExit("The rebuild has been superseded on main")
    version = re.search(r'^__version__ = "([0-9.]+)"',
                        Path("yucha/__init__.py").read_text(), re.MULTILINE).group(1)
    tag = "v" + version
    release = json.loads(subprocess.check_output(
        ["gh", "api", "repos/" + repo + "/releases/tags/" + tag], text=True))
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", tag, sha], text=True).rstrip("\0").split("\0")
    validate(release, version, [path for path in changed if path])
    subprocess.run(["python3", "packaging/appimage/verify.py", "dist"], check=True)
    files = sorted(path for path in Path("dist").iterdir() if path.is_file())
    expected = {"SHA256SUMS", "yucha-x86_64.AppImage", "yucha-x86_64.AppImage.zsync"}
    if {path.name for path in files} != expected or {asset["name"] for asset in release["assets"]} != expected:
        raise SystemExit("The stable AppImage asset set must remain unchanged")
    subprocess.run(["gh", "release", "upload", tag, "--repo", repo, "--clobber",
                    *[str(path) for path in files]], check=True)
    subprocess.run(["python3", "packaging/release/verify-upload.py", tag, "false"], check=True)


if __name__ == "__main__":
    main()
