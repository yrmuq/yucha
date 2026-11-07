# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise the real Qt controls without an mpv engine or a room server."""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "syncplay"))

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QWidget

from yucha.app import App
from yucha.configstore import DEFAULTS, ConfigStore
from yucha.i18n import system_language
from yucha.window import MainWindow, SettingsDialog


class PictureStub(QWidget):
    fullscreenRequested = Signal()
    volumeChanged = Signal(int)
    arrowPressed = Signal(int)
    filesDropped = Signal(list)
    enterPressed = Signal()

    def __init__(self, runtime):
        super().__init__()
        self.error = None
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

    def test_space_pauses_once_when_ready_and_playing(self):
        self.window.ready.setChecked(True)
        self.window.video.setFocus()
        self.qt.processEvents()
        self.window._toggle_ready = Mock()
        QTest.keyClick(self.window.video, Qt.Key.Key_Space)
        self.assertTrue(self.window.ctl.properties["pause"])
        self.assertEqual(self.window.ctl.calls.count(("cycle", "pause")), 1)
        self.window._toggle_ready.assert_not_called()

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
        for level in (0, 1, 9, 10, 99, 100, 130, 8, 99):
            self.window._show_volume(level)
            self.window._refresh_transport()
            self.qt.processEvents()
            self.window._place_overlays()
            self.assertEqual(self.window.volume_pop.geometry(), geometry)

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

    def test_reset_restores_all_dev_defaults_and_is_saved(self):
        self.store.data["appearance"].update({"uiFontSize": 16, "chatFontSize": 20,
                                              "subFontSize": 58, "subColor": "#AABBCC"})
        ordinary = copy.deepcopy(self.store.data["appearance"])
        def edit(dialog):
            dialog._dev_rows["alfa"]["size"].setValue(29)
            dialog._bar_alpha.setValue(12)
            dialog._bar_buttons["volume"].setChecked(False)
            dialog._reset_dev()
            self.expected_defaults = dialog._dev_defaults()
            self.assertEqual(dialog._dev_spec(), self.expected_defaults)
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        self.app.store = ConfigStore()
        restarted = self.make_window()
        self.assertEqual(restarted._dev, self.expected_defaults)
        for key in ("uiFontSize", "chatFontSize", "subFontSize", "subColor"):
            self.assertEqual(self.app.store.data["appearance"][key], ordinary[key])

    def test_other_reset_saves_defaults_without_changing_room_or_dev(self):
        self.store.data["appearance"].update({
            "theme": "light", "style": "classic", "accentColor": "#123456",
            "accentColor2": "#ABCDEF", "chatColor": "#010203", "uiFontSize": 16,
            "chatFontSize": 20, "subFontSize": 58, "subFont": "serif", "subColor": "#AABBCC",
            "autoplayNext": True, "fastforwardOnDesync": False, "slowOnDesync": False,
            "panelWidth": 650, "volumeOverlay": "vertical"})
        self.window._dev = {"gamma": 18, "ui": {"size": 15}, "panel": 650,
                            "osd": {"size": 22}, "sub": {"size": 57}}
        self.window.apply_theme()
        dev = copy.deepcopy(self.window._dev)
        room = copy.deepcopy(self.store.data["connection"])
        self.app.on_command = Mock(wraps=self.app.on_command)

        def edit(dialog):
            fields = tuple(field.text() for field in dialog._room_fields)
            dialog.reset_other.click()
            self.assertEqual(tuple(field.text() for field in dialog._room_fields), fields)
            self.assertEqual(self.window._dev, dev)
            dialog._accept()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsDialog, "exec", edit):
            self.window._open_settings()
        saved = ConfigStore().data
        for key, value in DEFAULTS["appearance"].items():
            if key not in ("dev", "devTab"):
                self.assertEqual(saved["appearance"][key], system_language() if key == "language" else value, key)
        self.assertEqual(saved["appearance"]["dev"], dev)
        self.assertTrue(saved["appearance"]["devTab"])
        self.assertEqual(saved["connection"], room)
        self.assertEqual([call.args[0]["c"] for call in self.app.on_command.call_args_list], ["appearance"])
        self.assertEqual(self.window.ctl.properties["volume-max"], 100)

    def test_cancel_undoes_both_resets(self):
        self.store.data["appearance"].update({"style": "classic", "uiFontSize": 16})
        self.window._dev = {"gamma": 19, "bar": 70}
        self.window.apply_theme()
        self.store.data["appearance"]["dev"] = copy.deepcopy(self.window._dev)
        self.store.save()
        before = copy.deepcopy(self.store.data)
        dialog = self.dialog()
        dialog._reset_standard()
        dialog._reset_dev()
        dialog.reject()
        self.assertEqual(self.store.data, before)
        self.assertEqual(self.window._dev, before["appearance"]["dev"])
        self.assertEqual(ConfigStore().data, before)

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


if __name__ == "__main__":
    unittest.main()
