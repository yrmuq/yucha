# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication

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
        cls._app = QCoreApplication.instance() or QCoreApplication([])

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


if __name__ == "__main__":
    unittest.main()
