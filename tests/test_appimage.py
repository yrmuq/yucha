# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class AppImageTests(unittest.TestCase):
    def test_launcher_selects_host_vaapi_or_fallback_and_relocates_pipewire(self):
        with tempfile.TemporaryDirectory(prefix="yucha appimage ") as directory:
            root = Path(directory)
            (root / "python/bin").mkdir(parents=True)
            shutil.copy(Path(__file__).resolve().parents[1] / "packaging/appimage/AppRun", root / "AppRun")
            python = root / "python/bin/python3"
            python.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '-c' in sys.argv:
    sys.exit(int(os.environ['TEST_PROBE_EXIT']))
keys = ('LD_LIBRARY_PATH', 'LIBVA_DRIVERS_PATH', 'SPA_PLUGIN_DIR',
        'PIPEWIRE_MODULE_DIR', 'PIPEWIRE_CONFIG_DIR', 'YUCHA_LIBMPV')
Path(os.environ['TEST_RESULT']).write_text(json.dumps({
    'args': sys.argv[1:], 'env': {key: os.environ.get(key) for key in keys}}))
''')
            python.chmod(0o700)
            result = root / "result.json"
            env = {**os.environ, "TEST_RESULT": str(result), "YUCHA_LIBMPV": "",
                   "LD_LIBRARY_PATH": "/existing libraries", "LIBVA_DRIVERS_PATH": "/custom/drivers",
                   "SPA_PLUGIN_DIR": "", "PIPEWIRE_MODULE_DIR": "", "PIPEWIRE_CONFIG_DIR": ""}
            library_dir = str(root / "usr/lib/yucha")
            for probe_exit in (0, 1):
                with self.subTest(probe_exit=probe_exit):
                    env["TEST_PROBE_EXIT"] = str(probe_exit)
                    subprocess.run(["sh", str(root / "AppRun"), "/video with spaces.mkv"], env=env, check=True)
                    data = json.loads(result.read_text())
                    self.assertEqual(data["args"], ["-m", "yucha", "/video with spaces.mkv"])
                    paths = [library_dir, "/existing libraries"]
                    if probe_exit:
                        paths.insert(0, library_dir + "/libva-fallback")
                    self.assertEqual(data["env"]["LD_LIBRARY_PATH"], ":".join(paths))
                    self.assertEqual(data["env"]["YUCHA_LIBMPV"], library_dir + "/libmpv.so.2")
                    self.assertEqual(data["env"]["LIBVA_DRIVERS_PATH"], "/custom/drivers")
                    self.assertEqual(data["env"]["SPA_PLUGIN_DIR"], library_dir + "/spa-0.2")
                    self.assertEqual(data["env"]["PIPEWIRE_MODULE_DIR"], library_dir + "/pipewire-0.3")
                    self.assertEqual(data["env"]["PIPEWIRE_CONFIG_DIR"], str(root / "usr/share/pipewire"))
            overrides = {key: "/custom/" + key for key in
                         ("SPA_PLUGIN_DIR", "PIPEWIRE_MODULE_DIR", "PIPEWIRE_CONFIG_DIR")}
            subprocess.run(["sh", str(root / "AppRun")], env={**env, **overrides}, check=True)
            self.assertTrue(overrides.items() <= json.loads(result.read_text())["env"].items())
