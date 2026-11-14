# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the release version into the program."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_version(version):
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise SystemExit("version is not X.Y.Z")
    init = ROOT / "yucha" / "__init__.py"
    init_text = init.read_text(encoding="utf-8")
    init_new, init_count = re.subn(
        r'(__version__ = ")[0-9]+\.[0-9]+\.[0-9]+(")',
        r"\g<1>" + version + r"\2",
        init_text,
        count=1,
    )
    if init_count != 1:
        raise SystemExit("version line was not found")
    init.write_text(init_new, encoding="utf-8")


def main():
    if len(sys.argv) != 2:
        raise SystemExit(2)
    write_version(sys.argv[1])


if __name__ == "__main__":
    main()
