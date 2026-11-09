# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from http.cookiejar import Cookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QLocale

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "third_party" / "syncplay"))

from twisted.internet import reactor
from twisted.internet.testing import StringTransport

from syncplay.server import SyncFactory
from yucha.player_ui import PlayerUI, room_file_notes
from yucha.session import RoomClient
from yucha.youtube import (
    audio_tracks, cookie_file, extract_youtube_cookies, playback_options, quality_label,
    quality_tracks, save_cookies, subtitle_tracks, video_url,
)


class YouTubeTests(unittest.TestCase):
    def test_cookie_import_filters_domains_and_saves_a_private_playback_session(self):
        from yt_dlp.cookies import YoutubeDLCookieJar

        source = YoutubeDLCookieJar()
        for domain, expires in ((".youtube.com", None), ("www.youtube.com", time.time() + 3600),
                                (".youtube.com", time.time() - 3600), ("youtube.com.evil.test", None),
                                ("notyoutube.com", None), (".google.com", None)):
            source.set_cookie(Cookie(0, str(expires), "test-session", None, False, domain, True,
                                     domain.startswith("."), "/", True, True, expires, False, None, None, {}))
        with tempfile.TemporaryDirectory(prefix="yucha, cookies=") as home, \
                patch.dict(os.environ, {"XDG_CONFIG_HOME": home}), \
                patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=source) as extract:
            self.assertNotIn("cookies", playback_options())
            cookies = extract_youtube_cookies("firefox", "/test/profile")
            extract.assert_called_once()
            self.assertEqual(extract.call_args.kwargs["profile"], "/test/profile")
            self.assertEqual({cookie.domain for cookie in cookies}, {".youtube.com", "www.youtube.com"})
            self.assertEqual(len(cookies), 2)
            save_cookies(cookies)
            path = cookie_file()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            restored = YoutubeDLCookieJar(str(path))
            restored.load()
            self.assertEqual(len(restored), 2)
            self.assertEqual(playback_options()["cookies"], str(path))
            before = path.read_bytes()
            with patch.object(cookies, "save", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_cookies(cookies)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob(".youtube-cookies-*")), [])
            extract.return_value = YoutubeDLCookieJar()
            with self.assertRaises(ValueError):
                extract_youtube_cookies("firefox")

    def test_quality_choices_start_at_480_and_use_resolution_labels(self):
        tracks = [{"id": height, "type": "video", "demux-h": height}
                  for height in (144, 360, 480, 720, 1080, 1440, 2160)]
        self.assertEqual([quality_label(height) for height, _ in quality_tracks(tracks)],
                         ["4K", "2K", "1080p", "720p", "480p"])

    def test_languages_filter_subtitles_and_choose_best_audio_per_language(self):
        tracks = [
            {"id": 1, "type": "audio", "title": "251 - audio only (Russian, low)", "demux-bitrate": 64000},
            {"id": 2, "type": "audio", "title": "251 - audio only (Russian, medium)", "demux-bitrate": 128000},
            {"id": 3, "type": "audio", "lang": "eng", "demux-bitrate": 192000},
            {"id": 4, "type": "audio", "lang": "en-US", "demux-bitrate": 96000},
            *[{"id": code, "type": "sub", "lang": code} for code in ("ru", "en-US", "de", "rus", "en-orig")],
        ]
        self.assertEqual([(name, track["id"]) for name, track in audio_tracks(tracks)],
                         [("Russian", 2), ("English", 3)])
        with patch("yucha.youtube.QLocale.system", return_value=QLocale("ru_RU")):
            self.assertEqual([track["id"] for track in subtitle_tracks(tracks)], ["ru", "en-US", "rus", "en-orig"])
        with patch("yucha.youtube.QLocale.system", return_value=QLocale("de_DE")):
            self.assertEqual([track["id"] for track in subtitle_tracks(tracks)], ["en-US", "de", "en-orig"])

    def test_clearing_file_publishes_empty_room_file(self):
        client = RoomClient.__new__(RoomClient)
        client.userlist = SimpleNamespace(currentUser=SimpleNamespace(file={"name": "old URL"}))
        client._protocol = Mock(logged=True)
        client.ui = Mock()
        client.clear_file()
        self.assertIsNone(client.userlist.currentUser.file)
        self.assertEqual(client._youtube_info, ("", "", 0))
        client._protocol.sendFileSetting.assert_called_once_with({"name": "", "size": 0, "duration": 0})
        client.ui.userListChange.assert_called_once_with()

    def test_video_identity_rejects_other_hosts_and_collapses_link_variants(self):
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        self.assertEqual(video_url("https://youtu.be/jNQXAC9IVRw?t=30"), url)
        self.assertEqual(video_url("https://www.youtube.com/shorts/jNQXAC9IVRw"), url)
        self.assertEqual(video_url("https://youtube.com.evil.test/watch?v=jNQXAC9IVRw"), "")
        self.assertEqual(video_url("https://www.youtube.com/playlist?list=example"), "")
        people = [{"name": "a", "youtube": url, "height": 720},
                  {"name": "b", "youtube": url, "height": 1080}]
        self.assertEqual(room_file_notes(people), (False, []))

    def test_room_server_preserves_stream_metadata_for_other_clients(self):
        before = set(reactor.getDelayedCalls())

        def cancel_server_timers():
            for call in reactor.getDelayedCalls():
                if call not in before:
                    call.cancel()

        self.addCleanup(cancel_server_timers)
        with redirect_stdout(io.StringIO()):
            server = SyncFactory(salt="test")

        def peer(name):
            protocol = server.buildProtocol(None)
            transport = StringTransport()
            protocol.makeConnection(transport)
            protocol.handleHello({"username": name, "room": {"name": "room"},
                                  "version": "1.7.7", "features": {}})
            return protocol, transport

        first, _ = peer("first")
        second, transport = peer("second")
        transport.clear()
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        client = RoomClient.__new__(RoomClient)
        current = SimpleNamespace(file={"name": url, "size": 0, "duration": 20, "path": url})
        client.userlist = SimpleNamespace(currentUser=current)
        client._protocol = SimpleNamespace(logged=True,
                                           sendFileSetting=lambda file: first.handleSet({"file": file}))
        client.set_youtube_info(url, "A video", 720)
        second.sendList()
        updates = [json.loads(line) for line in transport.value().splitlines()]
        broadcast = updates[0]["Set"]["user"]["first"]["file"]
        listed = updates[-1]["List"]["room"]["first"]["file"]
        self.assertEqual(broadcast, listed)
        self.assertNotIn("path", listed)
        self.assertNotIn("yucha_youtube", current.file)
        watcher = SimpleNamespace(file=listed, room="room", username="first", isReady=lambda: True)
        ui = PlayerUI(Mock())
        ui.addClient(SimpleNamespace(userlist=SimpleNamespace(currentUser=None, _users={"first": watcher})))
        ui.userListChange()
        person = ui.bridge.emit.call_args.args[0]["list"][0]
        self.assertEqual((person["youtube"], person["title"], person["height"]), (url, "A video", 720))
        client.ui = Mock()
        transport.clear()
        client.clear_file()
        second.sendList()
        updates = [json.loads(line) for line in transport.value().splitlines()]
        cleared = {"name": "", "size": 0, "duration": 0}
        self.assertEqual(updates[0]["Set"]["user"]["first"]["file"], cleared)
        self.assertEqual(updates[-1]["List"]["room"]["first"]["file"], cleared)
        watcher.file = cleared
        ui.userListChange()
        person = ui.bridge.emit.call_args.args[0]["list"][0]
        self.assertEqual(person["file"], "")
        self.assertIsNone(person["size"])
        self.assertIsNone(person["duration"])
