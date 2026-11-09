# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import json
import sys
import tempfile
import unittest
from http.cookiejar import Cookie
from pathlib import Path
from unittest.mock import patch

from yt_dlp.cookies import YoutubeDLCookieJar
import yt_dlp

from yucha.ytdl import PlaybackYDL, main
from yucha.youtube import cookie_file, save_cookies


class PlaybackCookiesTests(unittest.TestCase):
    def test_cli_entry_preserves_removal_when_the_extractor_finishes(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            cookies = YoutubeDLCookieJar()
            cookies.set_cookie(Cookie(0, "SID", "old-session", None, False, ".youtube.com", True,
                                      True, "/", True, True, None, True, None, None, {}))
            save_cookies(cookies)
            path = cookie_file()
            info = Path(directory) / "info.json"
            info.write_text(json.dumps({"id": "test", "title": "Test", "ext": "mp4",
                                        "url": "https://example.test/video.mp4", "vcodec": "avc1", "acodec": "mp4a"}))
            original = PlaybackYDL.__init__
            called = []

            def initialize(active, *args, **kwargs):
                original(active, *args, **kwargs)
                self.assertEqual(len(active.cookiejar), 1)
                path.unlink()
                called.append(True)

            args = ["yt-dlp", "--ignore-config", "--quiet", "--simulate", "--cookies", str(path),
                    "--load-info-json", str(info)]
            with patch.object(yt_dlp, "YoutubeDL", yt_dlp.YoutubeDL), \
                    patch.object(PlaybackYDL, "__init__", initialize), patch.object(sys, "argv", args):
                with self.assertRaises(SystemExit) as result:
                    main()
                self.assertIn(result.exception.code, (0, None))
            self.assertTrue(called)
            self.assertFalse(path.exists())

    def test_finishing_extractor_cannot_restore_or_overwrite_the_imported_session(self):
        def session(value):
            cookies = YoutubeDLCookieJar()
            cookies.set_cookie(Cookie(0, "SID", value, None, False, ".youtube.com", True,
                                      True, "/", True, True, None, True, None, None, {}))
            return cookies

        for action in ("remove", "replace"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory, \
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
                save_cookies(session("old-session"))
                path = cookie_file()
                with PlaybackYDL({"cookiefile": str(path), "quiet": True}, auto_init=False) as active:
                    self.assertEqual(next(iter(active.cookiejar)).value, "old-session")
                    if action == "remove":
                        path.unlink()
                    else:
                        save_cookies(session("new-session"))
                    self.assertEqual(next(iter(active.cookiejar)).value, "old-session")
                    active.cookiejar.set_cookie(next(iter(session("server-update"))))
                if action == "remove":
                    self.assertFalse(path.exists())
                else:
                    restored = YoutubeDLCookieJar(str(path))
                    restored.load()
                    self.assertEqual(next(iter(restored)).value, "new-session")
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
