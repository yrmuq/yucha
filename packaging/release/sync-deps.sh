#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
cd "$(dirname "$0")/../.."
git fetch origin refs/heads/main:refs/remotes/origin/main
if git ls-remote --exit-code origin refs/heads/deps >/dev/null; then
    git fetch origin refs/heads/deps:refs/remotes/origin/deps
    if git merge-base --is-ancestor origin/deps origin/main; then
        git checkout --detach origin/main
        git push origin HEAD:refs/heads/deps
        exit 0
    fi
    git checkout --detach origin/deps
    if ! git merge --no-commit --no-ff origin/main; then
        python3 - <<'MERGE'
import re, subprocess, tempfile
from pathlib import Path
path = "yucha/__init__.py"
conflicts = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], text=True).splitlines()
if conflicts != [path]:
    raise SystemExit("Conflicting dependency changes require manual resolution")
with tempfile.TemporaryDirectory() as folder:
    files = []
    for stage in (2, 1, 3):
        text = subprocess.check_output(["git", "show", f":{stage}:{path}"], text=True)
        # Only the version is exempt from conflict handling; all other code must merge cleanly.
        text, count = re.subn(r'^__version__ = "[0-9.]+"$', '__version__ = "0.0.0"', text, flags=re.M)
        if count != 1:
            raise SystemExit("Missing version line")
        file = Path(folder) / str(stage)
        file.write_text(text)
        files.append(str(file))
    merged = subprocess.run(["git", "merge-file", "-p", *files], stdout=subprocess.PIPE)
    if merged.returncode:
        raise SystemExit("Conflicting changes outside the version line")
    Path(path).write_bytes(merged.stdout)
MERGE
    fi
    version="$(git show origin/main:yucha/__init__.py | sed -n 's/^__version__ = "\([0-9.]*\)"/\1/p')"
    python3 packaging/release/bump.py "$version"
    git add yucha/__init__.py
    if git rev-parse -q --verify MERGE_HEAD >/dev/null; then
        git commit -m "Merge main into deps"
    elif ! git diff --cached --quiet; then
        git commit -m "Sync the main version into deps"
    fi
else
    git checkout --detach origin/main
fi
git push origin HEAD:refs/heads/deps
