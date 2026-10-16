# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""The yucha window. Fields and buttons are real widgets. mpv only draws
the picture into the video area."""

import time

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from yucha.engine import Picture

HIDE_AFTER = 3.0
CHAT_LIFE = 5.0
READY_LIFE = 2.0
VOLUME_LIFE = 2.0
PANEL_WIDTH = 380
BAR_HEIGHT = 72


def _palette(theme):
    if theme == "light":
        return {
            "bg": "#F7F4EE",
            "fg": "#1A1A1A",
            "muted": "#5C584F",
            "field": "#FFFCF7",
            "border": "#D9D3C7",
            "button": "#E7E1D6",
            "button_fg": "#1A1A1A",
            "on_fg": "#F7F4EE",
            "accent": "#8A5A12",
            "bad": "#9C3B3B",
        }
    return {
        "bg": "#12141A",
        "fg": "#F3EFE6",
        "muted": "#9A958C",
        "field": "#1C1E26",
        "border": "#34363F",
        "button": "#2C303A",
        "button_fg": "#F3EFE6",
        "on_fg": "#1A1408",
        "accent": "#E0A045",
        "bad": "#E07474",
    }


def _stylesheet(theme):
    p = _palette(theme)
    return """
    QMainWindow, QDialog, QWidget#root, QWidget#stage, QWidget#panel, QWidget#bar, QWidget#volume, QScrollArea, QLabel {{
        background: {bg};
        color: {fg};
    }}
    QLineEdit, QTextEdit, QSpinBox, QComboBox {{
        background: {field};
        color: {fg};
        border: 1px solid {border};
        padding: 6px;
        selection-background-color: {accent};
    }}
    QPushButton {{
        background: {button};
        color: {button_fg};
        border: none;
        padding: 8px 14px;
    }}
    QPushButton:checked {{
        background: {accent};
        color: {on_fg};
    }}
    QLabel#muted {{ color: {muted}; }}
    QWidget#bar {{ border-top: 1px solid {border}; }}
    QWidget#panel {{ border-left: 1px solid {border}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background: {bg};
        border: none;
    }}
    QSlider::groove:horizontal {{ height: 6px; background: {border}; }}
    QSlider::sub-page:horizontal {{ background: {accent}; }}
    QSlider::handle:horizontal {{
        background: {fg};
        width: 14px;
        margin: -6px 0;
        border-radius: 7px;
    }}
    """.format(**p)


def _clock(seconds):
    seconds = int(seconds or 0)
    if seconds < 0:
        seconds = 0
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{}:{:02d}".format(minutes, secs)


def _ass_escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
    )


def _bgr(hex_color):
    color = str(hex_color or "#F4F1EA").lstrip("#")
    if len(color) != 6:
        color = "F4F1EA"
    return color[4:6] + color[2:4] + color[0:2]


class SettingsDialog(QDialog):
    def __init__(self, appearance, parent):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.values = None
        layout = QFormLayout(self)
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        current = appearance.get("theme") or "dark"
        self.theme.setCurrentIndex(0 if current != "light" else 1)
        self.color = QLineEdit(str(appearance.get("chatColor") or "#F4F1EA"))
        self.chat_size = QSpinBox()
        self.chat_size.setRange(12, 48)
        self.chat_size.setValue(int(appearance.get("chatFontSize") or 18))
        self.ui_size = QSpinBox()
        self.ui_size.setRange(12, 32)
        self.ui_size.setValue(int(appearance.get("uiFontSize") or 16))
        layout.addRow("Theme", self.theme)
        layout.addRow("Chat color", self.color)
        layout.addRow("Chat size", self.chat_size)
        layout.addRow("Interface size", self.ui_size)
        buttons = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addRow(buttons)

    def _accept(self):
        color = self.color.text().strip()
        if len(color) != 7 or not color.startswith("#"):
            color = "#F4F1EA"
        self.values = {
            "theme": self.theme.currentData(),
            "chatColor": color,
            "chatFontSize": self.chat_size.value(),
            "uiFontSize": self.ui_size.value(),
        }
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ctl = None
        self._bridge_pos = 0
        self._osd = []
        self._connected = False
        self._said_connected = False
        self._duration = 0
        self._last_move = time.monotonic()
        self._last_cursor = QPoint(-1, -1)
        self._panel_open = False
        self._bar_open = True
        self._users = []
        self._ready_until = {}
        self._volume_until = 0
        self.setWindowTitle("yucha")
        self.resize(1280, 720)
        self.setMinimumSize(860, 520)
        self._build()
        self._fill_from_store()
        self.apply_theme()
        self.set_panel(not app.store.has_connection())
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._tick)
        self._ui_timer.start()

    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        column = QWidget()
        column.setObjectName("stage")
        self.stage = column
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.video = Picture(self.app.runtime)
        self.video.fullscreenRequested.connect(self._toggle_full)
        self.video.volumeChanged.connect(self._show_volume)
        col.addWidget(self.video, 1)

        self.bar = QWidget(column)
        self.bar.setObjectName("bar")
        self._overlay(self.bar)
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(10, 8, 10, 8)
        self.play = QPushButton("Play")
        self.elapsed = QLabel("0:00")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.total = QLabel("0:00")
        self.loop = QPushButton("Loop")
        self.loop.setCheckable(True)
        self.full = QPushButton("Full")
        self.full.setCheckable(True)
        self.room = QPushButton("Room")
        self.room.setCheckable(True)
        self.play.clicked.connect(self._toggle_pause)
        self.slider.sliderReleased.connect(self._seek_released)
        self.loop.clicked.connect(self._toggle_loop)
        self.full.clicked.connect(self._toggle_full)
        self.room.clicked.connect(self._toggle_room)
        for widget in (self.play, self.elapsed, self.slider, self.total, self.loop, self.full, self.room):
            bar.addWidget(widget)
        bar.setStretchFactor(self.slider, 1)

        self.volume_box = QWidget(column)
        self.volume_box.setObjectName("volume")
        self._overlay(self.volume_box)
        self.volume_box.hide()
        volume_row = QHBoxLayout(self.volume_box)
        volume_row.setContentsMargins(12, 8, 12, 8)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume_text = QLabel("0")
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_text)

        row.addWidget(column, 1)

        self.panel = QWidget(column)
        self.panel.setObjectName("panel")
        self._overlay(self.panel)
        side = QVBoxLayout(self.panel)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Room")
        header.addWidget(title)
        header.addStretch(1)
        settings = QPushButton("Settings")
        settings.clicked.connect(self._open_settings)
        header.addWidget(settings)
        side.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setContentsMargins(0, 0, 0, 0)
        self.host = QLineEdit()
        self.port = QLineEdit()
        self.name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.room_name = QLineEdit()
        for label, field in (
            ("Server", self.host),
            ("Port", self.port),
            ("Username", self.name),
            ("Password", self.password),
            ("Room", self.room_name),
        ):
            form.addRow(label, field)
            field.returnPressed.connect(self._submit)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._submit)
        form.addRow(self.connect_btn)
        hint = QLabel("Drop a video on the picture.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form.addRow(hint)
        scroll.setWidget(form_host)
        side.addWidget(scroll, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        side.addWidget(self.status)

        message_row = QHBoxLayout()
        self.message = QLineEdit()
        self.message.setPlaceholderText("Message")
        self.message.returnPressed.connect(self._send_chat)
        send = QPushButton("Send")
        send.clicked.connect(self._send_chat)
        message_row.addWidget(self.message, 1)
        message_row.addWidget(send)
        side.addLayout(message_row)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        side.addWidget(self.chat, 1)
        self.stage.installEventFilter(self)
        self._place_overlays()

    def _overlay(self, widget):
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        widget.setAutoFillBackground(True)

    def eventFilter(self, watched, event):
        if watched is self.stage and event.type() == QEvent.Type.Resize:
            self._place_overlays()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._place_overlays()

    def _place_overlays(self):
        if not hasattr(self, "panel"):
            return
        width = self.stage.width()
        height = self.stage.height()
        self.bar.setGeometry(0, max(0, height - BAR_HEIGHT), width, BAR_HEIGHT)
        panel_height = max(0, height - BAR_HEIGHT)
        if self._panel_open:
            panel_width = min(PANEL_WIDTH, width)
            self.panel.setGeometry(max(0, width - panel_width), 0, panel_width, panel_height)
            self.panel.show()
        else:
            self.panel.hide()
        box_width, box_height = 280, 48
        self.volume_box.setGeometry(
            max(0, (width - box_width) // 2),
            max(0, height - BAR_HEIGHT - 90),
            min(box_width, width),
            box_height,
        )
        self.bar.raise_()
        self.panel.raise_()
        self.volume_box.raise_()

    def _fill_from_store(self):
        conn = self.app.store.data["connection"]
        self.host.setText(str(conn.get("host") or "syncplay.pl"))
        self.port.setText(str(conn.get("port") or 8999))
        self.name.setText(str(conn.get("name") or ""))
        self.password.setText(str(conn.get("password") or ""))
        self.room_name.setText(str(conn.get("room") or ""))

    def apply_theme(self):
        appearance = self.app.store.data["appearance"]
        theme = appearance.get("theme") or "dark"
        self.setStyleSheet(_stylesheet(theme))
        size = int(appearance.get("uiFontSize") or 16)
        font = QFont()
        font.setPointSize(max(10, min(28, size)))
        QApplication.instance().setFont(font)

    def set_player(self, player):
        listener = getattr(player, "_listener", None) if player is not None else None
        self.ctl = getattr(listener, "mpvpipe", None)

    def set_panel(self, open_, animate=True):
        was_open = self._panel_open
        self._panel_open = bool(open_)
        self.room.setChecked(self._panel_open)
        if self._panel_open:
            self._bar_open = True
            self.bar.show()
        elif was_open:
            self._last_move = time.monotonic()
        self._place_overlays()

    def _toggle_room(self):
        self.set_panel(not self._panel_open)

    def _set_bar(self, open_):
        if self._panel_open:
            open_ = True
        if open_ == self._bar_open:
            return
        self._bar_open = open_
        self.bar.setVisible(open_)

    def _show_volume(self, level):
        level = max(0, min(100, int(level)))
        self.volume.setValue(level)
        self.volume_text.setText(str(level))
        self._volume_until = time.monotonic() + VOLUME_LIFE
        self.volume_box.show()
        self.volume_box.raise_()

    def _toggle_pause(self):
        self._cmd("cycle", "pause")

    def _toggle_loop(self):
        current = self._get("loop-file")
        on = current in ("inf", "yes", "always")
        self._set("loop-file", "no" if on else "inf")
        self.loop.setChecked(not on)

    def _toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self.full.setChecked(self.isFullScreen())

    def _seek_released(self):
        if self._duration <= 0:
            return
        at = self._duration * (self.slider.value() / 1000.0)
        self._cmd("seek", str(at), "absolute")

    def _submit(self):
        self.app.on_command({
            "c": "connect",
            "host": self.host.text(),
            "port": self.port.text(),
            "name": self.name.text(),
            "password": self.password.text(),
            "room": self.room_name.text(),
        })

    def _send_chat(self):
        text = self.message.text().strip()
        if not text:
            return
        self.app.on_command({"c": "chat", "text": text})
        self.message.clear()

    def _open_settings(self):
        dialog = SettingsDialog(self.app.store.data["appearance"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.values:
            return
        self.app.on_command({"c": "appearance", **dialog.values})
        self.apply_theme()

    def _get(self, name):
        if not self.ctl:
            return None
        try:
            return self.ctl.command("get_property", name)
        except Exception:
            return None

    def _set(self, name, value):
        if not self.ctl:
            return
        try:
            self.ctl.command("set_property", name, value)
        except Exception:
            pass

    def _cmd(self, *args):
        if not self.ctl:
            return
        try:
            self.ctl.command(*args)
        except Exception:
            pass

    def _tick(self):
        if self.video.error and self.status.text() != self.video.error:
            self.status.setText(self.video.error)
        self._follow_cursor()
        if self.volume_box.isVisible() and time.monotonic() >= self._volume_until:
            self.volume_box.hide()
        self._read_events()
        self._refresh_transport()
        self._refresh_osd()

    def _follow_cursor(self):
        pos = QCursor.pos()
        inside = self.rect().contains(self.mapFromGlobal(pos))
        if inside and pos != self._last_cursor:
            self._last_cursor = pos
            self._last_move = time.monotonic()
        over_bar = self.bar.rect().contains(self.bar.mapFromGlobal(pos))
        show = over_bar or (time.monotonic() - self._last_move) < HIDE_AFTER
        self._set_bar(show)

    def _read_events(self):
        events, self._bridge_pos = self.app.bridge.read_new(self._bridge_pos)
        for event in events:
            kind = event.get("e")
            if kind == "conn":
                self._on_conn(event)
            elif kind == "chat":
                self._add_chat(event.get("user") or "", event.get("text") or "")
            elif kind == "chat-local":
                self._add_chat("", event.get("text") or "")
            elif kind == "users":
                self._on_users(event)

    def _on_conn(self, event):
        state = event.get("state") or ""
        text = event.get("text") or ""
        self._connected = state == "connected"
        self.status.setText(text)
        pal = _palette(self.app.store.data["appearance"].get("theme"))
        if state == "failed":
            color = pal["bad"]
            self._said_connected = False
        elif state == "connected":
            color = pal["accent"]
            self._said_connected = True
        else:
            color = pal["muted"]
        self.status.setStyleSheet("color: {};".format(color))
        if event.get("openPanel"):
            self.set_panel(True)

    def _on_users(self, event):
        now = time.monotonic()
        people = []
        ready_names = set()
        for person in event.get("list") or []:
            name = str(person.get("name") or "")
            if not name:
                continue
            ready = bool(person.get("ready"))
            people.append((name, ready))
            if ready:
                ready_names.add(name)
                if name not in self._ready_until:
                    self._ready_until[name] = now + READY_LIFE
            else:
                self._ready_until.pop(name, None)
        for name in list(self._ready_until):
            if name not in ready_names:
                self._ready_until.pop(name, None)
        self._users = people

    def _add_chat(self, user, text):
        if not text:
            return
        line = text if not user else "{}: {}".format(user, text)
        self.chat.append(line)
        self._osd.append((time.monotonic(), line))

    def _refresh_transport(self):
        paused = self._get("pause")
        if paused is not None:
            self.play.setText("Play" if paused else "Pause")
        duration = self._get("duration")
        position = self._get("time-pos")
        try:
            self._duration = float(duration or 0)
        except (TypeError, ValueError):
            self._duration = 0
        try:
            position = float(position or 0)
        except (TypeError, ValueError):
            position = 0
        if not self.slider.isSliderDown() and self._duration > 0:
            self.slider.setValue(int(max(0, min(1000, position / self._duration * 1000))))
        if self.slider.isSliderDown() and self._duration > 0:
            shown = self._duration * (self.slider.value() / 1000.0)
        else:
            shown = position
        self.elapsed.setText(_clock(shown))
        self.total.setText(_clock(self._duration))
        loop = self._get("loop-file")
        self.loop.setChecked(loop in ("inf", "yes", "always"))

    def _refresh_osd(self):
        if not self.ctl:
            return
        now = time.monotonic()
        self._osd = [(born, line) for born, line in self._osd if now - born < CHAT_LIFE]
        appearance = self.app.store.data["appearance"]
        point = int(appearance.get("chatFontSize") or 18)
        measure = QFont(self.font())
        measure.setPointSize(max(10, min(48, point)))
        size = max(14, QFontMetrics(measure).height())
        color = _bgr(appearance.get("chatColor"))
        # Logical window pixels, not the 4K frame. The text then matches the
        # size of the text in the window.
        width = max(1, self.video.width())
        height = max(1, self.video.height())
        people = []
        for name, ready in self._users:
            if ready and now >= self._ready_until.get(name, 0):
                continue
            people.append((name, ready))
        lines = []
        step = size + 8
        block = len(people) + len(self._osd)
        y = max(24, int(height / 2) - block * step // 2)
        floor = max(24, height - BAR_HEIGHT - 16)
        for name, ready in people:
            if y > floor:
                break
            dot = "00FF00" if ready else "0000FF"
            lines.append(
                "{{\\pos({},{})\\an6\\bord1\\shad0\\fs{}\\1c&H{}&}}{{\\1c&H{}&}}● {{\\1c&H{}&}}{}".format(
                    max(20, width - 24), y, size, color, dot, color, _ass_escape(name)
                )
            )
            y += step
        for _born, line in self._osd:
            if y > floor:
                break
            lines.append(
                "{{\\pos({},{})\\an6\\bord1\\shad0\\fs{}\\1c&H{}&}}{}".format(
                    max(20, width - 24), y, size, color, _ass_escape(line)
                )
            )
            y += step
        if self._connected:
            lines.append(
                "{{\\pos({},{})\\an9\\bord1\\shad0\\fs{}\\1c&H{}&}}{}".format(
                    max(20, width - 16), floor, size, color, "connected"
                )
            )
        data = "\n".join(lines)
        if data == getattr(self, "_osd_sent", None):
            return
        self._osd_sent = data
        try:
            self.ctl.command(
                "osd-overlay",
                1,
                "ass-events" if data else "none",
                data,
                int(width),
                int(height),
                0,
            )
        except Exception:
            pass

    def closeEvent(self, event):
        self._ui_timer.stop()
        self.video.shutdown()
        event.accept()
        QApplication.instance().quit()
