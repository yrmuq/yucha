# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the real Qt controls without an mpv engine or a room server."""

import copy
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from http.cookiejar import Cookie
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "syncplay"))

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QKeyEvent, QMouseEvent, QPainter, QPalette, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import (
    QApplication, QDialog, QFormLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QScrollBar, QStyle, QStyleOptionSlider, QWidget,
)

from syncplay.messages import getMessage
from yucha.app import App
from yucha.bridge import Bridge
from yucha.player_ui import PlayerUI
from yucha.configstore import DEFAULTS, ConfigStore
from yucha import __version__, i18n
from yucha.i18n import system_language
from yucha.window import EdgeScroll, MainWindow, SettingsDialog, YouTubeConnect, _palette
from yucha.youtube import cookie_file


class PictureStub(QWidget):
    fullscreenRequested = Signal()
    volumeChanged = Signal(int)
    arrowPressed = Signal(int)
    filesDropped = Signal(list)
    enterPressed = Signal()

    def __init__(self, runtime):
        super().__init__()
        self.error = None
        self.mpv = None
        self.redraw = Mock()
        self.shutdown = Mock()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


class Control:
    def __init__(self):
        self.properties = {
            "path": "/tmp/video.mkv", "pause": False, "duration": 120,
            "time-pos": 30, "volume": 80, "volume-max": 130,
            "track-list": [{"id": 1, "type": "sub", "title": "Subtitles"},
                           {"id": 2, "type": "audio", "title": "Audio"}],
        }
        self.calls = []

    def command(self, *args):
        self.calls.append(args)
        if args[0] == "get_property":
            return self.properties.get(args[1])
        if args[0] == "set_property":
            value = args[2]
            if args[1] == "pause":
                value = value in (True, "yes")
            self.properties[args[1]] = value
        elif args[:2] == ("cycle", "pause"):
            self.properties["pause"] = not self.properties["pause"]


