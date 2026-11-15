# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from yucha.system import (
    FileBridge,
    SleepInhibit,
    handoff,
    join_line,
    media_paths,
    people_joined,
)


class FakeSleep(object):
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []
        self.held = False

    def acquire(self, app, reason):
        self.calls.append(("acquire", app, reason))
        self.held = bool(self.ok)
        return self.ok

    def release(self):
        self.calls.append(("release",))
        self.held = False


class SystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_appimage_fontconfig_uses_matching_rules_and_discovers_system_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "usr/etc/fonts"
            config.mkdir(parents=True)
            shutil.copy2("/etc/fonts/fonts.conf", config / "fonts.conf")
            shutil.copytree("/etc/fonts/conf.d", config / "conf.d")
            launcher = root / "AppRun"
            shutil.copy2(ROOT / "packaging/appimage/AppRun", launcher)
            launcher.chmod(0o755)
            probe = root / "probe.py"
            probe.write_text("""import ctypes, json, os
class FontSet(ctypes.Structure):
    _fields_ = [('nfont', ctypes.c_int), ('sfont', ctypes.c_int), ('fonts', ctypes.c_void_p)]
fc = ctypes.CDLL('libfontconfig.so.1')
fc.FcInitLoadConfigAndFonts.restype = ctypes.c_void_p
fc.FcConfigGetFonts.argtypes = [ctypes.c_void_p, ctypes.c_int]
fc.FcConfigGetFonts.restype = ctypes.POINTER(FontSet)
config = fc.FcInitLoadConfigAndFonts()
assert config
fc.FcConfigGetFontDirs.argtypes = [ctypes.c_void_p]
fc.FcConfigGetFontDirs.restype = ctypes.c_void_p
fc.FcStrListNext.argtypes = [ctypes.c_void_p]
fc.FcStrListNext.restype = ctypes.c_char_p
directories = fc.FcConfigGetFontDirs(config)
paths = []
while path := fc.FcStrListNext(directories):
    paths.append(path.decode())
print(json.dumps({'file': os.environ['FONTCONFIG_FILE'], 'path': os.environ['FONTCONFIG_PATH'],
                  'fonts': fc.FcConfigGetFonts(config, 0).contents.nfont, 'directories': paths}))
""")
            python = root / "python/bin/python3"
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nif [ "$1" = "-I" ]; then exit 0; fi\nexec ' +
                              shlex.quote(sys.executable) + ' ' + shlex.quote(str(probe)) + '\n')
            python.chmod(0o755)
            environment = {key: value for key, value in os.environ.items()
                           if key not in ("FONTCONFIG_FILE", "FONTCONFIG_PATH", "FC_DEBUG")}
            environment.update(XDG_CACHE_HOME=str(root / "cache"), XDG_CONFIG_HOME=str(root / "config"),
                               XDG_DATA_HOME=str(root / "data"))
            result = subprocess.run([str(launcher)], env=environment, text=True, capture_output=True, check=True)
            found = json.loads(result.stdout)
            self.assertEqual(found["file"], str(config / "fonts.conf"))
            self.assertEqual(found["path"], str(config))
            self.assertGreater(found["fonts"], 0)
            self.assertIn("/usr/share/fonts", found["directories"])
            self.assertIn(str(root / "data/fonts"), found["directories"])
            self.assertNotIn("Fontconfig warning", result.stderr)
            self.assertNotIn("Fontconfig error", result.stderr)

    def test_media_paths(self):
        self.assertEqual(media_paths(["--help", "film.mkv"]), ["film.mkv"])
        self.assertEqual(media_paths(["file:///tmp/a.mkv"]), ["/tmp/a.mkv"])
        self.assertEqual(media_paths(["--", "-odd.mkv"]), ["-odd.mkv"])

    def test_joins_skip_the_room_you_entered(self):
        known, joined = people_joined(None, [], "me")
        self.assertIsNone(known)
        self.assertEqual(joined, [])
        known, joined = people_joined(None, ["me", "ann"], "me")
        self.assertEqual(joined, [])
        known, joined = people_joined(known, ["me", "ann", "bo"], "me")
        self.assertEqual(joined, ["bo"])
        self.assertEqual(join_line(joined), "bo joined")
        self.assertEqual(join_line(["ann", "bo"]), "ann and bo joined")
        self.assertEqual(join_line(["a", "b", "c"]), "3 people joined")

    def test_awake_only_while_playing(self):
        fake = FakeSleep()
        gate = SleepInhibit(fake)
        gate.set_playing(False)
        gate.set_playing(True)
        gate.set_playing(True)
        self.assertEqual(fake.calls, [("acquire", "yucha", "Playing a video")])
        gate.set_playing(False)
        self.assertEqual(fake.calls[-1], ("release",))
        self.assertFalse(fake.held)

    def test_awake_retries_after_a_failed_play(self):
        fake = FakeSleep(ok=False)
        gate = SleepInhibit(fake)
        gate.set_playing(True)
        gate.set_playing(True)
        self.assertEqual(len(fake.calls), 1)
        gate.set_playing(False)
        gate.set_playing(True)
        self.assertEqual(len(fake.calls), 2)

    def test_second_launch_hands_off_the_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sock = Path(tmp.name) / "open.sock"
        got = []
        bridge = FileBridge(sock)
        bridge.opened.connect(lambda paths, token: got.append((paths, token)))
        self.assertTrue(bridge.start())
        self.addCleanup(bridge.stop)
        os.environ["XDG_ACTIVATION_TOKEN"] = "token-1"
        try:
            self.assertTrue(handoff(["/tmp/film.mkv"], sock, "token-1"))
        finally:
            os.environ.pop("XDG_ACTIVATION_TOKEN", None)
        for _ in range(30):
            QCoreApplication.processEvents()
            if got:
                break
            time.sleep(0.02)
        self.assertEqual(got, [(["/tmp/film.mkv"], "token-1")])
        bridge.stop()
        self.assertFalse(handoff(["/tmp/other.mkv"], sock))

    def test_closing_the_window_after_dns_exits_the_process(self):
        script = """
from pathlib import Path
from socket import getaddrinfo
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QWidget
from twisted.internet import threads

from yucha import app


def make_window(_app):
    window = QWidget()
    window.video = Mock()
    window.set_player = Mock()
    window.accept_files = Mock()
    threads.deferToThread(getaddrinfo, "localhost", 8999).addCallback(lambda _: window.close())
    return window


instance = Mock(runtime=Path("."))
with patch.object(app, "App", return_value=instance), patch.object(app, "launch_player"), \\
        patch("yucha.window.MainWindow", make_window), patch("yucha.system.FileBridge"), \\
        patch("yucha.configstore.runtime_dir", return_value=Path(".")):
    app.main()
instance.client.stop.assert_called_once_with(True)
"""
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
