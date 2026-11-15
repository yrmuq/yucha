# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging/release" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutomationTests(unittest.TestCase):
    def test_stable_refresh_rejects_runtime_changes_and_nonstable_channels(self):
        rebuild = load("rebuild")
        release = {"tag_name": "v0.11.0", "draft": False, "prerelease": False}
        self.assertEqual(rebuild.validate(release, "0.11.0", [".github/workflows/dev.yml"]), "v0.11.0")
        with self.assertRaisesRegex(SystemExit, "sources must match"):
            rebuild.validate(release, "0.11.0", ["yucha/window.py"])
        for changes in ({"draft": True}, {"prerelease": True}, {"tag_name": "v0.11.1"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(SystemExit, "existing stable"):
                rebuild.validate({**release, **changes}, "0.11.0", [])

    def test_runtime_updater_refreshes_all_pins_with_upstream_checksums(self):
        pins = load("pin-tools")
        payload = b"upstream archive fixture"
        python_name = "cpython-3.12.99+20261114-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
        def fetch(url):
            if url.endswith("/releases/latest"):
                repository = url.split("/repos/", 1)[1].split("/releases/", 1)[0]
                name = "appimagetool-x86_64.AppImage" if repository == "AppImage/appimagetool" else python_name
                return json.dumps({"assets": [{"name": name, "browser_download_url":
                    "https://github.com/" + repository + "/releases/download/test/" + name}]}).encode()
            if url.endswith("index.json"):
                return b'[{"version":"v24.99.0","lts":"test"}]'
            if url.endswith("SHASUMS256.txt"):
                return ("a" * 64 + "  node-v24.99.0-linux-x64.tar.xz\n").encode()
            return payload
        original = (ROOT / "packaging/appimage/build.sh").read_text()
        with patch.object(pins, "fetch", side_effect=fetch):
            updated = pins.update(original)
            self.assertIn('PY_TAR="$CACHE/cpython-3.12.99-install_only_stripped.tar.gz"', updated)
            self.assertIn('NODE_DIST="node-v24.99.0-linux-x64"', updated)
            for key in ("TOOL_SHA", "PY_SHA"):
                self.assertIn(key + '="' + hashlib.sha256(payload).hexdigest() + '"', updated)
            self.assertEqual(pins.update(updated), updated)

    def test_uploaded_assets_must_match_channel_source_and_checksums(self):
        uploaded = load("verify-upload")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "asset"
            path.write_bytes(b"published package")
            release = {"draft": True, "prerelease": False, "body": "Commit: source-sha", "target_commitish": "source-sha", "assets": [
                {"name": path.name, "state": "uploaded", "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}]}
            with patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/project", "GITHUB_SHA": "source-sha"}), \
                    patch.object(Path, "iterdir", return_value=[path]), \
                    patch.object(uploaded.subprocess, "check_output", side_effect=lambda *a, **k: json.dumps(release)) as api:
                uploaded.verify("dev", True)
                self.assertIn("--paginate", api.call_args.args[0])
                self.assertIn("repos/test/project/releases?per_page=100", api.call_args.args[0])
                release["body"] = "Commit: stale-sha"
                with self.assertRaisesRegex(SystemExit, "source commit"):
                    uploaded.verify("dev", True)
                release["body"] = "Commit: source-sha"
                release["assets"][0]["digest"] = "sha256:wrong"
                with self.assertRaisesRegex(SystemExit, "checksum mismatch"):
                    uploaded.verify("dev", True)
