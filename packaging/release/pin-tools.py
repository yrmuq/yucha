#!/usr/bin/env python3
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Refresh the existing Python, Node.js and appimagetool pins within their release lines."""

import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "yucha-pins"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def update(text):
    def replace(key, value):
        nonlocal text
        text, count = re.subn(r"^" + key + r"=.*$", key + '="' + value + '"', text, flags=re.M)
        if count != 1:
            raise ValueError("Missing or duplicate pin: " + key)

    def asset(repository, match):
        release = json.loads(fetch("https://api.github.com/repos/" + repository + "/releases/latest"))
        found = next(item for item in release["assets"] if match(item["name"]))
        url = found["browser_download_url"]
        if not url.startswith("https://github.com/" + repository + "/releases/download/"):
            raise ValueError("Unexpected upstream asset URL")
        return url, hashlib.sha256(fetch(url)).hexdigest()

    url, sha = asset("AppImage/appimagetool", lambda name: name == "appimagetool-x86_64.AppImage")
    replace("TOOL_URL", url)
    replace("TOOL_SHA", sha)
    url, sha = asset("astral-sh/python-build-standalone", lambda name: bool(re.fullmatch(
        r"cpython-3\.12\.\d+\+\w+-x86_64-unknown-linux-gnu-install_only_stripped\.tar\.gz", name)))
    replace("PY_URL", url)
    replace("PY_SHA", sha)
    filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    version = re.search(r"cpython-(3\.12\.\d+)\+", filename)[1]
    replace("PY_TAR", "$CACHE/cpython-" + version + "-install_only_stripped.tar.gz")
    releases = json.loads(fetch("https://nodejs.org/dist/index.json"))
    node = next(item["version"] for item in releases if item["version"].startswith("v24.") and item["lts"])
    dist = "node-" + node + "-linux-x64"
    url = "https://nodejs.org/download/release/" + node + "/" + dist + ".tar.xz"
    sha = next(line.split()[0] for line in fetch(
        "https://nodejs.org/download/release/" + node + "/SHASUMS256.txt").decode().splitlines()
               if line.split()[-1] == dist + ".tar.xz")
    if not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise ValueError("Invalid Node.js checksum")
    replace("NODE_DIST", dist)
    replace("NODE_URL", url)
    replace("NODE_SHA", sha)
    return text


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "appimage/build.sh"
    original = path.read_text()
    changed = update(original)
    if changed == original:
        sys.exit(2)
    path.write_text(changed)
