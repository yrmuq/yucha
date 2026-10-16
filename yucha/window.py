# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""The yucha window. Fields and buttons are real widgets. mpv only draws
the picture into the video area."""

import re
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
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
CHAT_EXTRA = 52
SEEK_STEPS = 100000
CHAT_BOX = 300


def _palette(theme, accent=None):
    if theme == "light":
        pal = {
            "bg": "#F7F4EE",
            "fg": "#1A1A1A",
            "muted": "#5C584F",
            "field": "#FFFCF7",
            "border": "#D9D3C7",
            "button": "#E7E1D6",
            "button_fg": "#1A1A1A",
            "on_fg": "#F7F4EE",
            "accent": "#7A2438",
            "bad": "#9C3B3B",
        }
    else:
        pal = {
            "bg": "#12141A",
            "fg": "#F3EFE6",
            "muted": "#9A958C",
            "field": "#1C1E26",
            "border": "#34363F",
            "button": "#2C303A",
            "button_fg": "#F3EFE6",
            "on_fg": "#F7F4EE",
            "accent": "#9A3A52",
            "bad": "#E07474",
        }
    if isinstance(accent, str) and len(accent) == 7 and accent.startswith("#"):
        pal["accent"] = accent
    return pal


def _stylesheet(theme, accent=None):
    p = _palette(theme, accent)
    return """
    QMainWindow, QDialog, QWidget#root, QWidget#stage, QWidget#panel, QWidget#bar, QWidget#chatline, QWidget#volume, QLabel {{
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
    QWidget#bar, QWidget#chatline {{ border-top: 1px solid {border}; }}
    QWidget#panel {{ border-left: 1px solid {border}; }}
    QWidget#banner {{
        background: {field};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QWidget#banner QLabel {{ background: transparent; }}
    QPushButton#icon {{
        padding: 0px;
        min-width: 40px;
        max-width: 40px;
        min-height: 36px;
        max-height: 36px;
    }}
    QSlider::groove:horizontal {{ height: 6px; background: {border}; }}
    QSlider::sub-page:horizontal {{ background: {accent}; }}
    QSlider::handle:horizontal {{
        background: {fg};
        width: 14px;
        height: 14px;
        margin: -4px 0;
        border-radius: 7px;
    }}
    QListWidget {{
        background: {field};
        color: {fg};
        border: 1px solid {border};
    }}
    QListWidget::item {{
        padding: 4px 6px;
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


def _natural(text):
    parts = re.split(r"(\d+)", str(text).lower())
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        elif part:
            key.append(part)
    return key


def _chunks(word, metrics, width):
    if metrics.horizontalAdvance(word) <= width:
        return [word]
    pieces = []
    buf = ""
    for char in word:
        trial = buf + char
        if buf and metrics.horizontalAdvance(trial) > width:
            pieces.append(buf)
            buf = char
        else:
            buf = trial
    if buf:
        pieces.append(buf)
    return pieces or [word]


def _wrap_plain(text, metrics, first_width, width):
    words = str(text).split()
    if not words:
        return [""]
    lines = []
    current = ""
    limit = first_width
    for word in words:
        for piece in _chunks(word, metrics, width):
            trial = piece if not current else current + " " + piece
            if current and metrics.horizontalAdvance(trial) > limit:
                lines.append(current)
                current = piece
                limit = width
            else:
                current = trial
    if current:
        lines.append(current)
    return lines


class FileList(QListWidget):
    """The episode list. A right click removes a row."""

    removed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            item = self.itemAt(event.position().toPoint())
            if item is not None:
                self.removed.emit(item.data(Qt.ItemDataRole.UserRole) or "")
            event.accept()
            return
        super().mousePressEvent(event)


class SeekBar(QSlider):
    """A click anywhere on the bar jumps to that moment."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._jump(event.position().x())
            self.setSliderDown(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self._jump(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self._jump(event.position().x())
            self.setSliderDown(False)
            self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _jump(self, x):
        span = max(1, self.width() - 1)
        ratio = min(1.0, max(0.0, float(x) / span))
        value = int(round(self.minimum() + ratio * (self.maximum() - self.minimum())))
        self.setValue(value)


class IconButton(QPushButton):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self._ink = QColor("#F3EFE6")
        self._ink_on = QColor("#F7F4EE")
        self.setObjectName("icon")
        self.setFixedSize(40, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_kind(self, kind):
        if self.kind != kind:
            self.kind = kind
            self.update()

    def set_ink(self, ink, ink_on):
        self._ink = QColor(ink)
        self._ink_on = QColor(ink_on)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = self._ink_on if self.isChecked() else self._ink
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx = self.width() / 2
        cy = self.height() / 2
        kind = self.kind
        if kind == "play":
            painter.setBrush(color)
            path = QPainterPath()
            path.moveTo(cx - 5, cy - 7)
            path.lineTo(cx - 5, cy + 7)
            path.lineTo(cx + 8, cy)
            path.closeSubpath()
            painter.drawPath(path)
        elif kind == "pause":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(int(cx - 6), int(cy - 7), 4, 14, 1, 1)
            painter.drawRoundedRect(int(cx + 2), int(cy - 7), 4, 14, 1, 1)
        elif kind == "loop":
            painter.drawArc(int(cx - 7), int(cy - 7), 14, 14, 50 * 16, 280 * 16)
            painter.setBrush(color)
            path = QPainterPath()
            path.moveTo(cx + 6, cy - 6)
            path.lineTo(cx + 6, cy - 1)
            path.lineTo(cx + 1, cy - 6)
            path.closeSubpath()
            painter.drawPath(path)
        elif kind == "chat":
            painter.drawRoundedRect(int(cx - 8), int(cy - 6), 16, 11, 2, 2)
            path = QPainterPath()
            path.moveTo(cx - 3, cy + 5)
            path.lineTo(cx - 6, cy + 8)
            path.lineTo(cx + 1, cy + 5)
            painter.drawPath(path)
        elif kind == "room":
            painter.drawRoundedRect(int(cx - 8), int(cy - 7), 16, 14, 2, 2)
            painter.drawLine(QPointF(cx + 3, cy - 7), QPointF(cx + 3, cy + 7))
        elif kind == "send":
            painter.setBrush(color)
            path = QPainterPath()
            path.moveTo(cx - 7, cy + 4)
            path.lineTo(cx + 7, cy - 6)
            path.lineTo(cx + 1, cy + 6)
            path.lineTo(cx - 1, cy + 1)
            path.closeSubpath()
            painter.drawPath(path)
        elif kind == "gear":
            painter.drawEllipse(QPointF(cx, cy), 3.2, 3.2)
            for step in range(8):
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(step * 45)
                painter.drawLine(QPointF(0, -5.2), QPointF(0, -7.4))
                painter.restore()
        painter.end()


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
        self.accent = QLineEdit(str(appearance.get("accentColor") or "#9A3A52"))
        self.chat_size = QSpinBox()
        self.chat_size.setRange(12, 48)
        self.chat_size.setValue(int(appearance.get("chatFontSize") or 18))
        self.ui_size = QSpinBox()
        self.ui_size.setRange(12, 32)
        self.ui_size.setValue(int(appearance.get("uiFontSize") or 16))
        layout.addRow("Theme", self.theme)
        layout.addRow("Chat color", self.color)
        layout.addRow("Accent color", self.accent)
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
        accent = self.accent.text().strip()
        if len(accent) != 7 or not accent.startswith("#"):
            accent = "#9A3A52"
        self.values = {
            "theme": self.theme.currentData(),
            "chatColor": color,
            "accentColor": accent,
            "chatFontSize": self.chat_size.value(),
            "uiFontSize": self.ui_size.value(),
        }
        self.accept()


class ConnectionDialog(QDialog):
    def __init__(self, connection, parent):
        super().__init__(parent)
        self.setWindowTitle("Connection")
        self.setModal(True)
        self.values = None
        layout = QFormLayout(self)
        self.host = QLineEdit(str(connection.get("host") or "syncplay.pl"))
        self.port = QLineEdit(str(connection.get("port") or 8999))
        self.name = QLineEdit(str(connection.get("name") or ""))
        self.password = QLineEdit(str(connection.get("password") or ""))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.room_name = QLineEdit(str(connection.get("room") or ""))
        for label, field in (
            ("Server", self.host),
            ("Port", self.port),
            ("Username", self.name),
            ("Password", self.password),
            ("Room", self.room_name),
        ):
            layout.addRow(label, field)
            field.returnPressed.connect(self._accept)
        buttons = QHBoxLayout()
        connect = QPushButton("Connect")
        cancel = QPushButton("Cancel")
        connect.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(connect)
        buttons.addWidget(cancel)
        layout.addRow(buttons)

    def _accept(self):
        self.values = {
            "host": self.host.text(),
            "port": self.port.text(),
            "name": self.name.text(),
            "password": self.password.text(),
            "room": self.room_name.text(),
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
        self._failed = False
        self._chat_open = False
        self._duration = 0
        self._last_move = time.monotonic()
        self._last_cursor = QPoint(-1, -1)
        self._panel_open = False
        self._bar_open = True
        self._users = []
        self._ready_until = {}
        self._pos_at = 0.0
        self._pos_when = time.monotonic()
        self._speed = 1.0
        self._paused = True
        self._playlist = []
        self._current_path = ""
        self._eof_seen = False
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
        self._knob_timer = QTimer(self)
        self._knob_timer.setInterval(33)
        self._knob_timer.timeout.connect(self._move_knob)
        self._knob_timer.start()

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
        self.video.filesDropped.connect(self._add_dropped)
        col.addWidget(self.video, 1)

        self.bar = QWidget(column)
        self.bar.setObjectName("bar")
        self._overlay(self.bar)
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(10, 8, 10, 8)
        self.play = IconButton("play")
        self.elapsed = QLabel("0:00")
        self.slider = SeekBar(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SEEK_STEPS)
        self.total = QLabel("0:00")
        self.loop = IconButton("loop")
        self.loop.setCheckable(True)
        self.chat_btn = IconButton("chat")
        self.chat_btn.setCheckable(True)
        self.room = IconButton("room")
        self.room.setCheckable(True)
        self.play.clicked.connect(self._toggle_pause)
        self.slider.sliderReleased.connect(self._seek_released)
        self.loop.clicked.connect(self._toggle_loop)
        self.chat_btn.clicked.connect(self._toggle_chat_field)
        self.room.clicked.connect(self._toggle_room)
        for widget in (self.play, self.elapsed, self.slider, self.total, self.loop, self.chat_btn, self.room):
            bar.addWidget(widget)
        bar.setStretchFactor(self.slider, 1)

        self.chat_line = QWidget(column)
        self.chat_line.setObjectName("chatline")
        self._overlay(self.chat_line)
        self.chat_line.hide()
        chat_row = QHBoxLayout(self.chat_line)
        chat_row.setContentsMargins(10, 6, 10, 6)
        self.bar_message = QLineEdit()
        self.bar_message.setPlaceholderText("Message")
        self.bar_message.returnPressed.connect(self._send_bar_chat)
        self.bar_send = IconButton("send")
        self.bar_send.clicked.connect(self._send_bar_chat)
        chat_row.addWidget(self.bar_message, 1)
        chat_row.addWidget(self.bar_send)

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
        title = QLabel("Panel")
        header.addWidget(title)
        header.addStretch(1)
        settings = QPushButton("Settings")
        settings.clicked.connect(self._open_settings)
        header.addWidget(settings)
        side.addLayout(header)

        banner_row = QHBoxLayout()
        banner_row.setSpacing(8)
        self.banner = QWidget()
        self.banner.setObjectName("banner")
        self.banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.banner.setAutoFillBackground(True)
        self.banner.setFixedHeight(44)
        inside = QHBoxLayout(self.banner)
        inside.setContentsMargins(14, 0, 14, 0)
        self.banner_text = QLabel("Not configured")
        self.banner_dot = QLabel("●")
        inside.addWidget(self.banner_text)
        inside.addStretch(1)
        inside.addWidget(self.banner_dot)
        self.gear = IconButton("gear")
        self.gear.clicked.connect(self._open_connection)
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(self.gear)
        side.addLayout(banner_row)

        self.reconnect = QPushButton("Reconnect")
        self.reconnect.clicked.connect(self._reconnect)
        self.reconnect.hide()
        side.addWidget(self.reconnect)

        self.files = FileList()
        self.files.removed.connect(self._remove_file)
        side.addWidget(self.files, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        side.addWidget(self.status)

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
        inset = BAR_HEIGHT
        self.bar.setGeometry(0, max(0, height - inset), width, inset)
        panel_width = min(PANEL_WIDTH, width) if self._panel_open else 0
        panel_height = max(0, height - inset)
        if self._panel_open:
            self.panel.setGeometry(max(0, width - panel_width), 0, panel_width, panel_height)
            self.panel.show()
        else:
            self.panel.hide()
        if self._chat_open:
            self.chat_line.setGeometry(
                0,
                max(0, height - inset - CHAT_EXTRA),
                max(0, width - panel_width),
                CHAT_EXTRA,
            )
            self.chat_line.show()
        else:
            self.chat_line.hide()
        box_width, box_height = 280, 48
        self.volume_box.setGeometry(
            max(0, (width - box_width) // 2),
            max(0, height - inset - 90),
            min(box_width, width),
            box_height,
        )
        self.bar.raise_()
        self.chat_line.raise_()
        self.panel.raise_()
        self.volume_box.raise_()

    def _bar_height(self):
        return BAR_HEIGHT

    def _fill_from_store(self):
        self._refresh_banner()

    def apply_theme(self):
        appearance = self.app.store.data["appearance"]
        theme = appearance.get("theme") or "dark"
        accent = appearance.get("accentColor")
        self.setStyleSheet(_stylesheet(theme, accent))
        size = int(appearance.get("uiFontSize") or 16)
        font = QFont()
        font.setPointSize(max(10, min(28, size)))
        QApplication.instance().setFont(font)
        pal = _palette(theme, appearance.get("accentColor"))
        for button in (self.play, self.loop, self.chat_btn, self.room, self.gear, self.bar_send):
            button.set_ink(pal["button_fg"], pal["on_fg"])
        self._refresh_banner()
        self._refresh_files()

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
        if self._panel_open or self._chat_open:
            open_ = True
        if open_ == self._bar_open:
            return
        self._bar_open = open_
        self.bar.setVisible(open_)
        self._place_overlays()

    def _toggle_chat_field(self):
        self._chat_open = not self._chat_open
        self.chat_btn.setChecked(self._chat_open)
        if self._chat_open:
            self._set_bar(True)
            self.bar_message.setFocus()
        else:
            self._last_move = time.monotonic()
        self._place_overlays()

    def _show_volume(self, level):
        level = max(0, min(100, int(level)))
        self.volume.setValue(level)
        self.volume_text.setText(str(level))
        self._volume_until = time.monotonic() + VOLUME_LIFE
        self.volume_box.show()
        self.volume_box.raise_()

    def _toggle_pause(self):
        eof = self._get("eof-reached")
        if eof in (True, "yes", "true", 1) and len(self._playlist) == 1:
            self._cmd("seek", "0", "absolute")
            self._set("pause", "no")
            self._paused = False
            self._pos_at = 0
            self._pos_when = time.monotonic()
            self._eof_seen = True
            return
        self._cmd("cycle", "pause")

    def _add_dropped(self, paths):
        dropped = []
        known = {item["path"] for item in self._playlist}
        for path in paths:
            if not path:
                continue
            dropped.append(path)
            if path not in known:
                self._playlist.append({"path": path, "name": Path(path).name})
                known.add(path)
        self._playlist.sort(key=lambda item: _natural(item["name"]))
        if not dropped:
            self._refresh_files()
            return
        wanted = set(dropped)
        start = next((item["path"] for item in self._playlist if item["path"] in wanted), "")
        if start:
            self._play_path(start)
        else:
            self._refresh_files()

    def _play_path(self, path):
        self._current_path = path
        self._eof_seen = True
        self._paused = False
        self._pos_at = 0
        self._pos_when = time.monotonic()
        if self.video.mpv is not None:
            try:
                self.video.mpv.command("loadfile", path, "replace", "start=0")
            except Exception:
                pass
        self._refresh_files()

    def _remove_file(self, path):
        if not path:
            return
        was_current = path == self._current_path
        index = next((i for i, item in enumerate(self._playlist) if item["path"] == path), -1)
        self._playlist = [item for item in self._playlist if item["path"] != path]
        if not was_current:
            self._refresh_files()
            return
        if not self._playlist:
            self._current_path = ""
            self._cmd("stop")
            self._refresh_files()
            return
        nxt = min(max(index, 0), len(self._playlist) - 1)
        self._play_path(self._playlist[nxt]["path"])

    def _advance(self):
        if len(self._playlist) <= 1:
            return
        index = next((i for i, item in enumerate(self._playlist) if item["path"] == self._current_path), -1)
        if index < 0 or index + 1 >= len(self._playlist):
            return
        self._play_path(self._playlist[index + 1]["path"])

    def _refresh_files(self):
        if not hasattr(self, "files"):
            return
        appearance = self.app.store.data["appearance"]
        pal = _palette(appearance.get("theme"), appearance.get("accentColor"))
        self.files.clear()
        for item in self._playlist:
            row = QListWidgetItem(item["name"])
            row.setData(Qt.ItemDataRole.UserRole, item["path"])
            if item["path"] == self._current_path:
                row.setBackground(QColor(pal["accent"]))
                row.setForeground(QColor(pal["on_fg"]))
            self.files.addItem(row)

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

    def _seek_released(self):
        if self._duration <= 0:
            return
        at = self._duration * (self.slider.value() / float(SEEK_STEPS))
        self._pos_at = at
        self._pos_when = time.monotonic()
        self._cmd("seek", str(at), "absolute")

    def _open_connection(self):
        dialog = ConnectionDialog(self.app.store.data["connection"], self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.values:
            return
        self.app.on_command({"c": "connect", **dialog.values})
        self._refresh_banner()

    def _send_bar_chat(self):
        text = self.bar_message.text().strip()
        if not text:
            return
        self.app.on_command({"c": "chat", "text": text})
        self.bar_message.clear()

    def _reconnect(self):
        conn = self.app.store.data["connection"]
        self._failed = False
        self.app.on_command({
            "c": "connect",
            "host": conn.get("host") or "",
            "port": conn.get("port") or "",
            "name": conn.get("name") or "",
            "password": conn.get("password") or "",
            "room": conn.get("room") or "",
        })
        self._refresh_banner()

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
        self._refresh_banner()
        self._refresh_transport()
        self._refresh_osd()

    def _follow_cursor(self):
        if self._panel_open or self._chat_open:
            self._set_bar(True)
            return
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
        self._connected = state == "connected"
        self._failed = state == "failed"
        if state == "failed" and self.status.text() != (event.get("text") or ""):
            self.status.setText(event.get("text") or "")
        if state == "connected":
            self.status.setText("")
        self._refresh_banner()
        if event.get("openPanel"):
            self.set_panel(True)

    def _configured(self):
        conn = self.app.store.data["connection"]
        return bool(
            str(conn.get("host") or "").strip()
            and str(conn.get("name") or "").strip()
            and str(conn.get("room") or "").strip()
        )

    def _refresh_banner(self):
        if not hasattr(self, "banner_text"):
            return
        pal = _palette(self.app.store.data["appearance"].get("theme"))
        if not self._configured():
            text, color = "Not configured", "#D6B23A"
        elif self._connected:
            text, color = "Room connected", "#3EAD62"
        elif self._failed:
            text, color = "Error connecting", pal["bad"]
        else:
            text, color = "Not configured", "#D6B23A"
        self.banner_text.setText(text)
        self.banner_dot.setStyleSheet("color: {}; background: transparent;".format(color))
        self.reconnect.setVisible(bool(self._failed and self._configured()))

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
        self._osd.append((time.monotonic(), user, text))

    def _refresh_transport(self):
        paused = self._get("pause")
        if paused is not None:
            self._paused = bool(paused)
            self.play.set_kind("play" if paused else "pause")
        try:
            self._speed = float(self._get("speed") or 1)
        except (TypeError, ValueError):
            self._speed = 1.0
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
        if not self.slider.isSliderDown():
            self._pos_at = position
            self._pos_when = time.monotonic()
        self.total.setText(_clock(self._duration))
        loop = self._get("loop-file")
        self.loop.setChecked(loop in ("inf", "yes", "always"))
        eof = self._get("eof-reached")
        ended = eof in (True, "yes", "true", 1) and self._duration > 0
        if ended:
            if not self._eof_seen:
                self._eof_seen = True
                self._advance()
        else:
            self._eof_seen = False
        self._move_knob()

    def _shown_position(self):
        if self.slider.isSliderDown() and self._duration > 0:
            return self._duration * (self.slider.value() / float(SEEK_STEPS))
        extra = 0.0
        if not self._paused:
            extra = (time.monotonic() - self._pos_when) * self._speed
        shown = self._pos_at + extra
        if self._duration > 0:
            shown = min(self._duration, max(0.0, shown))
        return max(0.0, shown)

    def _move_knob(self):
        shown = self._shown_position()
        if not self.slider.isSliderDown() and self._duration > 0:
            value = int(round(shown / self._duration * SEEK_STEPS))
            value = max(0, min(SEEK_STEPS, value))
            if value != self.slider.value():
                self.slider.setValue(value)
        self.elapsed.setText(_clock(shown))

    def _refresh_osd(self):
        if not self.ctl:
            return
        now = time.monotonic()
        self._osd = [item for item in self._osd if now - item[0] < CHAT_LIFE]
        appearance = self.app.store.data["appearance"]
        theme = appearance.get("theme") or "dark"
        point = int(appearance.get("chatFontSize") or 18)
        measure = QFont(self.font())
        measure.setPointSize(max(10, min(48, point)))
        size = max(14, QFontMetrics(measure).height())
        measure.setPixelSize(size)
        metrics = QFontMetrics(measure)
        color = _bgr(appearance.get("chatColor"))
        accent = _bgr(_palette(theme, appearance.get("accentColor"))["accent"])
        width = max(1, self.video.width())
        height = max(1, self.video.height())
        people = []
        for name, ready in self._users:
            if ready and now >= self._ready_until.get(name, 0):
                continue
            people.append((name, ready))
        lines = []
        step = metrics.height() + 4
        box_w = min(CHAT_BOX, max(160, width - 24))
        x = max(8, width - 8 - box_w)
        y = 16
        for name, ready in people:
            if y > height - BAR_HEIGHT - 16:
                break
            dot = "00FF00" if ready else "0000FF"
            lines.append(
                "{{\\pos({},{})\\an7\\bord1\\shad0\\fs{}\\1c&H{}&}}{} {{\\1c&H{}&}}●".format(
                    x, y, size, color, _ass_escape(name), dot
                )
            )
            y += step
        if people:
            y += 8
        floor = max(24, height - BAR_HEIGHT - 8)
        pad = 8
        inner = max(40, box_w - pad * 2)
        page = _palette(theme)
        for _born, user, text in self._osd:
            nick = (user + ": ") if user else ""
            nick_w = metrics.horizontalAdvance(nick) if nick else 0
            first_width = max(24, inner - nick_w)
            wrapped = _wrap_plain(text, metrics, first_width, inner)
            block_h = pad * 2 + max(1, len(wrapped)) * metrics.height()
            if y + block_h > floor:
                break
            lines.append(
                "{{\\an7\\pos({},{})\\bord0\\shad0\\1c&H{}&\\p1}}m 0 0 l {} 0 {} {} 0 {}".format(
                    x, y, _bgr(page["bg"]), box_w, box_w, block_h, block_h
                )
            )
            body = []
            for index, part in enumerate(wrapped):
                if index == 0 and user:
                    body.append(
                        "{{\\1c&H{}&}}{}{{\\1c&H{}&}}{}".format(
                            accent, _ass_escape(nick), color, _ass_escape(part)
                        )
                    )
                else:
                    body.append(_ass_escape(part))
            lines.append(
                "{{\\an7\\pos({},{})\\p0\\bord0\\shad0\\q2\\fs{}\\1c&H{}&}}{}".format(
                    x + pad, y + pad, size, color, "\\N".join(body)
                )
            )
            y += block_h + 6
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
        self._knob_timer.stop()
        self.video.shutdown()
        event.accept()
        QApplication.instance().quit()
