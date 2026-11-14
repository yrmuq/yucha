#!/usr/bin/env python3
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the final AppImage/update pair and write or verify release checksums."""

import hashlib
import subprocess
import sys
from pathlib import Path


def digest(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def verify(folder, write=False):
    image = folder / "yucha-x86_64.AppImage"
    zsync = folder / (image.name + ".zsync")
    fields = dict(line.split(": ", 1) for line in zsync.read_bytes().split(b"\n\n", 1)[0].decode().splitlines()
                  if ": " in line)
    if (fields.get("Filename") != image.name or fields.get("URL") != image.name
            or fields.get("Length") != str(image.stat().st_size) or fields.get("SHA-1") != digest(image, "sha1")):
        raise SystemExit("zsync does not match the final AppImage")
    update = subprocess.check_output(["readelf", "-p", ".upd_info", str(image)], text=True)
    expected = "gh-releases-zsync|yrmuq|yucha|latest|" + image.name + ".zsync"
    if expected not in update:
        raise SystemExit("Incorrect AppImage update source")
    files = [image, zsync]
    flatpak = folder / "yucha-x86_64-test.flatpak"
    if flatpak.is_file():
        files.append(flatpak)
    checksums = "".join(digest(path) + "  " + path.name + "\n" for path in files)
    target = folder / "SHA256SUMS"
    if write:
        target.write_text(checksums)
    elif target.read_text() != checksums:
        raise SystemExit("Release checksums do not match")
    print("Verified AppImage update metadata, zsync and release checksums")


if __name__ == "__main__":
    verify(Path(sys.argv[1]), write="--write" in sys.argv[2:])
