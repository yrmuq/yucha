#!/usr/bin/env python3
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify GitHub's uploaded asset digests and channel flags against this build."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def verify(tag, draft):
    release = json.loads(subprocess.check_output(
        ["gh", "api", "repos/" + os.environ["GITHUB_REPOSITORY"] + "/releases/tags/" + tag], text=True))
    prerelease = False if draft else int(tag.lstrip("v").split(".")[2]) > 0
    if release["draft"] != draft or release["prerelease"] != prerelease:
        raise SystemExit("Release channel flags do not match")
    if draft and ("Commit: " + os.environ["GITHUB_SHA"]) not in release.get("body", ""):
        raise SystemExit("Draft does not identify this source commit")
    assets = {asset["name"]: asset for asset in release["assets"]}
    files = {path.name: path for path in Path("dist").iterdir() if path.is_file()}
    if set(assets) != set(files):
        raise SystemExit("Published asset set does not match this build")
    for name, path in files.items():
        with path.open("rb") as stream:
            expected = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
        if assets[name].get("digest") != expected or assets[name].get("state") != "uploaded":
            raise SystemExit("Uploaded asset checksum mismatch: " + name)
    print("Verified published channel flags, source metadata and asset digests")


if __name__ == "__main__":
    verify(sys.argv[1], sys.argv[2] == "true")
