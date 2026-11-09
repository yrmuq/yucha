# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reject packaged ELF files that require glibc newer than the supported baseline."""

import re
import os
import subprocess
import sys
from pathlib import Path

MAX_GLIBC = (2, 41, 0)


def required_glibc(output):
    needed = False
    versions = set()
    for line in output.splitlines():
        if line.startswith("Version "):
            needed = line.startswith("Version needs section")
        if needed:
            versions.update(re.findall(r"\bName: GLIBC_(\d+\.\d+(?:\.\d+)?)\b", line))
    return versions


def check(paths):
    seen = set()
    failures = []
    count = 0
    for root in paths:
        if not root.exists():
            raise SystemExit("Missing ABI check input: " + str(root))
        for path in root.rglob("*") if root.is_dir() else (root,):
            if not path.is_file() or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            with path.open("rb") as source:
                if source.read(4) != b"\x7fELF":
                    continue
            count += 1
            output = subprocess.check_output(["readelf", "--version-info", "--wide", str(path)],
                                             text=True, env={**os.environ, "LC_ALL": "C"})
            for version in required_glibc(output):
                parts = tuple(int(value) for value in version.split("."))
                if (parts + (0,) * (3 - len(parts))) > MAX_GLIBC:
                    failures.append("{} requires GLIBC_{}".format(path, version))
    if failures:
        raise SystemExit("glibc 2.41 compatibility check failed:\n" + "\n".join(sorted(failures)))
    if not count:
        raise SystemExit("No ELF files found for the ABI check")
    print("glibc 2.41 compatibility check passed for {} ELF files".format(count))


if __name__ == "__main__":
    check([Path(value) for value in sys.argv[1:]])