class VisibilityEvents(QObject):
    def __init__(self):
        super().__init__()
        self.events = []

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            self.events.append((watched, event.type()))
        return False


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp.name})
        self.env.start()
        self.patches = [patch("yucha.window.Picture", PictureStub),
                        patch("yucha.window.detected_browsers", return_value=[
                            ("Firefox", "firefox", "/test/firefox"), ("Chromium", "chromium", "/test/chromium")]),
                        patch("yucha.window.Notifier"), patch("yucha.window.SleepInhibit"),
                        patch("yucha.window.SettingsDialog._check_release"),
                        patch("yucha.window.MainWindow._begin_release_check")]
        for item in self.patches:
            item.start()
        self.store = ConfigStore()
        self.store.data["appearance"].update({"checkUpdates": False, "theme": "dark",
                                              "volumeMax": 130, "devTab": True})
        self.store.data["connection"].update({"host": "example.test", "name": "me", "room": "room"})
        self.app = SimpleNamespace(store=self.store, runtime=Path(self.temp.name),
                                   bridge=Mock(), client=SimpleNamespace(_config={}))
        self.app.bridge.read_new.return_value = ([], 0)
        self.app.on_command = lambda command: App.on_command(self.app, command)
        self.windows = []
        self.window = self.make_window()

    def make_window(self):
        window = MainWindow(self.app)
        self.windows.append(window)
        window._ui_timer.stop()
        window._knob_timer.stop()
        window.ctl = Control()
        window._playlist = [{"path": "/tmp/video.mkv", "name": "video.mkv"}]
        window._current_path = "/tmp/video.mkv"
        window._connected = True
        window._paused = False
        window._refresh_files()
        window.show()
        window.set_panel(False)
        window._refresh_transport()
        self.qt.processEvents()
        window._place_overlays()
        self.qt.processEvents()
        return window

    def tearDown(self):
        for window in self.windows:
            self.qt.removeEventFilter(window)
            window.hide()
            window.deleteLater()
        self.qt.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for item in reversed(self.patches):
            item.stop()
        self.env.stop()
        self.temp.cleanup()

    def dialog(self):
        return SettingsDialog(self.store.data["appearance"], self.store.data["connection"], self.window)

    def click_at(self, widget, point):
        global_point = widget.mapToGlobal(point)
        target = self.window.childAt(self.window.mapFromGlobal(global_point))
        self.assertIsNotNone(target)
        QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.mapFromGlobal(global_point))
        self.qt.processEvents()

    def drag(self, widget, point, delta):
        destination = widget.mapToGlobal(point) + delta
        QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=point)
        self.qt.sendEvent(widget, QMouseEvent(QEvent.Type.MouseMove,
            QPointF(widget.mapFromGlobal(destination)), QPointF(destination),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.qt.sendEvent(widget, QMouseEvent(QEvent.Type.MouseButtonRelease,
            QPointF(widget.mapFromGlobal(destination)), QPointF(destination),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.qt.processEvents()

    def test_room_imports_and_removes_youtube_cookies_without_restarting_the_player(self):
        from yt_dlp.cookies import YoutubeDLCookieJar

        cookies = YoutubeDLCookieJar()
        for name in ("LOGIN_INFO", "SAPISID"):
            cookies.set_cookie(Cookie(0, name, "test-session", None, False, ".youtube.com", True,
                                      True, "/", True, True, None, True, None, None, {}))
        settings = self.dialog()
        settings.show()
        self.qt.processEvents()
        self.assertFalse(settings.youtube_connect.isVisible())
        size = settings.size()
        settings.tabs.setCurrentIndex(0)
        self.qt.processEvents()
        self.assertTrue(settings.youtube_connect.isVisible())
        self.assertEqual(settings.size(), size)
        area = settings.tabs.currentWidget().findChild(QScrollArea)
        self.assertTrue(area.widget().isAncestorOf(settings.youtube_connect))
        position = settings.youtube_connect.mapTo(area.viewport(), QPoint())
        self.assertTrue(area.viewport().rect().contains(position))
        self.assertTrue(area.viewport().rect().contains(position + QPoint(
            settings.youtube_connect.width() - 1, settings.youtube_connect.height() - 1)))
        ok = next(button for button in settings.findChildren(QPushButton) if button.text() == i18n.tr(43))
        bottom = settings.youtube_connect.mapTo(settings, QPoint(0, settings.youtube_connect.height())).y()
        self.assertLess(bottom, ok.mapTo(settings, QPoint()).y())

        def finish_import(dialog):
            dialog.start.click()
            self.assertFalse(dialog.start.isEnabled())
            for _ in range(100):
                self.qt.processEvents()
                if dialog.start.isEnabled():
                    break
                QTest.qWait(10)
            self.assertTrue(dialog.start.isEnabled())

        def interact(dialog):
            dialog.show()
            self.assertEqual(dialog.browser.currentData(), "firefox")
            self.assertGreater(dialog.browser.count(), 1)
            finish_import(dialog)
            self.assertEqual(dialog.status.text(), i18n.tr(131))
            extract.assert_called_once_with("firefox", "/test/firefox")
            self.assertTrue(cookie_file().is_file())
            self.assertEqual(self.window.ctl.properties["ytdl-raw-options"]["cookies"], str(cookie_file()))
            dialog.remove.click()
            self.assertFalse(cookie_file().exists())
            self.assertNotIn("cookies", self.window.ctl.properties["ytdl-raw-options"])
            extract.side_effect = FileNotFoundError("test profile missing")
            finish_import(dialog)
            self.assertEqual(dialog.status.text(), i18n.tr(139))
            self.assertFalse(cookie_file().exists())
            dialog.reject()
            dialog._import_done(cookies, 0)
            self.assertFalse(cookie_file().exists(), "A closed import dialog saved a session")

        try:
            with patch("yucha.window.extract_youtube_cookies", return_value=cookies) as extract, \
                    patch.object(YouTubeConnect, "exec", new=interact):
                settings._connect_youtube()
        finally:
            settings.reject()
            settings.deleteLater()

    def test_space_pauses_once_when_ready_and_playing(self):
        self.window.ready.setChecked(True)
        self.window.video.setFocus()
        self.qt.processEvents()
        self.window._toggle_ready = Mock()
        QTest.keyClick(self.window.video, Qt.Key.Key_Space)
        self.assertTrue(self.window.ctl.properties["pause"])
        self.assertEqual(self.window.ctl.calls.count(("cycle", "pause")), 1)
        self.window._toggle_ready.assert_not_called()

    def test_youtube_link_queues_and_quality_switches_without_reloading(self):
        window = self.window
        window.set_panel(True)
        self.assertEqual(window.link_add.x() - window.files_add.x(), 24)
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

        def enter_link():
            dialog = QApplication.activeModalWidget()
            buttons = dialog.findChildren(QPushButton)
            self.assertEqual(len(buttons), 2)
            self.assertLessEqual(abs(buttons[0].width() - buttons[1].width()), 1)
            self.assertLess(buttons[0].x(), buttons[1].x())
            self.assertTrue(all(button.icon().isNull() for button in buttons))
            field = dialog.findChild(QLineEdit)
            field.setText("https://youtu.be/jNQXAC9IVRw?si=example")
            QTest.keyClick(field, Qt.Key.Key_Return)

        with patch.object(window, "_fetch_youtube_title") as fetch:
            QTimer.singleShot(0, enter_link)
            window.link_add.click()
        fetch.assert_called_once_with(url)
        self.assertEqual(window._current_path, "/tmp/video.mkv")
        self.assertEqual(window._playlist[-1]["path"], url)
        self.assertTrue(window.quality_btn.isHidden())

        window._play_path(url)
        window.ctl.properties.update({
            "path": url, "media-title": "YouTube title", "video-params/h": 1080,
            "pause": True, "time-pos": 24,
            "track-list": [
                {"id": 1, "type": "video", "demux-h": 1080, "selected": True},
                {"id": 2, "type": "video", "demux-h": 720},
                {"id": 3, "type": "video", "demux-h": 720},
                {"id": 4, "type": "audio", "title": "English"},
                {"id": 5, "type": "audio", "title": "Russian"},
                {"id": 6, "type": "sub", "lang": "en"},
            ],
        })
        window._users = [{"name": "me", "file": url, "size": 0, "ready": True}]
        window._refresh_transport()
        self.assertEqual(window._playlist[-1]["name"], "YouTube title")
        self.assertEqual(window.room_users.sizes_col.itemAt(0).widget().text(), "1080p")
        self.assertFalse(window.quality_btn.isHidden())
        window.quality_btn.click()
        buttons = window.quality_pop.findChildren(QPushButton)
        self.assertEqual([button.text() for button in buttons], ["1080p", "720p"])
        window.ctl.calls.clear()
        buttons[1].click()
        self.assertEqual([call for call in window.ctl.calls if call[0] != "get_property"],
                         [("set_property", "vid", 2)])
        self.assertEqual(window.ctl.properties["time-pos"], 24)
        self.assertTrue(window.ctl.properties["pause"])
        self.assertFalse(window._quality_open)
        self.assertTrue(window.quality_pop.isHidden())
        self.assertFalse(window.quality_btn.isChecked())
        window.tracks_btn.click()
        self.assertTrue(window._tracks_open)
        self.assertFalse(window._quality_open)

    def test_youtube_track_menus_and_best_audio_follow_language(self):
        from PySide6.QtCore import QLocale
        window = self.window
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        window._current_path = url
        window._playlist = [{"path": url, "name": url}]
        window.ctl.properties.update({"path": url, "track-list": [
            {"id": 1, "type": "audio", "lang": "en", "demux-bitrate": 64000, "selected": True},
            {"id": 2, "type": "audio", "lang": "eng", "demux-bitrate": 192000},
            {"id": 3, "type": "audio", "lang": "ru", "demux-bitrate": 128000},
            {"id": 4, "type": "sub", "lang": "ru"},
            {"id": 5, "type": "sub", "lang": "en"},
            {"id": 6, "type": "sub", "lang": "de"},
            {"id": 7, "type": "video", "demux-h": 1440, "selected": True},
        ]})
        window._refresh_transport()
        self.assertEqual(window.quality_btn._quality, "2K")
        window.quality_btn.set_quality(1080)
        font = QFont(window.quality_btn.font())
        font.setPixelSize(18)
        font.setBold(False)
        self.assertGreaterEqual(window.quality_btn.width(), QFontMetrics(font).horizontalAdvance("1080p") + 12)
        self.assertIn(("set_property", "aid", 2), window.ctl.calls)
        with patch("yucha.youtube.QLocale.system", return_value=QLocale("ru_RU")):
            window._fill_tracks()
        buttons = window.tracks_pop.findChildren(QPushButton)
        self.assertEqual([button.text() for button in buttons][-2:], ["English", "Russian"])
        self.assertEqual(len(buttons), 5)
        buttons[-1].click()
        self.assertEqual(window.ctl.properties["aid"], 3)

    def test_youtube_title_reaches_users_before_play_and_when_switching(self):
        window = self.window
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        window._playlist = []
        window._users = [{"name": "me", "file": url, "ready": True}]
        self.app.client.set_youtube_info = Mock()
        reply = Mock()
        reply.error.return_value = QNetworkReply.NetworkError.NoError
        reply.read.return_value = b'{"title":"Title before play"}'
        with patch.object(window, "_fetch_youtube_title"), patch(
                "twisted.internet.reactor.callFromThread", side_effect=lambda fn, *args: fn(*args)):
            window._add_dropped([url])
            window.ctl.properties.update({"path": url, "media-title": "jNQXAC9IVRw", "pause": True})
            window._youtube_title_received(url, reply)
            window._refresh_transport()
            self.assertEqual(window.room_users.files_col.itemAt(0).widget().text(), "Title before play")
            self.app.client.set_youtube_info.assert_called_with(url, "Title before play", 0)
            self.assertTrue(window.ctl.properties["pause"])
            next_url = "https://www.youtube.com/watch?v=2iAkQCsSctc"
            window._playlist.append({"path": next_url, "name": "Queued title"})
            window.ctl.properties["media-title"] = "Old engine title"
            window._play_path(next_url)
            window._refresh_transport()
            self.assertEqual(window._stream, (next_url, "Queued title", 0))
            self.app.client.set_youtube_info.assert_called_with(next_url, "Queued title", 0)
        reply.deleteLater.assert_called_once_with()

    def test_youtube_title_auth_error_does_not_interrupt_playback(self):
        window = self.window
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        window._playlist = [{"path": url, "name": url}]
        window._current_path = url
        window.ctl.properties.update({"path": url, "media-title": "Stream title"})
        reply = Mock()
        reply.error.return_value = QNetworkReply.NetworkError.AuthenticationRequiredError
        window._title_requests[url] = reply
        window._youtube_title_received(url, reply)
        window._refresh_youtube(url)
        self.assertEqual(window._playlist[0]["name"], "Stream title")
        self.assertFalse(window.ctl.properties["pause"])
        self.assertFalse([call for call in window.ctl.calls if call[0] in ("stop", "loadfile", "set_property")])
        self.assertNotIn(url, window._title_requests)
        reply.read.assert_not_called()
        reply.deleteLater.assert_called_once_with()

    def test_chapter_markers_toggle_and_removed_youtube_does_not_return(self):
        window = self.window
        window.ctl.properties["chapter-list"] = [{"time": 0}, {"time": 30}]
        window._refresh_transport()
        self.assertEqual(window.slider._chapters, [])
        window.apply_dev({"chapters": True})
        self.assertEqual(window.slider._chapters, [0, 30])
        window.apply_dev({})
        self.assertEqual(window.slider._chapters, [])
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        window._current_path = url
        window._hold_pause = url
        window._playlist = [{"path": url, "name": url}]
        window._stream = (url, "Title", 720)
        window._users = [{"name": "me", "file": url, "youtube": url, "ready": True}]
        window.ctl.properties["path"] = url
        self.app.client.clear_file = Mock()
        with patch("twisted.internet.reactor.callFromThread", side_effect=lambda fn, *args: fn(*args)):
            window._remove_file(url)
        self.app.client.clear_file.assert_called_once_with()
        self.assertEqual(window._users[0]["file"], "")
        self.assertIsNone(window._hold_pause)
        window._refresh_transport()
        self.assertEqual(window._stream, ("", "", 0))
        self.assertTrue(window.quality_btn.isHidden())

    def test_future_scroll_areas_get_external_chat_style_bars(self):
        area = QScrollArea(self.window.stage)
        area.setGeometry(30, 30, 150, 80)
        body = QWidget()
        body.setFixedSize(120, 800)
        area.setWidget(body)
        area.show()
        self.qt.processEvents()
        manager = self.qt._scroll_edges
        bars = manager._areas[area]
        bar = next(bar for bar in bars if bar.orientation() == Qt.Orientation.Vertical)
        self.assertEqual(area.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.verticalScrollBar().setValue(20)
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.width(), 3)
        self.assertEqual(bar.x(), area.geometry().right() + 2)
        self.assertEqual(bar.objectName(), self.window.chat_scroll.objectName())
        area.move(60, 40)
        self.assertEqual(bar.x(), area.geometry().right() + 2)
        area.hide()
        self.assertTrue(bar.isHidden())
        area.deleteLater()
        self.qt.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertNotIn(area, manager._areas)

    def test_long_scrollbar_thumb_is_capped_without_changing_page_scroll(self):
        native = QScrollBar(Qt.Orientation.Vertical, self.window)
        native.setRange(0, 4000)
        native.setPageStep(600)
        bar = EdgeScroll(Qt.Orientation.Vertical, self.window)
        bar.setGeometry(5, 5, 3, 600)
        bar.attach(native)
        bar.show()
        self.qt.processEvents()
        for length in (600, 900):
            bar.resize(3, length)
            option = QStyleOptionSlider()
            bar.initStyleOption(option)
            thumb = bar.style().subControlRect(QStyle.ComplexControl.CC_ScrollBar, option,
                                               QStyle.SubControl.SC_ScrollBarSlider, bar)
            self.assertGreaterEqual(thumb.height(), 18)
            self.assertLessEqual(thumb.height(), 64)
        bar.triggerAction(bar.SliderAction.SliderPageStepAdd)
        self.assertEqual(native.value(), 600)
        self.assertEqual(bar.value(), 600)
        bar.setValue(bar.maximum())
        self.assertEqual(native.value(), 4000)

    def test_settings_wheel_scrolls_page_without_changing_fields(self):
        dialog = self.dialog()
        dialog.show()
        dialog._open_dev()
        self.qt.processEvents()
        combo = dialog._dev_rows["ui"]["family"]
        area = combo.parentWidget()
        while not isinstance(area, QScrollArea):
            area = area.parentWidget()
        bar = area.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        original = combo.currentIndex()
        event = QWheelEvent(QPointF(combo.rect().center()), QPointF(combo.mapToGlobal(combo.rect().center())),
                            QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(combo, event)
        self.assertEqual(combo.currentIndex(), original)
        self.assertGreater(bar.value(), 0)
        dialog.reject()

    def test_external_track_scrollbar_keeps_popup_open_and_scrolls(self):
        window = self.window
        window.set_panel(True)
        window.ctl.properties["track-list"] = [
            {"id": i, "type": "sub", "lang": "en", "title": "English " + str(i)} for i in range(40)]
        window._toggle_tracks_popup()
        self.qt.processEvents()
        area = window.tracks_pop
        area.verticalScrollBar().setValue(10)
        bars = self.qt._scroll_edges._areas[area]
        bar = next(bar for bar in bars if bar.orientation() == Qt.Orientation.Vertical)
        self.assertTrue(bar.isVisible())
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(1, bar.height() - 2))
        self.assertTrue(window._tracks_open)
        self.assertTrue(window._panel_open)
        self.assertGreater(area.verticalScrollBar().value(), 10)

    def test_playlist_height_adapts_without_covering_chat(self):
        window = self.window
        window.set_panel(True)
        for count in (0, 1, 30):
            window._playlist = [{"path": f"/tmp/{i}.mkv", "name": f"Episode {i + 1}.mkv"} for i in range(count)]
            window._refresh_files()
            for height in (520, 720, 1080):
                with self.subTest(count=count, height=height):
                    window.resize(1280, height)
                    self.qt.processEvents()
                    window._place_overlays()
                    row_h = max(24, QFontMetrics(window.files.font()).height() + 12)
                    rows = window.files.viewport().height() // row_h
                    self.assertEqual(window.files.count(), count)
                    self.assertGreaterEqual(rows, 1)
                    self.assertLessEqual(rows, 12)
                    if count < 3 and height >= 720:
                        self.assertEqual(rows, 3)
                    if count == 30 and height == 1080:
                        self.assertEqual(rows, 12)
                        self.assertGreater(window.files.verticalScrollBar().maximum(), 0)
                    self.assertLess(window.files.geometry().bottom(), window.chat.y())
                    self.assertGreaterEqual(window.chat.height(), window.chat.minimumSizeHint().height())
                    self.assertLess(window.chat.geometry().bottom(), window.panel.height())
        window._users = [{"name": str(i), "file": "Episode.mkv", "size": 10000000, "ready": True} for i in range(4)]
        window.resize(1280, 520)
        window._paint_users()
        self.qt.processEvents()
        window._place_overlays()
        rows = window.files.viewport().height() // row_h
        self.assertGreaterEqual(rows, 1)
        self.assertLess(rows, 3)
        self.assertGreaterEqual(window.chat.height(), window.chat.minimumSizeHint().height())

    def test_playlist_centers_playing_episode_and_preserves_manual_scroll(self):
        window = self.window
        window.resize(1280, 520)
        window.set_panel(True)
        window._playlist = [{"path": f"/tmp/{i}.mkv", "name": f"Episode {i + 1}.mkv"} for i in range(6)]
        window._refresh_files()
        self.qt.processEvents()
        window.video.setFocus()
        focus = QApplication.focusWidget()
        row_h = window.files.item(0).sizeHint().height()
        self.assertEqual(window.files.viewport().height() // row_h, 3)
        for index, visible in ((1, [0, 1, 2]), (3, [2, 3, 4]), (5, [3, 4, 5])):
            window._play_path(f"/tmp/{index}.mkv", start=True)
            self.qt.processEvents()
            shown = [window.files.indexAt(QPoint(10, row_h * row + 1)).row() for row in range(3)]
            self.assertEqual(shown, visible)
            self.assertIs(QApplication.focusWidget(), focus)
        window.files.verticalScrollBar().setValue(0)
        window._add_dropped(["/tmp/extra.mkv"])
        self.assertEqual(window.files.verticalScrollBar().value(), 0)
        window.resize(1280, 1080)
        self.qt.processEvents()
        self.assertEqual(window.files.verticalScrollBar().maximum(), 0)
        window._play_path("/tmp/3.mkv", start=True)
        self.assertEqual(window.files.verticalScrollBar().value(), 0)

    def test_drops_append_without_replacing_an_open_episode(self):
        window = self.window
        window._playlist = [{"path": "/tmp/first.mkv", "name": "first.mkv"},
                            {"path": "/tmp/current.mkv", "name": "current.mkv"}]
        window._current_path = "/tmp/current.mkv"
        with patch.object(window, "_play_path") as play:
            for paused in (False, True):
                window._paused = paused
                window._add_dropped([f"/tmp/new-{paused}.mkv", "/tmp/current.mkv"])
                self.assertEqual(window._current_path, "/tmp/current.mkv")
                self.assertEqual(window._paused, paused)
                play.assert_not_called()
            self.assertEqual(len(window._playlist), 4)
            window._playlist = []
            window._add_dropped(["/tmp/episode10.mkv", "/tmp/episode2.mkv"])
            play.assert_called_once_with("/tmp/episode2.mkv", start=False)

    def test_repeat_key_uses_the_physical_r_and_resets_on_restart(self):
        before = copy.deepcopy(self.store.data)
        for platform in ("wayland", "xcb"):
            with patch("yucha.window.QGuiApplication.platformName", return_value=platform):
                for text in ("r", "к", "ρ"):
                    for mode in (1, 2, 0):
                        event = QKeyEvent(QEvent.Type.KeyPress, ord(text.upper()), Qt.KeyboardModifier.NoModifier,
                                          27, 0, 0, text)
                        QApplication.sendEvent(self.window.video, event)
                        self.assertEqual(self.window._repeat, mode)
                        self.assertEqual(self.window.board.repeat, mode)
                        repeat = QKeyEvent(QEvent.Type.KeyPress, ord(text.upper()), Qt.KeyboardModifier.NoModifier,
                                           27, 0, 0, text, True)
                        QApplication.sendEvent(self.window.video, repeat)
                        self.assertEqual(self.window._repeat, mode)
                self.window._open_chat_field()
                self.qt.processEvents()
                text_key = QKeyEvent(QEvent.Type.KeyPress, ord("К"), Qt.KeyboardModifier.NoModifier, 27, 0, 0, "к")
                QApplication.sendEvent(self.window.bar_message, text_key)
                self.assertTrue(self.window.bar_message.text().endswith("к"))
                self.assertEqual(self.window._repeat, 0)
                self.window._close_chat_field()
        QTest.keyClick(self.window.video, Qt.Key.Key_R)
        self.assertEqual(self.window._repeat, 1)
        self.assertEqual(self.store.data, before)
        restarted = self.make_window()
        self.assertEqual(restarted._repeat, 0)
        self.assertEqual(restarted.board.repeat, 0)

    def test_repeat_end_of_file_restarts_wraps_and_stops_correctly(self):
        window = self.window
        window._playlist = [{"path": f"/tmp/{i}.mkv", "name": str(i)} for i in range(3)]
        self.store.data["appearance"]["autoplayNext"] = False
        with patch.object(window, "_play_path", wraps=window._play_path) as play:
            for mode, current, expected, start in ((1, 1, 1, True), (2, 2, 0, True), (0, 1, 2, False)):
                window._repeat = mode
                window._current_path = f"/tmp/{current}.mkv"
                window.ctl.properties.update({"path": window._current_path, "eof-reached": False})
                window._refresh_transport()
                play.reset_mock()
                seeks = window.ctl.calls.count(("seek", "0", "absolute"))
                window.ctl.properties["eof-reached"] = True
                window._refresh_transport()
                if mode == 1:
                    play.assert_not_called()
                    self.assertEqual(window.ctl.calls.count(("seek", "0", "absolute")), seeks + 1)
                    self.assertFalse(window.ctl.properties["pause"])
                else:
                    play.assert_called_once_with(f"/tmp/{expected}.mkv", start=start)
                window._refresh_transport()
                self.assertEqual(play.call_count, 0 if mode == 1 else 1)
                self.assertEqual(window.ctl.calls.count(("seek", "0", "absolute")), seeks + (mode == 1))
            window._repeat = 0
            window._current_path = "/tmp/2.mkv"
            window._eof_seen = False
            play.reset_mock()
            window._refresh_transport()
            play.assert_not_called()
            window._playlist = window._playlist[:1]
            window._current_path = "/tmp/0.mkv"
            for mode in (1, 2):
                window._repeat = mode
                window._advance()
                self.assertEqual(window._current_path, "/tmp/0.mkv")

    def test_repeat_avoids_reload_and_syncplay_does_not_restore_the_rewind_pause(self):
        from syncplay.client import SyncplayClient
        client = SyncplayClient.__new__(SyncplayClient)
        client._player = Mock()
        client.ui = Mock()
        client._globalPaused = True
        client._playerPaused = True
        client.lastAdvanceTime = None
        client.lastRewindTime = time.time()
        client.lastUpdatedFileTime = 0
        client.lastPausedOnLeaveTime = None
        client.userlist = Mock()
        client.userlist.currentUser.canControl.return_value = True
        client.isPlayingMusic = Mock(return_value=False)
        client.instaplayConditionsMet = Mock(return_value=True)
        client.getPlayerPaused = Mock(return_value=True)
        client.changeReadyState = Mock()
        client.openFile = Mock()
        self.app.client = client
        window = self.window
        window._repeat = 1
        window._playlist.append({"path": "/tmp/next.mkv", "name": "next.mkv"})
        window.ctl.properties.update({"pause": True, "eof-reached": True})
        window._eof_seen = False
        window._refresh_transport()
        client.openFile.assert_not_called()
        self.assertIn(("seek", "0", "absolute"), window.ctl.calls)
        self.assertFalse(window.ctl.properties["pause"])
        self.assertFalse(client._toggleReady(True, False))
        client._player.setPaused.assert_called_once_with(True)
        client._player.reset_mock()
        window._repeat = 2
        with patch("twisted.internet.reactor.callFromThread", side_effect=lambda fn, *args: fn(*args)):
            window._advance()
        client.openFile.assert_called_once_with("/tmp/next.mkv", True)
        self.assertTrue(client._toggleReady(True, False))
        client._player.setPaused.assert_not_called()
        client.userlist.currentUser.canControl.return_value = False
        self.assertFalse(client._toggleReady(True, False))
        client._player.setPaused.assert_called_once_with(True)

    def test_file_notifications_stay_in_chat_and_alone_status_moves_to_the_left(self):
        try:
            for language in ("English", "Russian"):
                i18n.use(language)
                window = self.window
                window._osd = []
                window._users = [{"name": "me", "ready": False, "file": "Episode.mkv", "size": 10000000, "duration": 120}]
                window._on_conn({"state": "connecting"})
                window._on_conn({"state": "connected"})
                window._on_users({"list": window._users})
                window._add_chat("", "me is playing 'Episode.mkv' (02:00) in room: 'room'")
                self.assertIn("Episode.mkv", window.chat.toPlainText())
                self.assertFalse(window._osd)
                window._add_chat("", "You're alone in the room")
                self.assertIn(i18n.tr(110), window.board.notices)
                self.assertIn(i18n.tr(110), window.chat.toPlainText())
                self.assertFalse(window._osd)
                window._add_chat("me", "You're alone in the room")
                self.assertEqual(len(window._osd), 1)
                window._add_chat("", "me paused at 0:05")
                self.assertEqual(len(window._osd), 2)
                window._on_users({"list": window._users + [{"name": "other", "ready": False, "file": "Episode.mkv", "size": 10000000, "duration": 120}]})
                window._refresh_osd()
                self.assertNotIn(i18n.tr(110), window.board.notices)
        finally:
            i18n.use("English")

    def test_alone_status_expires_once_per_entry_and_ignores_later_warnings(self):
        window = self.window
        me = {"name": "me", "ready": False, "file": "Episode.mkv", "size": 10000000, "duration": 120}
        other = {**me, "name": "other"}
        with patch("yucha.window.time.monotonic", return_value=100.0) as clock:
            window._on_conn({"state": "connecting"})
            window._on_conn({"state": "connected"})
            window._on_users({"list": [me]})
            window._refresh_osd()
            self.assertIn(i18n.tr(110), window.board.notices)
            clock.return_value = 104.0
            window._add_chat("", "You're alone in the room")
            self.assertIn(i18n.tr(110), window.board.notices)
            clock.return_value = 106.0
            window._refresh_osd()
            self.assertNotIn(i18n.tr(110), window.board.notices)
            window._add_chat("", "You're alone in the room")
            window._add_chat("", "me is playing 'Episode.mkv' (02:00)")
            self.assertNotIn(i18n.tr(110), window.board.notices)
            window._on_users({"list": [me, other]})
            window._on_users({"list": [me]})
            window._add_chat("", "You're alone in the room")
            self.assertNotIn(i18n.tr(110), window.board.notices)

            window._on_conn({"state": "connecting"})
            window._on_users({"list": [me, other]})
            window._on_conn({"state": "connected"})
            window._on_users({"list": [me]})
            window._add_chat("", "You're alone in the room")
            self.assertNotIn(i18n.tr(110), window.board.notices)

            window._on_conn({"state": "connecting"})
            window._on_users({"list": [me]})
            window._on_conn({"state": "connected"})
            window._refresh_osd()
            self.assertIn(i18n.tr(110), window.board.notices)
            window._on_users({"list": [me, other]})
            window._refresh_osd()
            self.assertNotIn(i18n.tr(110), window.board.notices)
            window._on_conn({"state": "connecting"})
            window._on_conn({"state": "connected"})
            window._add_chat("", "You're alone in the room")
            self.assertNotIn(i18n.tr(110), window.board.notices)
            window._on_users({"list": [me]})
            window._refresh_osd()
            self.assertIn(i18n.tr(110), window.board.notices)

    def test_alone_chat_is_tied_to_entry_not_youtube_quality_updates(self):
        window = self.window
        me = {"name": "me", "ready": False, "file": "", "size": None, "duration": None}
        other = {**me, "name": "other"}
        line = [{"k": "text", "v": i18n.tr(110)}]
        window._on_conn({"state": "connecting"})
        window._on_conn({"state": "connected"})
        window._add_chat("", "You're alone in the room")
        self.assertNotIn(line, window._chat_lines)
        window._on_users({"list": [me]})
        self.assertEqual(window._chat_lines.count(line), 1)
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        window._playlist = [{"path": url, "name": "A video"}]
        window._current_path = url
        window.ctl.properties.update({"path": url, "video-params/h": 1080})
        self.app.client.set_youtube_info = Mock(
            side_effect=lambda *args: window._add_chat("", "You are alone in the room"))
        with patch("twisted.internet.reactor.callFromThread", side_effect=lambda fn, *args: fn(*args)):
            for height in (1080, 720, 480):
                window._pick_track("vid", height)
                window.ctl.properties["video-params/h"] = height
                window._refresh_youtube(url)
        self.assertEqual(self.app.client.set_youtube_info.call_count, 3)
        self.assertEqual(window._chat_lines.count(line), 1)
        window._on_users({"list": [me, other]})
        window._on_users({"list": [me]})
        window._add_chat("", "You're alone in the room")
        self.assertEqual(window._chat_lines.count(line), 1)
        window._on_conn({"state": "connecting"})
        window._on_users({"list": [me]})
        window._on_conn({"state": "connected"})
        window._add_chat("", "You're alone in the room")
        self.assertEqual(window._chat_lines.count(line), 2)

    def test_panel_bottom_follows_chat_limit_with_unchanged_padding_and_top(self):
        window = self.window
        window._dev["panel_center"] = False
        window.set_panel(True)
        for style in ("classic", "modern"):
            self.store.data["appearance"]["style"] = style
            window.apply_theme()
            for height in (520, 720, 1080):
                window.resize(1280, height)
                self.qt.processEvents()
                window._dev["chat_max"] = 0
                window._fit_playlist()
                top = window.panel.y()
                full_height = window.panel.height()
                padding = window.panel.layout().contentsMargins().bottom()
                for cap in (150, 90, 0):
                    with self.subTest(style=style, height=height, cap=cap):
                        window._dev["chat_max"] = cap
                        window._fit_playlist()
                        self.qt.processEvents()
                        window._place_overlays()
                        self.assertEqual(window.panel.y(), top)
                        self.assertEqual(window.panel.height() - window.chat.y() - window.chat.height(), padding)
                        if cap:
                            self.assertLessEqual(window.chat.height(), cap)
                            self.assertLessEqual(window.panel.height(), full_height)
                        else:
                            self.assertEqual(window.panel.height(), full_height)
                window._dev["chat_max"] = 90
                window._fit_playlist()
                short = window.panel.height()
                window._dev["chat_max"] = 150
                window._fit_playlist()
                self.assertGreaterEqual(window.panel.height(), short)

    def test_chat_maximum_height_previews_and_dev_reset_and_cancel_restore_it(self):
        self.window.set_panel(True)
        dialog = self.dialog()
        self.assertEqual(dialog._chat_max.value(), 340)
        self.assertEqual(dialog._chat_max.specialValueText(), i18n.tr(109))
        form = dialog._chat_max.parentWidget().layout()
        self.assertEqual(form.labelForField(dialog._chat_max).text(), i18n.tr(108))
        dialog._chat_max.setValue(150)
        self.qt.processEvents()
        self.assertEqual(self.window.chat.maximumHeight(), 150)
        self.assertEqual(self.window.chat.height(), 150)
        dialog._reset_dev()
        self.qt.processEvents()
        self.assertEqual(dialog._chat_max.value(), 340)
        self.assertGreater(self.window.chat.height(), 150)
        dialog.reject()
        self.assertNotIn("chat_max", self.window._dev)

    def test_repeat_indicator_has_accent_fill_and_themed_outlines(self):
        self.window._users = []
        for theme in ("dark", "light"):
            self.store.data["appearance"].update({"theme": theme, "accentColor": "#CC3355"})
            self.window._dev.setdefault("face", {})["border"] = {theme: "#2244AA"}
            for mode in (0, 1, 2):
                self.window._repeat = mode
                self.window._refresh_osd()
                image = QImage(120, 120, QImage.Format.Format_ARGB32)
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                self.window.board.paint_on(painter, 120, 120)
                painter.end()
                colors = [image.pixelColor(x, y) for x in range(120) for y in range(120)]
                center = [image.pixelColor(x, y) for x in range(36, 45) for y in range(34, 47)]
                self.assertEqual(any(color.alpha() for color in center), mode == 1)
                if mode:
                    self.assertIn(QColor("#CC3355"), colors)
                    self.assertTrue(any(color.alpha() and color.blue() > color.red() for color in colors))
                    if mode == 1:
                        self.assertTrue(any(color.alpha() and color.blue() > color.red() for color in center))
                else:
                    self.assertFalse(any(color.alpha() for color in colors))

    def test_mute_uses_the_physical_m_key_without_intercepting_text(self):
        for platform in ("wayland", "xcb"):
            with patch("yucha.window.QGuiApplication.platformName", return_value=platform):
                for text in ("m", "ь", "μ"):
                    with self.subTest(platform=platform, text=text):
                        self.window._set_muted(False)
                        event = QKeyEvent(QEvent.Type.KeyPress, ord(text.upper()), Qt.KeyboardModifier.NoModifier,
                                          58, 0, 0, text)
                        QApplication.sendEvent(self.window.video, event)
                        self.assertTrue(self.window._muted)
                        repeat = QKeyEvent(QEvent.Type.KeyPress, ord(text.upper()), Qt.KeyboardModifier.NoModifier,
                                           58, 0, 0, text, True)
                        QApplication.sendEvent(self.window.video, repeat)
                        self.assertTrue(self.window._muted)
                self.window._set_muted(False)
                other_key = QKeyEvent(QEvent.Type.KeyPress, ord("Ь"), Qt.KeyboardModifier.NoModifier,
                                      57, 0, 0, "ь")
                QApplication.sendEvent(self.window.video, other_key)
                self.assertFalse(self.window._muted)
                self.window._open_chat_field()
                self.qt.processEvents()
                text_key = QKeyEvent(QEvent.Type.KeyPress, ord("Ь"), Qt.KeyboardModifier.NoModifier,
                                     58, 0, 0, "ь")
                QApplication.sendEvent(self.window.bar_message, text_key)
                self.assertTrue(self.window.bar_message.text().endswith("ь"))
                self.assertFalse(self.window._muted)
                self.window._close_chat_field()
        QTest.keyClick(self.window.video, Qt.Key.Key_M)
        self.assertTrue(self.window._muted)

    def test_sidebar_separators_keep_empty_rows_and_people_at_the_top(self):
        self.window.set_panel(True)
        for theme, border in (("dark", "#34363F"), ("light", "#D9D3C7"), ("dark", "#526478")):
            self.store.data["appearance"]["theme"] = theme
            self.window._dev.setdefault("face", {})["border"] = {theme: border}
            self.window.apply_theme()
            for count in (0, 1, 3):
                with self.subTest(theme=theme, count=count):
                    self.window._playlist = [{"path": f"/tmp/{index}.mkv", "name": f"{index}.mkv"}
                                             for index in range(count)]
                    self.window._users = [{"name": f"user{index}", "file": f"{index}.mkv",
                                           "size": 10000000, "ready": True} for index in range(count)]
                    self.window._refresh_files()
                    self.window._paint_users()
                    self.qt.processEvents()
                    files = self.window.files
                    self.assertEqual(files.count(), count)
                    image = files.viewport().grab().toImage()
                    for index in range(max(3, count) - 1):
                        y = (files.visualItemRect(files.item(index)).bottom() if index < count
                             else (index + 1) * max(24, QFontMetrics(files.font()).height() + 12) - 1)
                        self.assertEqual(image.pixelColor(10, y), QColor(border))
                    users = self.window.room_users
                    self.assertEqual(len(users._full_names), count)
                    if count:
                        for column in (users.names_col, users.files_col, users.sizes_col):
                            self.assertEqual(column.itemAt(0).widget().y(), 0)
                    lines = users._lines
                    image = users.grab().toImage()
                    for index in range(1, max(2, count)):
                        y = lines.top + index * lines.row_h
                        self.assertEqual(image.pixelColor(10, y), QColor(border))
                    for x in (lines.split_x, lines.split2_x):
                        y = lines.top + 3
                        self.assertEqual(image.pixelColor(x, y), QColor(border))

    def test_user_size_column_gives_its_saved_width_only_to_the_filename(self):
        self.window.set_panel(True)
        self.window._users = [{"name": "me", "file": "Episode 1.mkv", "size": 10000000, "ready": True}]
        self.window._paint_users()
        for width in (380, 600):
            with self.subTest(width=width):
                self.window._panel_width = width
                self.window._place_overlays()
                self.qt.processEvents()
                users = self.window.room_users
                changed = (users.names.width(), users.files_scroll.width(), users.sizes.width())
                # Let the previous Qt layout calculate its original column widths.
                users.names.setMinimumWidth(0)
                users.names.setMaximumWidth(16777215)
                users.sizes.setMinimumWidth(users._size_width)
                users.layout().activate()
                original = (users.names.width(), users.files_scroll.width(), users.sizes.width())
                self.assertEqual(changed[0], original[0])
                self.assertLessEqual(abs(changed[2] - original[2] * 0.85), 1)
                self.assertEqual(changed[1] - original[1], original[2] - changed[2])
                self.assertEqual(sum(changed), sum(original))
                self.window._paint_users()
                self.qt.processEvents()
                self.assertEqual((users.names.width(), users.files_scroll.width(), users.sizes.width()), changed)

    def test_connection_banner_uses_matching_text_and_dot_colors(self):
        try:
            for language in ("English", "Russian"):
                i18n.use(language)
                for theme in ("dark", "light"):
                    with self.subTest(language=language, theme=theme):
                        self.store.data["appearance"]["theme"] = theme
                        self.window.apply_theme()
                        for state, message, color in (("connected", 6, "#3EAD62"),
                                ("disconnected", 7, "#C4453C"), ("connecting", 9, "#D6B23A"),
                                ("failed", 7, "#C4453C")):
                            self.window._on_conn({"state": state})
                            label = self.window.banner_text
                            self.assertEqual(label.text(), i18n.tr(message))
                            size = self.window.font().pointSize() - (1 if state == "connected" else 0)
                            self.assertEqual(label.font().pointSize(), size)
                            for field in (label, self.window.banner_dot):
                                self.assertEqual(field.palette().color(QPalette.ColorRole.WindowText), QColor(color))
                        self.window._chat_held = True
                        self.window._on_conn({"state": "connecting"})
                        self.assertEqual(label.text(), i18n.tr(9))
        finally:
            i18n.use("English")

    def test_reconnect_notifications_update_the_banner_until_the_room_is_joined(self):
        self.app.bridge = Bridge(Path(self.temp.name))
        ui = PlayerUI(self.app.bridge)
        def message(key, *args, state):
            ui.showMessage(getMessage(key).format(*args))
            self.window._read_events()
            self.assertEqual(self.window._connected, state == "connected")
            self.assertEqual(ui._connected, state == "connected")
            self.assertEqual(self.window._connecting, state == "connecting")
        message("connection-attempt-notification", "example.test", 8999, state="connecting")
        message("reachout-successful-notification", "example.test", "127.0.0.1", state="connecting")
        message("connected-successful-notification", state="connected")
        from syncplay.client import SyncplayClient
        client = MagicMock(ui=ui)
        for _ in range(2):
            SyncplayClient._performRetryStateReset(client)
            self.window._read_events()
            self.assertFalse(ui._connected)
            self.assertFalse(self.window._connected)
            self.assertTrue(self.window._connecting)
            self.assertEqual(self.window.banner_text.text(), i18n.tr(9))
        message("connected-successful-notification", state="connected")
        message("disconnection-notification", state="failed")
        self.assertEqual(self.window.banner_text.text(), i18n.tr(7))
        ui.showErrorMessage(getMessage("wrong-password-server-error"))
        self.window._read_events()
        specific = self.window.status.text()
        message("disconnection-notification", state="failed")
        self.assertEqual(self.window.status.text(), specific)
        message("connection-attempt-notification", "example.test", 8999, state="connecting")
        self.assertFalse(self.window.status.text())
        self.assertIsNone(ui._fail_text)
        message("connected-successful-notification", state="connected")
        ui.showMessage("<friend> " + getMessage("reconnection-attempt-notification"))
        self.window._read_events()
        self.assertTrue(self.window._connected)

    def test_space_repeats_and_chat_do_not_toggle_playback(self):
        self.window.ready.setChecked(True)
        self.window.video.setFocus()
        self.qt.processEvents()
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ", True)
        QApplication.sendEvent(self.window.video, event)
        self.assertFalse(self.window.ctl.properties["pause"])
        self.window._open_chat_field()
        self.qt.processEvents()
        QTest.keyClicks(self.window.bar_message, "hello world")
        self.assertEqual(self.window.bar_message.text(), "hello world")
        self.assertFalse(self.window.ctl.properties["pause"])

    def test_space_pauses_playing_video_even_before_ready_state_arrives(self):
        self.window.ready.setChecked(False)
        self.window._toggle_ready = Mock()
        self.window.video.setFocus()
        self.qt.processEvents()
        QTest.keyClick(self.window.video, Qt.Key.Key_Space)
        self.assertTrue(self.window.ctl.properties["pause"])
        self.window._toggle_ready.assert_not_called()

    def test_space_in_readonly_chat_and_volume_popup_pauses_once(self):
        self.window.set_panel(True)
        self.window.chat.setFocus()
        self.qt.processEvents()
        QTest.keyClick(self.window.chat, Qt.Key.Key_Space)
        self.assertTrue(self.window.ctl.properties["pause"])
        self.window._toggle_volume_popup()
        QTest.keyClick(self.window.volume_slider, Qt.Key.Key_Space)
        self.assertFalse(self.window.ctl.properties["pause"])
        self.assertEqual(self.window.ctl.calls.count(("cycle", "pause")), 2)

    def test_bar_buttons_stay_put_during_transport_updates(self):
        events = VisibilityEvents()
        for button in (self.window.ready, self.window.chat_btn, self.window.tracks_btn):
            button.installEventFilter(events)
        geometry = self.window.volume_btn.geometry()
        for _ in range(5):
            self.window._refresh_transport()
            self.qt.processEvents()
        self.assertEqual(events.events, [])
        self.assertEqual(self.window.volume_btn.geometry(), geometry)

    def test_tracks_button_accepts_gaps_and_volume_click_is_independent(self):
        button = self.window.tracks_btn
        for point in (QPoint(1, 1), QPoint(20, 15), QPoint(20, 20), QPoint(38, 34)):
            self.click_at(button, point)
            self.assertTrue(self.window._tracks_open)
            self.window._toggle_tracks_popup()
        for _ in range(4):
            self.click_at(self.window.volume_btn, self.window.volume_btn.rect().center())
            self.assertTrue(self.window._volume_open)
            self.assertFalse(self.window._tracks_open)
            self.window._toggle_volume_popup()

    def test_clicking_panel_background_keeps_it_open(self):
        self.window.set_panel(True)
        self.qt.processEvents()
        self.click_at(self.window.panel, QPoint(self.window.panel.width() // 2, 5))
        self.assertTrue(self.window._panel_open)
        self.click_at(self.window.video, QPoint(10, 100))
        self.assertFalse(self.window._panel_open)

    def test_vertical_volume_geometry_stays_fixed_across_digit_counts(self):
        self.store.data["appearance"]["volumeOverlay"] = "vertical"
        self.window._toggle_volume_popup()
        self.qt.processEvents()
        self.window._place_overlays()
        geometry = self.window.volume_pop.geometry()
        readout_y = self.window.volume_readout.y()
        for level in (0, 1, 9, 10, 99, 100, 130, 8, 99):
            self.window._show_volume(level)
            self.window._refresh_transport()
            self.qt.processEvents()
            self.window._place_overlays()
            self.assertEqual(self.window.volume_pop.geometry(), geometry)
            self.assertLessEqual(abs(self.window.volume_readout.geometry().center().x() - self.window.volume_pop.rect().center().x()), 1)
            self.assertEqual(self.window.volume_readout.y(), readout_y)

    def test_popup_tracks_real_button_position_after_tracks_disappear(self):
        self.window._toggle_volume_popup()
        self.window.ctl.properties["track-list"] = []
        self.window._refresh_transport()
        self.qt.processEvents()
        popup = self.window.volume_pop.geometry()
        button = self.window.volume_btn
        center = button.mapTo(self.window.stage, button.rect().center()).x()
        self.assertLessEqual(abs(popup.center().x() - center), 1)
        for _ in range(3):
            self.window._refresh_transport()
            self.qt.processEvents()
            self.assertEqual(self.window.volume_pop.geometry(), popup)

    def test_clicking_inside_fullscreen_panel_edge_does_not_close_it(self):
        self.store.data["appearance"]["style"] = "classic"
        self.window.apply_theme()
        self.window.showFullScreen()
        self.window.set_panel(True)
        self.qt.processEvents()
        self.click_at(self.window.panel, QPoint(self.window.panel.width() - 2, 5))
        self.assertTrue(self.window._panel_open)

    def test_panel_bottom_drag_saves_chat_height_without_changing_the_padding(self):
        window = self.window
        window.resize(1280, 1100)
        window.set_panel(True)
        self.qt.processEvents()
        self.assertEqual(window.chat.height(), 340)
        original = window.panel.height()
        self.drag(window.panel, QPoint(window.panel.width() // 2, original - 2), QPoint(0, -80))
        self.assertEqual(window.chat.height(), 260)
        self.assertEqual(window.panel.height(), original - 80)
        self.assertEqual(window.panel.height() - window.chat.y() - window.chat.height(), 16)
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {"chat_max": 260})
        dialog = self.dialog()
        self.assertEqual(dialog._chat_max.value(), 260)
        dialog.reject()
        self.drag(window.panel, QPoint(window.panel.width() // 2, window.panel.height() - 2), QPoint(0, 80))
        self.assertEqual(window.chat.height(), 340)
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {})
        # The original width grip still persists the ordinary panel width.
        self.drag(window.panel, QPoint(2, 80), QPoint(-60, 0))
        self.assertEqual(ConfigStore().data["appearance"]["panelWidth"], 440)
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {})

    def test_panel_center_drag_and_home_stay_above_the_bar(self):
        window = self.window
        window.resize(1280, 1100)
        window.set_panel(True)
        window.apply_dev({})
        self.qt.processEvents()
        for field in (window.users_title, window.playlist_title, window.chat_title):
            self.assertEqual(field.cursor().shape(), Qt.CursorShape.ArrowCursor)
        for field in (window.gear, window.panel_home, window.banner):
            self.assertEqual(field.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        for point, cursor in ((QPoint(2, 80), Qt.CursorShape.SizeHorCursor),
                (QPoint(window.panel.width() // 2, window.panel.height() - 2), Qt.CursorShape.SizeVerCursor),
                (QPoint(window.panel.width() - 2, 10), Qt.CursorShape.ArrowCursor)):
            QTest.mouseMove(window.panel, point)
            self.assertEqual(window.panel.cursor().shape(), cursor)
        bounds = window._panel_rect()
        expected = QPoint(bounds.x(), bounds.y() + (bounds.height() - window.panel.height()) // 2)
        self.assertEqual(window.panel.pos(), expected)
        self.assertTrue(window.panel_home.isHidden())
        window._open_settings = Mock()
        self.drag(window.banner, window.banner.rect().center(), QPoint(60, 0))
        self.assertEqual(window.panel.pos(), expected)
        self.assertIsNone(window._panel_pos)
        self.assertTrue(window.panel_home.isHidden())
        self.drag(window.banner, window.banner.rect().center(), QPoint(-400, -80))
        self.assertEqual(window.panel.pos(), expected + QPoint(-400, -80))
        self.assertTrue(window.panel_home.isVisible())
        window._open_settings.assert_not_called()
        for delta in (QPoint(-10000, -10000), QPoint(10000, 10000)):
            self.drag(window.banner, window.banner.rect().center(), delta)
            self.assertGreaterEqual(window.panel.x(), 12)
            self.assertGreaterEqual(window.panel.y(), bounds.y())
            self.assertLessEqual(window.panel.geometry().right(), window.stage.width() - 13)
            self.assertLessEqual(window.panel.geometry().bottom(), window._bar_rect().top() - 9)
        window.resize(900, 600)
        self.qt.processEvents()
        self.assertLessEqual(window.panel.geometry().right(), window.stage.width() - 13)
        self.assertLessEqual(window.panel.geometry().bottom(), window._bar_rect().top() - 9)
        window.resize(1280, 1100)
        self.qt.processEvents()
        window.panel_home.click()
        self.assertEqual(window.panel.pos(), expected)
        self.assertTrue(window.panel_home.isHidden())
        QTest.mouseClick(window.banner, Qt.MouseButton.LeftButton)
        window._open_settings.assert_called_once_with(0)
        self.drag(window.banner, window.banner.rect().center(), QPoint(-100, -30))
        manual = window.panel.pos()
        dialog = self.dialog()
        dialog._panel_flags["panel_drag"].setChecked(False)
        self.assertIsNone(window._panel_pos)
        dialog.reject()
        self.assertEqual(window.panel.pos(), manual)
        self.assertTrue(window.panel_home.isVisible())
        window._open_settings.reset_mock()
        QTest.mousePress(window.banner, Qt.MouseButton.LeftButton)
        self.qt.sendEvent(window.banner, QEvent(QEvent.Type.UngrabMouse))
        self.assertIsNotNone(window._grip)
        self.qt.sendEvent(window.panel, QEvent(QEvent.Type.UngrabMouse))
        self.assertIsNone(window._grip)
        QTest.mouseRelease(window.panel, Qt.MouseButton.LeftButton)
        window._open_settings.assert_not_called()
        window.apply_dev({"panel_drag": False})
        self.assertEqual(window.panel.pos(), expected)
        self.assertIsNone(window._panel_pos)
        self.assertTrue(window.panel_home.isHidden())
        window.apply_dev({"panel_center": False})
        self.assertEqual(window.panel.y(), bounds.y())

    def test_panel_options_and_minimum_bar_width_preview_save_and_reset(self):
        dialog = self.dialog()
        self.assertEqual(dialog._chat_max.value(), 340)
        self.assertTrue(dialog._panel_flags["panel_center"].isChecked())
        self.assertTrue(dialog._panel_flags["panel_drag"].isChecked())
        self.assertEqual(dialog._bar_min.value(), 500)
        self.assertFalse(dialog._panel_flags["chapters"].isChecked())
        dialog._panel_flags["panel_center"].setChecked(False)
        dialog._panel_flags["panel_drag"].setChecked(False)
        dialog._bar_min.setValue(1000)
        dialog._panel_flags["chapters"].setChecked(True)
        self.assertEqual(self.window._bar_rect().width(), 1000)
        dialog._accept()
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.app.store = ConfigStore()
        restarted = self.make_window()
        self.assertTrue(restarted._dev["chapters"])
        self.assertFalse(restarted._dev["panel_center"])
        self.assertFalse(restarted._dev["panel_drag"])
        self.assertFalse(restarted.panel_home.isVisible())
        restarted.set_panel(True)
        self.assertTrue(restarted.panel_home.isHidden())
        self.assertEqual(restarted._bar_rect().width(), 1000)
        restarted.resize(900, 600)
        self.qt.processEvents()
        self.assertEqual(restarted._bar_rect().width(), restarted.stage.width())
        self.app.store = self.store
        dialog = self.dialog()
        dialog._panel_flags["panel_drag"].setChecked(True)
        dialog._bar_min.setValue(300)
        dialog.reject()
        self.assertFalse(self.window._dev["panel_drag"])
        self.assertEqual(self.window._dev["bar_min"], 1000)
        dialog = self.dialog()
        dialog._reset_dev()
        self.assertFalse(dialog._panel_flags["chapters"].isChecked())
        self.assertEqual(self.window._dev, {})
        self.assertTrue(self.window.panel_home.isHidden())
        self.assertTrue(dialog._panel_flags["panel_center"].isChecked())
        self.assertTrue(dialog._panel_flags["panel_drag"].isChecked())
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {})
        dialog.reject()

    def test_both_fullscreen_edges_toggle_the_panel_without_affecting_windowed_clicks(self):
        window = self.window
        self.assertFalse(window._panel_open)
        self.click_at(window.stage, QPoint(1, 1))
        self.assertFalse(window._panel_open)
        window.showFullScreen()
        self.qt.processEvents()
        for point in (QPoint(1, 1), QPoint(window.stage.width() - 1, 1)):
            self.click_at(window.stage, point)
            self.assertTrue(window._panel_open)
            window.set_panel(False)

    def test_banner_hover_keeps_the_pointing_cursor_and_room_click(self):
        window = self.window
        window.set_panel(True)
        self.qt.processEvents()
        window._grip_cursor = Mock(wraps=window._grip_cursor)
        for field in (window.banner, window.banner_text, window.banner_dot):
            QTest.mouseMove(window.video, window.video.rect().center())
            window._grip_cursor.reset_mock()
            point = field.mapTo(window.banner, field.rect().center())
            QTest.mouseMove(window.banner, point)
            self.qt.processEvents()
            window._grip_cursor.assert_not_called()
            self.assertEqual(window.banner.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        window._open_settings = Mock()
        QTest.mouseClick(window.banner, Qt.MouseButton.LeftButton)
        window._open_settings.assert_called_once_with(0)

    def test_left_panel_mirrors_controls_geometry_and_the_width_grip(self):
        window = self.window
        window.resize(1280, 1100)
        window.set_panel(True)
        for style in ("modern", "classic"):
            with self.subTest(style=style):
                look = self.store.data["appearance"]
                look.update(style=style, mainPanel="right")
                window.apply_dev({})
                window._reset_panel_position()
                self.qt.processEvents()
                right = window.panel.geometry()
                look["mainPanel"] = "left"
                window.apply_theme()
                self.qt.processEvents()
                left = window.panel.geometry()
                gap = 12 if style == "modern" else 0
                self.assertEqual(left.x(), gap)
                self.assertEqual(right.x(), window.stage.width() - left.width() - gap)
                self.assertEqual(left.size(), right.size())
                self.assertEqual(left.y(), right.y())
                self.assertEqual(window.panel_home.kind, "arrow_left")
                self.assertTrue(window.panel_home.isHidden())
                self.drag(window.banner, window.banner.rect().center(), QPoint(400, 40))
                self.assertNotEqual(window.panel.pos(), left.topLeft())
                self.assertTrue(window.panel_home.isVisible())
                self.assertLess(window.panel_home.x(), window.gear.x())
                self.assertLess(window.gear.x(), window.banner.x())
                self.assertLess(window.panel.geometry().bottom(), window._bar_rect().top() - (8 if gap else 0))
                window.panel_home.click()
                self.assertEqual(window.panel.geometry(), left)
                self.assertTrue(window.panel_home.isHidden())
                self.drag(window.panel, QPoint(window.panel.width() - 2, 80), QPoint(60, 0))
                self.assertEqual(window.panel.width(), left.width() + 60)
                self.assertEqual(window.panel.x(), gap)
                self.assertTrue(window.panel_home.isHidden())
                window.apply_dev({"panel_drag": False})
                self.assertTrue(window.panel_home.isHidden())
                self.assertLess(window.gear.x(), window.banner.x())
                look["mainPanel"] = "right"
                window.apply_dev({})
                self.qt.processEvents()
                self.assertEqual(window.panel_home.kind, "arrow_right")
                self.assertTrue(window.panel_home.isHidden())
                self.drag(window.banner, window.banner.rect().center(), QPoint(-60, 0))
                self.assertTrue(window.panel_home.isVisible())
                self.assertLess(window.banner.x(), window.gear.x())
                self.assertLess(window.gear.x(), window.panel_home.x())

    def test_panel_side_preview_cancel_save_and_resets(self):
        window = self.window
        window.resize(1280, 1100)
        window.set_panel(True)
        self.qt.processEvents()
        try:
            for language, choices in (("English", ["Right", "Left"]), ("Russian", ["Справа", "Слева"])):
                i18n.use(language)
                dialog = self.dialog()
                self.assertEqual([dialog.main_panel.itemText(i) for i in range(2)], choices)
                dialog.reject()
        finally:
            i18n.use("English")
        window._panel_pos = QPoint(200, 100)
        window._place_overlays()
        before = window.panel.pos()
        dialog = self.dialog()
        self.assertEqual(dialog.main_panel.currentData(), "right")
        dialog.main_panel.setCurrentIndex(1)
        self.assertEqual(window.panel.x(), 12)
        self.assertEqual(ConfigStore().data["appearance"]["mainPanel"], "right")
        dialog.main_panel.setCurrentIndex(0)
        dialog.reject()
        self.assertEqual(window.panel.pos(), before)
        room = copy.deepcopy(self.store.data["connection"])
        def edit(dialog):
            dialog.main_panel.setCurrentIndex(1)
            dialog._accept()
            return QDialog.DialogCode.Accepted
        with patch.object(SettingsDialog, "exec", edit):
            window._open_settings()
        self.app.store = ConfigStore()
        restarted = self.make_window()
        restarted.set_panel(True)
        self.assertEqual(restarted.panel.x(), 12)
        self.assertEqual(restarted.panel_home.kind, "arrow_left")
        self.assertEqual(self.app.store.data["connection"], room)
        self.app.store = self.store
        window._panel_pos = QPoint(200, 100)
        window._place_overlays()
        dialog = self.dialog()
        dialog._reset_dev()
        self.assertEqual(window.panel.x(), 12)
        self.assertEqual(ConfigStore().data["appearance"]["mainPanel"], "left")
        dialog.reject()
        dialog = self.dialog()
        dialog._reset_standard()
        self.assertEqual(dialog.main_panel.currentData(), "right")
        self.assertEqual(window.panel_home.kind, "arrow_right")
        self.assertEqual(window.panel.x(), window.stage.width() - window.panel.width() - 12)
        self.assertEqual(ConfigStore().data["appearance"]["mainPanel"], "right")
        self.assertEqual(ConfigStore().data["connection"], room)
        dialog.reject()

    def test_horizontal_volume_number_has_the_same_background_as_panel(self):
        self.window.video.setStyleSheet("background: #325FC0;")
        self.window._dev = {"bar_alpha": 40}
        self.window.apply_theme()
        self.window._show_volume(80)
        self.qt.processEvents()
        image = self.window.grab().toImage()
        number_corner = self.window.volume_text.mapTo(self.window, QPoint(1, 1))
        panel_corner = self.window.volume_box.mapTo(self.window, QPoint(12, 7))
        self.assertEqual(image.pixelColor(number_corner), image.pixelColor(panel_corner))

    def test_alfa_size_controls_content_independently(self):
        dialog = self.dialog()
        dialog._dev_rows["alfa"]["size"].setValue(19)
        self.qt.processEvents()
        self.assertEqual(self.window.chat.font().pointSize(), 19)
        self.assertEqual(self.window.files.font().pointSize(), 19)
        self.assertEqual(self.window.volume_readout.font().pointSize(), 19)
        self.assertEqual(self.window.font().pointSize(), 13)
        dialog.reject()

    def test_ok_does_not_apply_an_unchanged_preview_again(self):
        def edit(dialog):
            dialog.accent.set_color("#128ABC")
            dialog._preview_theme()
            self.window.apply_theme = Mock(wraps=self.window.apply_theme)
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        self.window.apply_theme.assert_not_called()
        self.assertEqual(ConfigStore().data["appearance"]["accentColor"], "#128ABC")

    def test_ok_flushes_a_pending_size_preview_only_once(self):
        self.window.apply_theme = Mock(wraps=self.window.apply_theme)

        def edit(dialog):
            dialog.ui_size.setValue(14)
            self.assertTrue(dialog._theme_timer.isActive())
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        self.assertEqual(self.window.apply_theme.call_count, 1)
        self.assertEqual(self.window.font().pointSize(), 14)

    def test_closed_settings_dialogs_are_released(self):
        execute = SettingsDialog.exec

        def close(dialog):
            QTimer.singleShot(0, dialog.reject if cancel else dialog._accept)
            return execute(dialog)

        with patch.object(SettingsDialog, "exec", close):
            for cancel in (True, False):
                self.window._open_settings()
                self.qt.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self.assertEqual(self.window.findChildren(SettingsDialog), [])

    def test_dev_ui_osd_and_title_sizes_are_effective(self):
        dialog = self.dialog()
        dialog._dev_rows["ui"]["size"].setValue(15)
        dialog._dev_rows["osd"]["size"].setValue(21)
        dialog._dev_rows["titles"]["size"].setValue(16)
        self.qt.processEvents()
        self.assertEqual(self.window.font().pointSize(), 15)
        self.assertEqual(self.window.board.font_px, 21)
        self.assertEqual(self.window.users_title.font().pointSize(), 16)
        dialog.accent.set_color("#567ABC")
        dialog._preview_theme()
        self.assertEqual(self.window.board.font_px, 21)
        dialog.reject()

    def test_dev_settings_survive_restart_and_cancel_restores_preview(self):
        def edit(dialog):
            dialog._dev_rows["alfa"]["size"].setValue(18)
            dialog._dev_bar.setValue(70)
            dialog._bar_alpha.setValue(61)
            dialog._settings_w.setValue(540)
            dialog._slider_numbers.setChecked(True)
            dialog._chat_max.setValue(150)
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        saved = copy.deepcopy(self.window._dev)
        self.app.store = ConfigStore()
        restarted = self.make_window()
        self.assertEqual(restarted._dev, saved)
        self.assertEqual(restarted._bar_height(), 70)
        self.assertEqual(restarted.chat.font().pointSize(), 18)
        self.assertEqual(restarted.chat.maximumHeight(), 150)
        before = copy.deepcopy(self.window._dev)
        dialog = self.dialog()
        dialog._dev_rows["alfa"]["size"].setValue(30)
        dialog.reject()
        self.assertEqual(self.window._dev, before)

    def test_saved_dialog_controls_apply_even_with_dev_tab_hidden(self):
        def edit(dialog):
            dialog._settings_w.setValue(540)
            dialog._settings_h.setValue(400)
            dialog._settings_pad.setValue(32)
            dialog._slider_numbers.setChecked(True)
            dialog._store_dev_tab(False)
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        dialog = self.dialog()
        self.assertIsNone(dialog._dev_page)
        self.assertEqual((dialog._page_w, dialog._page_h), (540, 400))
        self.assertEqual(dialog._side_layouts[0][0].contentsMargins().left(), 32)
        self.assertTrue(dialog.ui_size._numbers)
        dialog.reject()

    def test_dev_activation_does_not_save_values_and_edits_are_sparse(self):
        self.store.data["appearance"]["devTab"] = False
        dialog = self.dialog()
        for _ in range(5):
            dialog._logo_pressed()
        self.assertEqual(self.window._dev, {})
        dialog._accept()
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {})
        dialog = self.dialog()
        dialog.gamma_size.setValue(18)
        dialog._dev_rows["alfa"]["bold"].setChecked(True)
        dialog._face_rows["border"]["dark"].set_color("#123456")
        dialog._push_dev()
        expected = {"gamma": 18, "alfa": {"bold": True}, "face": {"border": {"dark": "#123456"}}}
        self.assertEqual(self.window._dev, expected)
        dialog._accept()
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.assertEqual(ConfigStore().data["appearance"]["dev"], expected)
        dialog = self.dialog()
        self.assertEqual(dialog._face_rows["border"]["light"]._color.name().upper(),
                         dialog._dev_defaults()["face"]["border"]["light"])
        dialog.gamma_size.setValue(10)
        self.assertNotIn("gamma", self.window._dev)
        dialog._accept()
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.assertNotIn("gamma", ConfigStore().data["appearance"]["dev"])

    def test_legacy_dev_defaults_are_not_saved_as_overrides(self):
        dialog = self.dialog()
        defaults = dialog._dev_defaults()
        dialog.reject()
        self.window._dev = defaults
        self.window._dev["gamma"] = 18
        dialog = self.dialog()
        dialog._accept()
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {"gamma": 18})

    def test_dev_reset_is_saved_immediately_without_saving_other_previews(self):
        self.store.data["appearance"].update({"uiFontSize": 16, "chatFontSize": 20,
                                              "subFontSize": 58, "subColor": "#AABBCC"})
        self.window._dev = {"gamma": 19, "bar": 70}
        self.store.data["appearance"]["dev"] = copy.deepcopy(self.window._dev)
        self.store.save()
        before = copy.deepcopy(self.store.data)
        dialog = self.dialog()
        dialog.ui_size.setValue(15)
        dialog._preview_theme()
        dialog.host.setText("not-saved.example")
        dialog._reset_dev()
        self.assertEqual(self.window._dev, {})
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {})
        self.assertEqual(ConfigStore().data["appearance"]["uiFontSize"], 16)
        self.assertEqual(self.window.font().pointSize(), 15)
        dialog.gamma_size.setValue(24)
        dialog.reject()
        before["appearance"]["dev"] = {}
        self.assertEqual(self.store.data, before)
        self.assertEqual(ConfigStore().data, before)
        self.assertEqual(self.window._dev, {})
        self.assertEqual(self.window.font().pointSize(), 16)
        self.app.store = ConfigStore()
        restarted = self.make_window()
        self.assertEqual(restarted._dev, {})
        self.assertEqual(restarted.font().pointSize(), 16)
        self.assertEqual(restarted.board.font_px, 20)
        restarted._apply_subtitles()
        self.assertEqual(restarted.ctl.properties["sub-font-size"], 58)

    def test_other_reset_is_saved_immediately_and_preserves_room(self):
        self.store.data["appearance"].update({
            "theme": "light", "style": "classic", "accentColor": "#123456",
            "accentColor2": "#ABCDEF", "chatColor": "#010203", "uiFontSize": 16,
            "chatFontSize": 20, "subFontSize": 58, "subFont": "serif", "subColor": "#AABBCC",
            "autoplayNext": True, "fastforwardOnDesync": False, "slowOnDesync": False,
            "panelWidth": 650, "volumeOverlay": "vertical"})
        self.window._dev = {"gamma": 18, "ui": {"size": 15}, "panel": 650,
                            "osd": {"size": 22}, "sub": {"size": 57}, "settings_h": 500}
        self.store.data["appearance"]["dev"] = copy.deepcopy(self.window._dev)
        self.window.apply_dev(self.window._dev)
        room = copy.deepcopy(self.store.data["connection"])
        self.app.on_command = Mock(wraps=self.app.on_command)
        dialog = self.dialog()
        dialog.host.setText("pending.example")
        fields = tuple(field.text() for field in dialog._room_fields)
        dialog.reset_other.click()
        self.assertEqual(tuple(field.text() for field in dialog._room_fields), fields)
        self.assertEqual(self.window._dev, {})
        self.assertEqual(dialog.tabs.indexOf(dialog._dev_page), -1)
        self.assertEqual((dialog._page_w, dialog._page_h), (450, 375))
        self.assertEqual(self.window._panel_width, 380)
        self.assertEqual(self.window.ctl.properties["volume-max"], 100)
        saved = ConfigStore().data
        for key, value in DEFAULTS["appearance"].items():
            self.assertEqual(saved["appearance"][key], system_language() if key == "language" else value, key)
        self.assertEqual(saved["connection"], room)
        self.assertEqual([call.args[0]["c"] for call in self.app.on_command.call_args_list], ["appearance"])
        dialog.ui_size.setValue(16)
        dialog._preview_theme()
        dialog.reject()
        self.assertEqual(self.store.data, saved)
        self.assertEqual(ConfigStore().data, saved)

    def test_other_reset_restores_defaults_with_dev_hidden(self):
        self.store.data["appearance"].update(devTab=False, dev={"settings_pad": 40, "settings_w": 600})
        self.window._dev = copy.deepcopy(self.store.data["appearance"]["dev"])
        dialog = self.dialog()
        dialog._reset_standard()
        self.assertEqual(dialog._side_layouts[0][0].contentsMargins().left(), 23)
        self.assertEqual((dialog._page_w, dialog._page_h), (450, 375))
        dialog.reject()
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {})

    def test_other_reset_restores_panel_geometry_and_dev_can_be_reopened(self):
        self.store.data["appearance"]["panelWidth"] = 650
        self.window._panel_width = 650
        self.window.set_panel(True)
        self.window.apply_theme()
        self.qt.processEvents()
        self.assertEqual(self.window.panel.width(), 650)
        dialog = self.dialog()
        dialog._reset_standard()
        self.qt.processEvents()
        self.assertEqual(self.window.panel.width(), 380)
        for _ in range(5):
            dialog._logo_pressed()
        self.assertIsNotNone(dialog._dev_page)
        self.assertEqual(self.window._dev, {})
        dialog.gamma_size.setValue(18)
        dialog._accept()
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.assertEqual(ConfigStore().data["appearance"]["dev"], {"gamma": 18})

    def test_standard_font_controls_do_not_create_dev_overrides(self):
        self.window._dev = {"gamma": 18, "ui": {"size": 20, "bold": True}}
        dialog = self.dialog()
        dialog.ui_size.setValue(15)
        dialog._preview_theme()
        self.assertEqual(self.window._dev, {"gamma": 18, "ui": {"bold": True}})
        self.assertEqual(dialog._dev_rows["ui"]["size"].value(), 15)
        dialog.reject()

    def test_gamma_changes_only_settings_and_survives_reopening(self):
        ordinary = copy.deepcopy(self.store.data["appearance"])
        main_size = self.window.font().pointSize()
        content_size = self.window.chat.font().pointSize()
        def edit(dialog):
            form = dialog._dev_rows["titles"]["size"].parentWidget().parentWidget().layout()
            labels = [form.itemAt(row, QFormLayout.ItemRole.LabelRole) for row in range(form.rowCount())]
            names = [item.widget().text() for item in labels if item and hasattr(item.widget(), "text")]
            self.assertEqual(names[names.index("beta text size") + 1], "gamma text size")
            dialog.gamma_size.setValue(20)
            self.qt.processEvents()
            for field in (dialog, dialog.tabs.tabBar(), dialog.port, dialog.theme,
                          dialog.theme.view(), dialog.reset_other, dialog._dev_rows["ui"]["size"]):
                self.assertEqual(field.font().pointSize(), 20)
            self.assertEqual(self.window.font().pointSize(), main_size)
            self.assertEqual(self.window.chat.font().pointSize(), content_size)
            self.assertEqual(self.store.data["appearance"], ordinary)
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        self.app.store = ConfigStore()
        self.app.store.data["appearance"]["devTab"] = False
        restarted = self.make_window()
        dialog = SettingsDialog(self.app.store.data["appearance"], self.app.store.data["connection"], restarted)
        self.assertIsNone(dialog._dev_page)
        self.assertEqual(dialog.port.font().pointSize(), 20)
        dialog.reject()

    def test_settings_defaults_and_layout_use_the_selected_language(self):
        try:
            for language, horizontal, vertical, repository, link, version, gamma in (
                ("English", "Horizontal", "Vertical", "Repository", "GitHub", "Version", "gamma text size"),
                ("Russian", "Горизонтальная", "Вертикальная", "Репозиторий", "гитхаб", "Версия", "Размер текста гамма"),
            ):
                with self.subTest(language=language):
                    i18n.use(language)
                    dialog = self.dialog()
                    dialog.tabs.setCurrentIndex(2)
                    dialog.show()
                    self.qt.processEvents()
                    self.assertEqual(dialog.gamma_size.value(), 10)
                    self.assertEqual(dialog._dev_rows["alfa"]["size"].value(), 10)
                    self.assertEqual(self.window.chat.font().pointSize(), 10)
                    self.assertEqual(dialog.port.font().pointSize(), 10)
                    self.assertEqual(dialog._page_h, 375)
                    self.assertEqual([dialog.overlay.itemText(index) for index in (0, 1)], [horizontal, vertical])
                    form = dialog.reset_other.parentWidget().layout()
                    self.assertEqual(form.getWidgetPosition(dialog.reset_other)[1], QFormLayout.ItemRole.SpanningRole)
                    self.assertEqual(dialog.reset_other.x(), form.contentsMargins().left())
                    self.assertEqual(dialog.reset_other.width(), dialog.reset_other.parentWidget().width()
                                     - form.contentsMargins().left() - form.contentsMargins().right())
                    host = dialog.check_updates.parentWidget()
                    reset_gap = dialog.reset_other.mapTo(dialog, QPoint()).y() - host.mapTo(dialog, QPoint(0, host.height())).y()
                    dialog.tabs.setCurrentIndex(0)
                    self.qt.processEvents()
                    connect_gap = (dialog._connect.mapTo(dialog, QPoint()).y()
                                   - dialog.room_name.mapTo(dialog, QPoint(0, dialog.room_name.height())).y())
                    self.assertEqual(connect_gap, reset_gap)
                    gamma_form = dialog.gamma_size.parentWidget().layout()
                    self.assertEqual(gamma_form.labelForField(dialog.gamma_size).text(), gamma)
                    dialog.tabs.setCurrentWidget(dialog._dev_page)
                    self.qt.processEvents()
                    spin = dialog._dev_rows["ui"]["size"]
                    self.assertGreaterEqual(spin.height(), spin.minimumSizeHint().height())
                    form = dialog.gamma_size.parentWidget().layout()
                    actions = form.itemAt(0, QFormLayout.ItemRole.SpanningRole).widget()
                    reset, export = (actions.layout().itemAt(index).widget() for index in (0, 1))
                    self.assertEqual([reset.text(), export.text()], [i18n.tr(70), i18n.tr(69)])
                    self.assertLessEqual(abs(reset.width() - export.width()), 1)
                    self.assertEqual(reset.x(), 0)
                    self.assertEqual(export.geometry().right(), actions.width() - 1)
                    self.assertEqual(actions.width(), actions.parentWidget().width()
                                     - form.contentsMargins().left() - form.contentsMargins().right())
                    dialog.tabs.setCurrentIndex(3)
                    self.qt.processEvents()
                    about = dialog._about_content
                    texts = [label.text() for label in about.findChildren(QLabel)]
                    self.assertIn(f'{repository}: <a href="https://github.com/yrmuq/yucha">{link}</a>', texts)
                    self.assertIn(f'{version}: {__version__}', texts)
                    thanks = about.layout().itemAt(about.layout().count() - 1).widget()
                    for height in (375, 500):
                        dialog._settings_h.setValue(height)
                        self.qt.processEvents()
                        expected = about.height() - about.layout().contentsMargins().bottom() - 1
                        self.assertLessEqual(abs(thanks.geometry().bottom() - expected), 1)
                    dialog.reject()
                    dialog.hide()
        finally:
            i18n.use("English")

    def test_dev_opens_at_the_right_edge_without_a_spacer_tab(self):
        dialog = self.dialog()
        dialog.show()
        self.qt.processEvents()
        self.assertEqual(dialog.tabs.count(), 5)
        self.assertTrue(all(dialog.tabs.tabText(index) for index in range(dialog.tabs.count())))
        button = dialog.tabs.cornerWidget(Qt.Corner.TopRightCorner)
        self.assertEqual(button.text(), "Dev")
        self.assertEqual(button.geometry().right(), dialog.tabs.width() - 1)
        self.assertEqual(dialog.tabs.tabBar().tabRect(0).left(), 0)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.assertIs(dialog.tabs.currentWidget(), dialog._dev_page)
        self.assertTrue(button.isChecked())
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        self.assertTrue(button.isChecked())
        dialog.tabs.setCurrentIndex(0)
        self.assertFalse(button.isChecked())
        dev_page = dialog._dev_page
        for _ in range(5):
            dialog._logo_pressed()
        self.assertEqual(dialog.tabs.indexOf(dev_page), -1)
        self.assertTrue(button.isHidden())
        for _ in range(5):
            dialog._logo_pressed()
        self.assertIs(dialog.tabs.currentWidget(), dev_page)
        self.assertFalse(button.isHidden())
        self.assertTrue(button.isChecked())
        dialog.reject()

    def test_theme_controls_and_popup_margins_follow_the_active_palette(self):
        dialog = self.dialog()
        dialog.show()
        for theme, field in (("dark", "#1C1E26"), ("light", "#FFFCF7"), ("dark", "#293441")):
            with self.subTest(theme=theme, field=field):
                self.window._dev.setdefault("face", {})["field"] = {theme: field}
                dialog.theme.setCurrentIndex(dialog.theme.findData(theme))
                dialog._flush_theme()
                self.qt.processEvents()
                foreground = QColor(_palette(theme)["fg"])
                for scale in (dialog.chat_size, dialog.ui_size, dialog.sub_size):
                    self.assertEqual(scale.palette().color(QPalette.ColorRole.WindowText), foreground)
                for swatch in (dialog.accent, dialog.accent2, dialog.sub_color):
                    self.assertEqual(swatch.palette().color(QPalette.ColorRole.ButtonText), foreground)
                for combo in (dialog.theme, dialog.style_pick, dialog.sub_font, dialog.language, dialog.overlay):
                    popup = combo.view().window()
                    self.assertEqual(popup.palette().color(QPalette.ColorRole.Window), QColor(field))
                    self.assertEqual(combo.view().palette().color(QPalette.ColorRole.Base), QColor(field))
                dialog.style_pick.showPopup()
                self.qt.processEvents()
                image = dialog.style_pick.view().window().grab().toImage()
                for y in (2, image.height() - 3):
                    self.assertEqual(image.pixelColor(10, y), QColor(field))
                dialog.style_pick.hidePopup()
        dialog.reject()

    def test_saved_sizes_stay_custom_until_dev_reset(self):
        self.window._dev = {"gamma": 17, "alfa": {"size": 18}, "settings_h": 430}
        dialog = self.dialog()
        self.assertEqual(dialog.port.font().pointSize(), 17)
        self.assertEqual(dialog._dev_rows["alfa"]["size"].value(), 18)
        self.assertEqual(dialog._page_h, 430)
        dialog._reset_dev()
        self.qt.processEvents()
        self.assertEqual(dialog.gamma_size.value(), 10)
        self.assertEqual(dialog._dev_rows["alfa"]["size"].value(), 10)
        self.assertEqual(self.window.chat.font().pointSize(), 10)
        self.assertEqual(dialog.port.font().pointSize(), 10)
        self.assertEqual(dialog._page_h, 375)
        dialog.reject()


if __name__ == "__main__":
    unittest.main()
