# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""The yucha window. Fields and buttons are real widgets. mpv only draws
the picture into the video area."""

import html
from copy import deepcopy
import math
import os
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyledItemDelegate,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from yucha import __version__, fetch_newer_stable
from yucha.configstore import DEFAULTS, dev_settings, font_name, hex_color, move_entry, wheel_rgb
from yucha.engine import Picture
from yucha.i18n import languages, system_language, tr, trf
from yucha.player_ui import replace_seek_toast, room_file_notes
from yucha.system import Notifier, SleepInhibit, join_line, people_joined

HIDE_AFTER = 3.0
CHAT_LIFE = 5.0
READY_LIFE = 2.0
VOLUME_LIFE = 2.0
PANEL_WIDTH = 380
PANEL_MIN = 240
PANEL_MAX = 900
EDGE_PX = 12
GRIP_PX = 8
BAR_HEIGHT = 57
POP_GAP = 8
FLOAT_GAP = 12
CHAT_EXTRA = 52
SEEK_STEPS = 100000
CHAT_BOX = 300
VOLUME_MAX = 130
CHAT_CAP = 300
SLIDE = 0.2


def _volume_limit(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 100
    number = max(100, min(VOLUME_MAX, number))
    return 100 + ((number - 100) // 5) * 5


def _system_dark():
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    kinds = getattr(Qt, "ColorScheme", None)
    if scheme is not None and kinds is not None:
        current = scheme()
        if current == kinds.Dark:
            return True
        if current == kinds.Light:
            return False
    window = QApplication.palette().color(QPalette.ColorRole.Window)
    ink = QApplication.palette().color(QPalette.ColorRole.WindowText)
    return window.lightness() < ink.lightness()


def _dev_ink(row, theme):
    if not isinstance(row, dict):
        return ""
    picked = row.get("light" if theme == "light" else "dark") or row.get("color") or ""
    return str(picked)


def _font_families():
    cached = getattr(_font_families, "names", None)
    if cached is not None:
        return cached
    names = ["sans-serif"]
    for name in QFontDatabase.families():
        if name and name not in names:
            names.append(name)
    _font_families.names = names
    return names


def _css_family(name):
    if not name:
        return ""
    safe = str(name).replace("\\", "").replace('"', "")
    if not safe:
        return ""
    return ' font-family: "{}";'.format(safe)


def _rgba(text, percent):
    color = QColor(text)
    alpha = max(0, min(255, int(round(float(percent) / 100.0 * 255))))
    return "rgba({}, {}, {}, {})".format(color.red(), color.green(), color.blue(), alpha)


def _shown_theme(theme):
    if theme == "light":
        return "light"
    if theme == "auto":
        return "dark" if _system_dark() else "light"
    return "dark"


def bounded_panel(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = PANEL_WIDTH
    return max(PANEL_MIN, min(PANEL_MAX, number))


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


def _stylesheet(theme, accent=None, paint=None):
    p = _palette(theme, accent)
    if paint:
        p.update(paint)
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
    StepScale, TickSlider, QPushButton#swatch {{
        color: {fg};
    }}
    QComboBox QAbstractItemView {{
        background: {field};
        color: {fg};
        border: 1px solid {border};
        selection-background-color: {accent};
        selection-color: {on_fg};
        outline: 0;
    }}
    QPushButton {{
        background: {button};
        color: {button_fg};
        border: none;
        padding: 8px 14px;
    }}
    QDialog QLineEdit, QDialog QTextEdit, QDialog QSpinBox, QDialog QComboBox, QDialog QFontComboBox {{
        background: {field};
        color: {fg};
    }}
    QDialog QPushButton {{
        background: {field};
        color: {fg};
        border: 1px solid {border};
    }}
    QPushButton#swatch, QPushButton#swatch:hover, QPushButton#swatch:pressed {{
        background: transparent;
        border: none;
        padding: 0;
    }}
    QPushButton#step {{
        padding: 4px 12px;
        min-width: 28px;
    }}
    QPushButton#step:disabled {{
        background: {field};
        color: {muted};
    }}
    QPushButton#muteicon, QPushButton#muteicon:hover, QPushButton#muteicon:pressed, QPushButton#muteicon:checked {{
        background: transparent;
        border: none;
        padding: 0;
    }}
    QPushButton:checked {{
        background: {accent};
        color: {on_fg};
    }}
    QLabel#muted {{ color: {muted}; }}
    QLabel#heading {{
        font-weight: 700;
        background: transparent;
    }}
    QWidget#bar {{ border-top: 1px solid {border}; }}
    QWidget#chatline {{
        background: {field};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QWidget#chatline QLineEdit {{
        background: transparent;
        border: none;
    }}
    QWidget#panel {{ border-left: 1px solid {border}; }}
    QWidget#banner {{
        background: {field};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QWidget#banner QLabel {{ background: transparent; }}
    QPushButton#icon, QPushButton#baricon, QPushButton#panelicon {{
        padding: 0px;
        min-width: 40px;
        max-width: 40px;
        min-height: 36px;
        max-height: 36px;
    }}
    QPushButton#baricon, QPushButton#baricon:hover, QPushButton#baricon:pressed, QPushButton#baricon:checked,
    QPushButton#panelicon, QPushButton#panelicon:hover, QPushButton#panelicon:pressed, QPushButton#panelicon:checked {{
        background: transparent;
        border: none;
    }}
    QCheckBox {{
        color: {fg};
        background: transparent;
        spacing: 8px;
    }}
    QWidget#volume {{
        background: {bg};
        border-radius: 10px;
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
    QSlider#volumebar::groove:horizontal {{
        height: 3px;
        background: {border};
        border: none;
        border-radius: 2px;
    }}
    QSlider#volumebar::sub-page:horizontal {{
        background: {accent};
        border-radius: 2px;
    }}
    QSlider#volumebar::add-page:horizontal {{
        background: transparent;
    }}
    QSlider#volumebar::handle:horizontal {{
        background: {fg};
        width: 12px;
        height: 12px;
        margin: -5px 0;
        border-radius: 6px;
    }}
    QSlider#volumebar::groove:vertical {{
        width: 3px;
        background: {border};
        border: none;
        border-radius: 2px;
    }}
    QSlider#volumebar::sub-page:vertical {{
        background: transparent;
    }}
    QSlider#volumebar::add-page:vertical {{
        background: {accent};
        border-radius: 2px;
    }}
    QSlider#volumebar::handle:vertical {{
        background: {fg};
        width: 12px;
        height: 12px;
        margin: 0 -5px;
        border-radius: 6px;
    }}
    QWidget#volume, QWidget#volumepop, QWidget#trackpop {{
        background: {bg};
        border-radius: 10px;
    }}
    QWidget#volumepop QLabel, QWidget#trackpop QLabel {{
        background: transparent;
    }}
    QPushButton#trackrow {{
        background: transparent;
        color: {fg};
        border: none;
        border-radius: 6px;
        padding: 4px 10px;
        text-align: left;
    }}
    QPushButton#trackrow:checked {{
        background: {accent};
        color: {on_fg};
    }}
    QTabWidget::pane {{
        border: 1px solid {border};
        background: {bg};
    }}
    QWidget#settingshost, QWidget#settingspage, QScrollArea#settingscroll, QScrollArea#settingscroll > QWidget {{
        background: {bg};
        border: none;
    }}
    QTabBar::tab, QPushButton#devtab {{
        background: {field};
        color: {fg};
        padding: 2px 12px;
        margin: 0px;
        border: 1px solid {border};
    }}
    QTabBar::tab:selected, QPushButton#devtab:checked {{
        background: {accent};
        color: {on_fg};
    }}
    QListWidget {{
        background: {field};
        color: {fg};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QListWidget::item {{
        padding: 4px 6px;
        background: transparent;
    }}
    QTextEdit#roomchat {{
        background: {field};
        color: {fg};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QScrollBar#edgescroll:vertical {{
        background: transparent;
        width: 3px;
        margin: 0px;
    }}
    QScrollBar#edgescroll:horizontal {{
        background: transparent;
        height: 3px;
        margin: 0px;
    }}
    QScrollBar#edgescroll::handle:vertical {{
        background: {muted};
        min-height: 18px;
        border-radius: 1px;
    }}
    QScrollBar#edgescroll::handle:horizontal {{
        background: {muted};
        min-width: 18px;
        border-radius: 1px;
    }}
    QScrollBar#edgescroll::add-line:vertical, QScrollBar#edgescroll::sub-line:vertical,
    QScrollBar#edgescroll::add-line:horizontal, QScrollBar#edgescroll::sub-line:horizontal {{
        height: 0px;
        width: 0px;
        background: none;
    }}
    QScrollBar#edgescroll::add-page:vertical, QScrollBar#edgescroll::sub-page:vertical,
    QScrollBar#edgescroll::add-page:horizontal, QScrollBar#edgescroll::sub-page:horizontal {{
        background: none;
    }}
    QScrollArea#userfiles {{
        background: transparent;
        border: none;
    }}
    QScrollArea#userfiles QWidget {{
        background: transparent;
    }}
    QWidget#usersbox {{
        background: {field};
        border: 1px solid {border};
        border-radius: 8px;
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


def _megabytes(size):
    try:
        value = float(size)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return "{} MB".format(int(round(value / 1048576.0)))


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


def _round_box(width, height, radius):
    radius = int(min(radius, width / 2, height / 2))
    if radius < 2:
        return "m 0 0 l {w} 0 {w} {h} 0 {h}".format(w=width, h=height)
    curve = radius * 0.5522847498
    return " ".join([
        "m {r} 0".format(r=_n(radius)),
        "l {x} 0".format(x=_n(width - radius)),
        "b {c1} 0 {w} {c2} {w} {r}".format(
            c1=_n(width - radius + curve), w=_n(width), c2=_n(curve), r=_n(radius)
        ),
        "l {w} {y}".format(w=_n(width), y=_n(height - radius)),
        "b {w} {c1} {c2} {h} {x} {h}".format(
            w=_n(width), c1=_n(height - radius + curve), c2=_n(width - radius + curve),
            h=_n(height), x=_n(width - radius),
        ),
        "l {x} {h}".format(x=_n(radius), h=_n(height)),
        "b {c1} {h} 0 {c2} 0 {y}".format(
            c1=_n(radius - curve), h=_n(height), c2=_n(height - radius + curve), y=_n(height - radius),
        ),
        "l 0 {y}".format(y=_n(radius)),
        "b 0 {c1} {c2} 0 {r} 0".format(c1=_n(radius - curve), c2=_n(curve), r=_n(radius)),
    ])


def _n(value):
    return str(int(round(value)))


_TIME = r"\d+:\d+(?::\d+)?"
_PLAYING_LINE = re.compile(r"^(.+?) is playing '(.+?)' \([^)]*\)(?: in room: '.*')?$")


def _ease(done):
    return done * done * (3 - 2 * done)


def _slide_x(now, born, leave, target, edge):
    """0 is off the right edge. 1 is the resting place."""
    if leave is None:
        done = min(1.0, max(0.0, (now - born) / SLIDE))
    else:
        done = 1.0 - min(1.0, max(0.0, (now - leave) / SLIDE))
    done = _ease(done)
    return int(round(edge + (target - edge) * done))


def _hidden_line(text):
    low = str(text).lower()
    return "persistent rooms" in low or "not a known media directory" in low


def _startup_line(text):
    return (
        text.startswith("Attempting to connect to ")
        or text.startswith("Attempting secure connection")
        or text.startswith("Successfully reached ")
    )


def _status_spans(text):
    text = " ".join(str(text).split())
    rules = (
        (r"^(.+?) paused at (" + _TIME + r")$", lambda m: (
            ("nick", m.group(1)),
            ("text", ": "),
            ("mark", "pause"),
            ("text", " " + tr(59) + " " + m.group(2)),
        )),
        (r"^(.+?) unpaused$", lambda m: (
            ("nick", m.group(1)),
            ("text", ": "),
            ("mark", "play"),
            ("text", " " + tr(61)),
        )),
        (r"^(.+?) jumped from (" + _TIME + r") to (" + _TIME + r")$", lambda m: (
            ("nick", m.group(1)),
            ("text", ": " + m.group(2) + " "),
            ("mark", "jump"),
            ("text", " " + m.group(3)),
        )),
        (r"^Rewinded due to time difference with (.+)$", lambda m: (
            ("nick", m.group(1)),
            ("text", ": "),
            ("mark", "back"),
        )),
        (r"^Fast-forwarded due to time difference with (.+)$", lambda m: (
            ("nick", m.group(1)),
            ("text", ": "),
            ("mark", "forward"),
        )),
        (r"^Slowing down due to time difference with (.+)$", lambda m: (
            ("nick", m.group(1)),
            ("text", ": "),
            ("mark", "down"),
        )),
        (r"^Reverting speed back to normal$", lambda m: (
            ("text", "1× " + tr(60)),
        )),
        (_PLAYING_LINE, lambda m: (
            ("nick", m.group(1)),
            ("text", ": "),
            ("mark", "play"),
            ("text", " " + tr(61) + " " + m.group(2)),
        )),
    )
    for pattern, build in rules:
        found = re.match(pattern, text)
        if found:
            return [{"k": kind, "v": value} for kind, value in build(found)]
    return None


def _spans_html(spans, me, mine, other, bad="#E07474"):
    bits = []
    for span in spans:
        safe = html.escape(span["v"], quote=False).replace("\n", "<br>")
        if span["k"] == "nick":
            color = mine if span["v"] == me else other
            bits.append('<span style="color: {}; font-weight: 700;">{}</span>'.format(color, safe))
        elif span["k"] == "leave":
            bits.append('<span style="color: {};">{}</span>'.format(bad, safe))
        elif span["k"] == "mark":
            glyph = html.escape(_MARK_GLYPH.get(span["v"], ""), quote=False)
            style = "font-size: 1em; font-weight: 700;" if span["v"] == "pause" else "font-size: 0.5em;"
            bits.append('<span style="{} vertical-align: middle;">{}</span>'.format(style, glyph))
        else:
            bits.append(safe)
    return "".join(bits)


_MARK_GLYPH = {
    "play": "▶",
    "pause": "❚❚",
    "back": "◀◀",
    "forward": "▶▶",
    "down": "↓",
    "jump": "→",
}


def _mark_width(kind, xh):
    if kind == "pause":
        return max(8, int(round(xh * 1.2)))
    if kind in ("back", "forward"):
        return max(8, int(round(xh * 1.45)))
    if kind == "jump":
        return max(8, int(round(xh * 1.15)))
    return max(6, int(round(xh * 0.9)))


def _piece_width(piece, metrics):
    if piece["k"] == "mark":
        return _mark_width(piece["v"], max(1, metrics.xHeight()))
    return metrics.horizontalAdvance(piece["v"])


def _toast_lines(spans, metrics, width):
    words = []
    for span in spans:
        if span["k"] == "mark":
            words.append(span)
            continue
        for part in re.split(r"(\s+)", span["v"]):
            if part:
                words.append({"k": span["k"], "v": part})
    if not words:
        return [[{"k": "text", "v": ""}]]
    if sum(_piece_width(word, metrics) for word in words) <= width:
        return [words]
    lines = []
    current = []
    used = 0
    for word in words:
        wide = _piece_width(word, metrics)
        if current and used + wide > width and word["v"].strip():
            lines.append(current)
            current = []
            used = 0
        current.append(word)
        used += wide
    if current:
        lines.append(current)
    return lines or [[{"k": "text", "v": ""}]]


def _paint_mark(painter, kind, band, color):
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    x = band.x()
    y = band.y()
    w = band.width()
    h = band.height()
    if kind == "pause":
        gap = max(2.0, h * 0.22)
        bar = max(2.0, (w - gap) / 2)
        radius = max(0.6, h * 0.12)
        painter.drawRoundedRect(QRectF(x, y, bar, h), radius, radius)
        painter.drawRoundedRect(QRectF(x + bar + gap, y, bar, h), radius, radius)
    elif kind == "back":
        step = w / 2
        for index in (0, 1):
            left = x + index * step
            path = QPainterPath()
            path.moveTo(left + step * 0.85, y)
            path.lineTo(left, y + h / 2)
            path.lineTo(left + step * 0.85, y + h)
            path.closeSubpath()
            painter.drawPath(path)
    elif kind == "forward":
        step = w / 2
        for index in (0, 1):
            left = x + index * step
            path = QPainterPath()
            path.moveTo(left, y)
            path.lineTo(left + step * 0.85, y + h / 2)
            path.lineTo(left, y + h)
            path.closeSubpath()
            painter.drawPath(path)
    elif kind == "down":
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + w, y)
        path.lineTo(x + w / 2, y + h)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "jump":
        mid = y + h / 2
        pen = QPen(QColor(color), max(1.4, h * 0.16))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, mid), QPointF(x + w * 0.55, mid))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(x + w, mid)
        path.lineTo(x + w * 0.42, y)
        path.lineTo(x + w * 0.42, y + h)
        path.closeSubpath()
        painter.drawPath(path)
    else:
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x, y + h)
        path.lineTo(x + w, y + h / 2)
        path.closeSubpath()
        painter.drawPath(path)
    painter.restore()


class NoticeBoard(QWidget):
    """Room notes drawn into the video frame. The timer redraws that frame while a toast moves."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("notices")
        self.hide()
        self.font_px = 18
        self.page = _palette("dark")
        self.me = ""
        self.mine = "#9A3A52"
        self.other = "#1F6A8A"
        self.notices = []
        self.ready = []
        self.plate_alpha = 232
        self.ready_on = "#3EAD62"
        self.ready_off = "#C4453C"
        self.toasts = []
        self.repaint_frame = None
        self.bar_h = BAR_HEIGHT
        self.force = None
        self.repeat = 0
        self._repeat_key = None
        self._repeat_image = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def show_state(self, font_px, page, me, mine, other, notices, ready, toasts):
        self.font_px = font_px
        self.page = page
        self.me = me
        self.mine = mine
        self.other = other
        self.notices = notices
        self.ready = ready
        self.toasts = toasts
        self._tick()

    def _moving(self, now):
        for item in self.toasts:
            leave = item.get("leave")
            if leave is not None or now - item["born"] < SLIDE:
                return True
        return False

    def _tick(self):
        now = time.monotonic()
        if self._moving(now):
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()
        if self.repaint_frame is not None:
            self.repaint_frame()

    def paint_on(self, painter, width, height):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = QFont(self.font())
        forced = self.force or {}
        if forced.get("family"):
            font.setFamily(forced["family"])
        font.setBold(bool(forced.get("bold")))
        font.setPointSize(max(1, int(self.font_px)))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        row_h = metrics.height()
        xh = max(4, metrics.xHeight())
        pad = 8
        width = max(1, width)
        now = time.monotonic()
        y = 16
        left_w = 0
        if self.repeat:
            self._paint_repeat(painter, 16, y)
            y += 56
            left_w = 64
        if self.notices:
            text_w = max(metrics.horizontalAdvance(line) for line in self.notices)
            box_w = text_w + pad * 2
            box_h = pad * 2 + len(self.notices) * row_h
            self._box(painter, 16, y, box_w, box_h)
            painter.setPen(QColor(self.page["fg"]))
            for index, line in enumerate(self.notices):
                baseline = y + pad + index * row_h + metrics.ascent()
                painter.drawText(16 + pad, baseline, line)
            y += box_h + 8
            left_w = max(left_w, 16 + box_w)
        if self.ready:
            name_w = max(metrics.horizontalAdvance(person["name"]) for person in self.ready)
            dot = max(8, xh)
            box_w = pad * 2 + name_w + 10 + dot
            box_h = pad * 2 + len(self.ready) * row_h
            self._box(painter, 16, y, box_w, box_h)
            for index, person in enumerate(self.ready):
                top = y + pad + index * row_h
                baseline = top + metrics.ascent()
                ink = self.mine if person["name"] == self.me else self.other
                painter.setPen(QColor(ink))
                painter.drawText(16 + pad, baseline, person["name"])
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(self.ready_on if person["ready"] else self.ready_off))
                cy = top + (row_h - dot) / 2
                painter.drawEllipse(QRectF(16 + pad + name_w + 10, cy, dot, dot))
            left_w = max(left_w, 16 + box_w)
        room = max(120, width - left_w - 32)
        floor = max(24, height - self.bar_h - 8)
        y = 16
        for item in self.toasts:
            lines = _toast_lines(item["spans"], metrics, room)
            widest = 0
            for line in lines:
                widest = max(widest, sum(_piece_width(piece, metrics) for piece in line))
            box_w = min(room + pad * 2, widest + pad * 2)
            box_h = pad * 2 + max(1, len(lines)) * row_h
            if y + box_h > floor:
                break
            target = max(8, width - 8 - box_w)
            draw_x = _slide_x(now, item["born"], item.get("leave"), target, width)
            self._box(painter, draw_x, y, box_w, box_h)
            text_y = y + pad
            for line in lines:
                baseline = text_y + metrics.ascent()
                band_top = baseline - xh
                cursor = draw_x + pad
                for piece in line:
                    if piece["k"] == "mark":
                        wide = _mark_width(piece["v"], xh)
                        ink = self.page["fg"]
                        _paint_mark(painter, piece["v"], QRectF(cursor, band_top, wide, xh), ink)
                        cursor += wide
                        continue
                    ink = self.mine if piece["k"] == "nick" and piece["v"] == self.me else self.page["fg"]
                    if piece["k"] == "nick" and piece["v"] != self.me:
                        ink = self.other
                    painter.setPen(QColor(ink))
                    painter.drawText(cursor, baseline, piece["v"])
                    cursor += metrics.horizontalAdvance(piece["v"])
                text_y += row_h
            y += box_h + 6

    def _paint_repeat(self, target, x, y):
        size = max(1, round(48 * target.device().devicePixelRatioF()))
        key = (self.repeat, self.page["accent"], self.page["border"], self.font().key(), size)
        if key != self._repeat_key:
            image = QImage(size * 4, size * 4, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.scale(size * 4 / 48, size * 4 / 48)
            painter.translate(24, 24)
            painter.setPen(QPen(QColor(self.page["border"]), 1, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QColor(self.page["accent"]))
            arrow = QPainterPath()
            arrow.arcMoveTo(QRectF(-18, -18, 36, 36), 155)
            arrow.arcTo(QRectF(-18, -18, 36, 36), 155, -130)
            for radius, angle in ((23, 25), (15.5, -10), (8, 25), (13, 25)):
                radians = math.radians(angle)
                arrow.lineTo(radius * math.cos(radians), -radius * math.sin(radians))
            arrow.arcTo(QRectF(-13, -13, 26, 26), 25, 130)
            arrow.closeSubpath()
            painter.drawPath(arrow)
            painter.rotate(180)
            painter.drawPath(arrow)
            painter.rotate(180)
            if self.repeat == 1:
                font = QFont(self.font())
                font.setPixelSize(18)
                font.setBold(True)
                digit = QPainterPath()
                digit.addText(0, 0, font, "1")
                center = digit.boundingRect().center()
                digit.translate(-center.x(), -center.y())
                painter.drawPath(digit)
            painter.end()
            self._repeat_image = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
            self._repeat_key = key
        target.drawImage(QRectF(x, y, 48, 48), self._repeat_image)

    def _box(self, painter, x, y, w, h):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QColor(self.page["bg"])
        color.setAlpha(self.plate_alpha)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x, y, w, h), 8, 8)


class ClickBox(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and inside:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class FileDelegate(QStyledItemDelegate):
    """The first row, when it is the current file, follows the list's top corners."""

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        color = _role_color(index.data(Qt.ItemDataRole.BackgroundRole))
        if color is not None and color.alpha() > 0:
            if index.row() == 0:
                painter.fillPath(_top_round(option.rect, 8), color)
            else:
                painter.fillRect(option.rect, color)
        ink = _role_color(index.data(Qt.ItemDataRole.ForegroundRole))
        if ink is None:
            ink = option.palette.color(QPalette.ColorRole.Text)
        painter.setPen(ink)
        host = option.widget
        painter.setFont(host.font() if host is not None else option.font)
        painter.drawText(
            option.rect.adjusted(6, 0, -6, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            index.data() or "",
        )
        painter.restore()


def _role_color(value):
    if isinstance(value, QColor):
        return value
    if isinstance(value, QBrush):
        return value.color()
    return None


def _top_round(rect, radius):
    box = QPainterPath()
    left = rect.left()
    top = rect.top()
    right = rect.right() + 1
    bottom = rect.bottom() + 1
    curve = min(radius, (right - left) / 2, bottom - top)
    box.moveTo(left, bottom)
    box.lineTo(left, top + curve)
    box.arcTo(left, top, curve * 2, curve * 2, 180, -90)
    box.lineTo(right - curve, top)
    box.arcTo(right - curve * 2, top, curve * 2, curve * 2, 90, -90)
    box.lineTo(right, bottom)
    box.closeSubpath()
    return box


class FileList(QListWidget):
    """The episode list. A left click plays a row. A drag reorders it. A right click removes it."""

    removed = Signal(str)
    chosen = Signal(str)
    moved = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setItemDelegate(FileDelegate(self))
        self._press_item = None
        self._press_pos = None
        self._dragging = False
        self._drop_row = -1
        self._line = QWidget(self.viewport())
        self._line.setFixedHeight(2)
        self._line.hide()
        self.set_mark("#F4F1EA", "#34363F")

    def set_mark(self, color, border):
        self._line.setStyleSheet("background: {}; border: none;".format(color))
        self._border = QColor(border)
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QPen(self._border, 1))
        for index in range(max(3, self.count()) - 1):
            if index < self.count():
                y = self.visualItemRect(self.item(index)).bottom()
            else:
                y = (index + 1) * max(24, QFontMetrics(self.font()).height() + 12) - 1
            painter.drawLine(6, y, self.viewport().width() - 6, y)
        painter.end()

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        path = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        if item is not None and event.button() == Qt.MouseButton.RightButton:
            self.removed.emit(path or "")
            event.accept()
            return
        if item is not None and event.button() == Qt.MouseButton.LeftButton and path:
            self._press_item = item
            self._press_pos = event.position()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_item is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        moved = (event.position() - self._press_pos).manhattanLength()
        if not self._dragging and moved < 8:
            return
        self._dragging = True
        self._drop_row = self._row_at(event.position().y())
        self._show_line()
        event.accept()

    def mouseReleaseEvent(self, event):
        item = self._press_item
        dragging = self._dragging
        dest = self._drop_row
        self._press_item = None
        self._dragging = False
        self._drop_row = -1
        self._line.hide()
        if item is None:
            super().mouseReleaseEvent(event)
            return
        path = item.data(Qt.ItemDataRole.UserRole) or ""
        if dragging:
            self.moved.emit(path, dest)
        elif path and event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(path)
        event.accept()

    def _row_at(self, y):
        count = self.count()
        for index in range(count):
            rect = self.visualItemRect(self.item(index))
            if y < rect.center().y():
                return index
        return count

    def _show_line(self):
        count = self.count()
        if count <= 0 or self._drop_row < 0:
            self._line.hide()
            return
        if self._drop_row >= count:
            y = self.visualItemRect(self.item(count - 1)).bottom()
        else:
            y = self.visualItemRect(self.item(self._drop_row)).top()
        self._line.setGeometry(6, max(0, int(y) - 1), max(1, self.viewport().width() - 12), 2)
        self._line.show()
        self._line.raise_()


class ColumnLines(QWidget):
    """Lines over the user list. Mouse clicks pass through."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.rows = 0
        self.row_h = 0
        self.top = 0
        self.split_x = 0
        self.split2_x = 0
        self.color = QColor("#34363F")

    def paintEvent(self, event):
        if self.row_h <= 0:
            return
        painter = QPainter(self)
        painter.setPen(QPen(self.color, 1))
        bottom = self.height() - self.top
        if self.split_x:
            painter.drawLine(self.split_x, self.top, self.split_x, bottom)
        if self.split2_x:
            painter.drawLine(self.split2_x, self.top, self.split2_x, bottom)
        for index in range(1, self.rows):
            y = self.top + index * self.row_h
            painter.drawLine(8, y, self.width() - 8, y)
        painter.end()


class EdgeScroll(QScrollBar):
    """A thin bar that sits just outside a field and hides after a second."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setObjectName("edgescroll")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._native = None
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._until = 0
        self.hide()
        self.sliderMoved.connect(self.bump)

    def attach(self, native):
        self._native = native
        native.rangeChanged.connect(self.sync)
        native.valueChanged.connect(self._from_native)
        self.valueChanged.connect(self._from_self)
        self.sync()

    def sync(self, *_args):
        native = self._native
        if native is None:
            return
        self.blockSignals(True)
        self.setMinimum(native.minimum())
        self.setMaximum(native.maximum())
        self.setPageStep(native.pageStep())
        self.setSingleStep(max(1, native.singleStep()))
        self.setValue(native.value())
        self.blockSignals(False)
        if self.maximum() <= self.minimum():
            self.hide()

    def _from_native(self, value):
        if self.value() != value:
            self.blockSignals(True)
            self.setValue(value)
            self.blockSignals(False)

    def _from_self(self, value):
        native = self._native
        if native is not None and native.value() != value:
            native.setValue(value)

    def bump(self, *_args):
        if self.maximum() <= self.minimum():
            self.hide()
            return
        self._until = time.monotonic() + 1.0
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        if time.monotonic() >= self._until:
            self.hide()
            self._timer.stop()


class UserTable(QWidget):
    """Nicks stay put. File names sit in the wider column and scroll sideways."""

    wheeled = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("usersbox")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._full_names = []
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        self.names = QWidget()
        self.names_col = QVBoxLayout(self.names)
        self.names_col.setContentsMargins(0, 0, 0, 0)
        self.names_col.setSpacing(0)
        self.names_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.files_scroll = QScrollArea()
        self.files_scroll.setObjectName("userfiles")
        self.files_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.files_scroll.setWidgetResizable(False)
        self.files_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files_host = QWidget()
        self.files_col = QVBoxLayout(self.files_host)
        self.files_col.setContentsMargins(0, 0, 0, 0)
        self.files_col.setSpacing(0)
        self.files_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.files_scroll.viewport().setAutoFillBackground(False)
        self.files_scroll.setWidget(self.files_host)
        self.files_scroll.viewport().installEventFilter(self)
        self.names.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.names.installEventFilter(self)
        self.sizes = QWidget()
        self.sizes_col = QVBoxLayout(self.sizes)
        self.sizes_col.setContentsMargins(0, 0, 0, 0)
        self.sizes_col.setSpacing(0)
        self.sizes_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.sizes.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row.addWidget(self.names, 4)
        row.addWidget(self.files_scroll, 11)
        row.addWidget(self.sizes, 0)
        self._row_h = 0
        self._size_width = 0
        self._line = QColor("#34363F")
        self._lines = ColumnLines(self)
        self._text_css = ""

    def set_people(self, people, me, mine, other, line):
        self._clear(self.names_col)
        self._clear(self.files_col)
        self._clear(self.sizes_col)
        self._full_names = []
        metrics = QFontMetrics(self.font())
        row_h = metrics.height() + 8
        self._row_h = row_h
        self._line = QColor(line)
        margins = self.layout().contentsMargins()
        self.names.show()
        self.files_scroll.show()
        widest = 1
        bold = QFont(self.font())
        bold.setBold(True)
        for person in people:
            name = person["name"]
            self._full_names.append(name)
            nick = QLabel(name)
            nick.setWordWrap(False)
            nick.setFixedHeight(row_h)
            nick.setFont(bold)
            nick.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            nick.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            color = mine if name == me else other
            nick.setStyleSheet(
                "color: {}; background: transparent; font-weight: 700;{}".format(
                    color,
                    " font-size: {};".format(self._text_css) if self._text_css else "",
                )
            )
            self.names_col.addWidget(nick)
            filename = person.get("file") or ""
            label = QLabel(filename)
            label.setWordWrap(False)
            label.setFixedHeight(row_h)
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            label.setStyleSheet(
                "background: transparent;{}".format(
                    " font-size: {};".format(self._text_css) if self._text_css else ""
                )
            )
            wide = max(1, metrics.horizontalAdvance(filename) + 8)
            label.setFixedWidth(wide)
            widest = max(widest, wide)
            self.files_col.addWidget(label)
            size = QLabel(_megabytes(person.get("size")))
            size.setWordWrap(False)
            size.setFixedHeight(row_h)
            size.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            size.setStyleSheet(
                "background: transparent;{}".format(
                    " font-size: {};".format(self._text_css) if self._text_css else ""
                )
            )
            self.sizes_col.addWidget(size)
        count = len(people)
        rows = max(2, count)
        content_h = rows * row_h
        self.files_host.setFixedSize(widest, content_h)
        self._size_width = max(metrics.horizontalAdvance("0000 MB") + 8, self.sizes.minimumSizeHint().width())
        self.sizes.setMinimumWidth(round(self._size_width * 0.85))
        self.setFixedHeight(content_h + margins.top() + margins.bottom())
        self._elide_names()
        self._place_lines()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and watched in (self.names, self.files_scroll.viewport()):
            self._scroll_files(event)
            return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        self._scroll_files(event)
        event.accept()

    def _scroll_files(self, event):
        bar = self.files_scroll.horizontalScrollBar()
        delta = event.angleDelta().y() or event.angleDelta().x()
        bar.setValue(bar.value() - delta)
        self.wheeled.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_names()
        self._place_lines()

    def _place_lines(self):
        if not hasattr(self, "_lines"):
            return
        margins = self.layout().contentsMargins()
        available = self.width() - margins.left() - margins.right() - 2 * self.layout().spacing() - self._size_width
        self.names.setFixedWidth(max(self.names.minimumSizeHint().width(), round(available * 4 / 15)))
        self.layout().activate()
        left = self.names.geometry().right()
        right = self.files_scroll.geometry().left()
        file_right = self.files_scroll.geometry().right()
        size_left = self.sizes.geometry().left()
        self._lines.rows = max(2, len(self._full_names))
        self._lines.row_h = self._row_h
        self._lines.top = self.layout().contentsMargins().top()
        self._lines.split_x = int((left + right) / 2) if right > left else left
        self._lines.split2_x = int((file_right + size_left) / 2) if size_left > file_right else 0
        self._lines.color = self._line
        self._lines.setGeometry(self.rect())
        self._lines.show()
        self._lines.raise_()
        self._lines.update()

    def _elide_names(self):
        width = max(1, self.names.width() - 4)
        bold = QFont(self.font())
        bold.setBold(True)
        metrics = QFontMetrics(bold)
        labels = []
        for index in range(self.names_col.count()):
            item = self.names_col.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel):
                labels.append(widget)
        for label, full in zip(labels, self._full_names):
            label.setText(full)
            label.setMinimumWidth(metrics.horizontalAdvance(full) + 8)

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class SeekBar(QSlider):
    """A click anywhere on the bar jumps to that moment."""

    def __init__(self, orientation):
        super().__init__(orientation)
        self._chapters = []
        self._chapter_duration = 0

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

    def set_chapters(self, times, duration):
        self._chapters = list(times or [])
        self._chapter_duration = float(duration or 0)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        duration = self._chapter_duration
        if duration <= 0 or not self._chapters:
            return
        painter = QPainter(self)
        color = self.palette().color(QPalette.ColorRole.WindowText)
        painter.setPen(QPen(color, 2))
        groove = self.height() / 2
        span = max(1, self.width())
        for mark in self._chapters:
            if mark <= 0.05 or mark >= duration - 0.05:
                continue
            x = mark / duration * span
            painter.drawLine(QPointF(x, groove - 7), QPointF(x, groove + 7))
        painter.end()


class QuietSpin(QSpinBox):
    """A number field. The wheel does not change it."""

    def wheelEvent(self, event):
        event.ignore()


class TickSlider(QWidget):
    """A size control. The ball sits on a step, and the wheel does not move it."""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lo = 0
        self._hi = 1
        self._value = 0
        self.setMinimumSize(180, 28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def setRange(self, lo, hi):
        self._lo = int(lo)
        self._hi = max(self._lo, int(hi))
        self._value = min(self._hi, max(self._lo, self._value))
        self.update()

    def setValue(self, value):
        value = min(self._hi, max(self._lo, int(value)))
        if value == self._value:
            self.update()
            return
        self._value = value
        self.update()
        self.valueChanged.emit(value)

    def value(self):
        return self._value

    def wheelEvent(self, event):
        event.ignore()

    def _span(self):
        return max(1, self._hi - self._lo)

    def _x_for(self, value):
        pad = 8
        room = max(1, self.width() - pad * 2)
        return pad + (value - self._lo) * room / self._span()

    def _value_at(self, x):
        pad = 8
        room = max(1, self.width() - pad * 2)
        raw = self._lo + (x - pad) * self._span() / room
        return min(self._hi, max(self._lo, int(round(raw))))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = self.palette().color(QPalette.ColorRole.WindowText)
        y = self.height() / 2
        pad = 8
        painter.setPen(QPen(ink, 1))
        painter.drawLine(QPointF(pad, y), QPointF(self.width() - pad, y))
        steps = self._span()
        marks = steps if steps <= 32 else 24
        for index in range(marks + 1):
            x = pad + index * (self.width() - pad * 2) / marks
            painter.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(QPointF(self._x_for(self._value), y), 6, 6)
        painter.end()


class StepScale(QWidget):
    """Seven sizes around the usual one. The ball sits on a mark."""

    valueChanged = Signal(int)

    def __init__(self, standard):
        super().__init__()
        self._standard = int(standard)
        self._offset = 0
        self._numbers = False
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def setValue(self, value):
        offset = max(-3, min(3, int(value) - self._standard))
        if offset == self._offset:
            self.update()
            return
        self._offset = offset
        self.update()
        self.valueChanged.emit(self.value())

    def value(self):
        return self._standard + self._offset

    def wheelEvent(self, event):
        event.ignore()

    def _xs(self):
        pad = 10
        room = max(1, self.width() - pad * 2)
        return [pad + index * room / 6.0 for index in range(7)]

    def _offset_at(self, x):
        xs = self._xs()
        nearest = min(range(7), key=lambda index: abs(xs[index] - x))
        return nearest - 3

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setValue(self._standard + self._offset_at(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self._standard + self._offset_at(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ink = self.palette().color(QPalette.ColorRole.WindowText)
        xs = self._xs()
        line_y = self.height() / 2 - (8 if self._numbers else 0)
        painter.setPen(QPen(ink, 1))
        painter.drawLine(QPointF(xs[0], line_y), QPointF(xs[-1], line_y))
        for x in xs:
            painter.drawLine(QPointF(x, line_y - 4), QPointF(x, line_y + 4))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawEllipse(QPointF((xs[0] + xs[-1]) / 2 if self._offset == 0 else xs[self._offset + 3], line_y), 5, 5)
        if self._numbers:
            font = QFont(self.font())
            font.setPointSize(7)
            painter.setFont(font)
            painter.setPen(ink)
            for step, x in zip(range(-3, 4), xs):
                painter.drawText(
                    QRectF(x - 18, line_y + 6, 36, 14),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    str(self._standard + step),
                )
        painter.end()

    def set_numbers(self, shown):
        shown = bool(shown)
        if not getattr(self, "_base_h", 0):
            self._base_h = max(self.height(), 28)
        self._numbers = shown
        self.setFixedHeight(self._base_h + (14 if shown else 0))
        self.update()


class IconButton(QPushButton):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self._ink = QColor("#F3EFE6")
        self._ink_on = QColor("#F7F4EE")
        self._accent = QColor("#9A3A52")
        self._ready_on = QColor("#3EAD62")
        self._ready_off = QColor("#C4453C")
        self._silent = False
        self.setObjectName("icon")
        self.setFixedSize(40, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)

    def hitButton(self, point):
        return self.rect().contains(point)

    def set_kind(self, kind):
        if self.kind != kind:
            self.kind = kind
            self.update()

    def set_ink(self, ink, ink_on, accent):
        self._ink = QColor(ink)
        self._ink_on = QColor(ink_on)
        self._accent = QColor(accent)
        self.update()

    def set_silent(self, silent):
        silent = bool(silent)
        if self._silent == silent:
            return
        self._silent = silent
        self.update()

    def paintEvent(self, event):
        if self.kind == "send":
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            color = QColor(self._accent)
            cx = self.width() / 2
            cy = self.height() / 2
            radius = min(self.width(), self.height()) / 2 - 2
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 1.6))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
            inset = radius - 4
            tip = cy - inset
            tail = cy + inset
            painter.drawLine(QPointF(cx, tail), QPointF(cx, tip))
            painter.drawLine(QPointF(cx, tip), QPointF(cx - 4, tip + 5))
            painter.drawLine(QPointF(cx, tip), QPointF(cx + 4, tip + 5))
            painter.end()
            return
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self._ink)
        if self.isChecked() and self.kind == "mute":
            color = QColor("#C4453C")
        elif self.isChecked() and self.kind in ("speaker", "tracks"):
            color = QColor(self._accent)
        elif self.isChecked():
            color = QColor(self._ink_on)
        if not self.isEnabled():
            color.setAlpha(90)
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
        elif kind == "ready":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._ready_on if self.isChecked() else self._ready_off)
            painter.drawEllipse(QPointF(cx, cy), 7, 7)
        elif kind == "chat":
            painter.setPen(QPen(self._ink, 1.6))
            if self.isChecked():
                painter.setBrush(self._accent)
            painter.drawRoundedRect(int(cx - 8), int(cy - 6), 16, 11, 2, 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(cx - 3, cy + 5)
            path.lineTo(cx - 6, cy + 8)
            path.lineTo(cx + 1, cy + 5)
            painter.drawPath(path)
        elif kind == "room":
            painter.setPen(QPen(self._ink, 1.6))
            if self.isChecked():
                painter.setBrush(self._accent)
            painter.drawRoundedRect(int(cx - 8), int(cy - 7), 16, 14, 2, 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(cx + 3, cy - 7), QPointF(cx + 3, cy + 7))
        elif kind == "send":
            return
        elif kind == "gear":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            for step in range(6):
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(step * 60)
                painter.drawRoundedRect(-2, -8, 4, 4, 1, 1)
                painter.restore()
            painter.drawEllipse(QPointF(cx, cy), 5.4, 5.4)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setBrush(Qt.GlobalColor.transparent)
            painter.drawEllipse(QPointF(cx, cy), 2.2, 2.2)
        elif kind == "speaker":
            painter.setBrush(color)
            path = QPainterPath()
            path.moveTo(cx - 7, cy - 3)
            path.lineTo(cx - 3, cy - 3)
            path.lineTo(cx + 1, cy - 7)
            path.lineTo(cx + 1, cy + 7)
            path.lineTo(cx - 3, cy + 3)
            path.lineTo(cx - 7, cy + 3)
            path.closeSubpath()
            painter.drawPath(path)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(int(cx + 2), int(cy - 4), 6, 8, -50 * 16, 100 * 16)
            if self._silent:
                painter.setPen(QPen(QColor("#C4453C"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(cx - 6, cy - 6), QPointF(cx + 7, cy + 5))
        elif kind == "tracks":
            painter.drawLine(QPointF(cx - 6, cy - 5), QPointF(cx + 6, cy - 5))
            painter.drawLine(QPointF(cx - 6, cy), QPointF(cx + 3, cy))
            painter.drawLine(QPointF(cx - 6, cy + 5), QPointF(cx + 6, cy + 5))
        elif kind == "mute":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(cx - 3.2, cy + 3.2), 4.2, 3.1)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(color, 1.6))
            painter.drawLine(QPointF(cx + 0.6, cy + 2), QPointF(cx + 0.6, cy - 6))
            painter.drawLine(QPointF(cx - 6, cy - 6), QPointF(cx + 7, cy + 5))
        painter.end()


class ColorDisc(QWidget):
    picked = Signal(str)
    """A hue circle. The middle is white. A click chooses the color under the pointer."""

    def __init__(self, color):
        super().__init__()
        self.setFixedSize(220, 220)
        self._radius = 100
        self._image = None
        self._chosen = QColor(hex_color(color, "#FFFFFF"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def color(self):
        return self._chosen

    def _bitmap(self):
        if self._image is not None:
            return self._image
        size = self.width()
        scale = 2
        image = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        center = size * scale / 2
        radius = self._radius * scale
        for y in range(size * scale):
            for x in range(size * scale):
                dx = x - center
                dy = y - center
                dist = math.hypot(dx, dy)
                if dist > radius + 0.5:
                    continue
                used = min(dist, radius)
                factor = used / dist if dist else 0
                rgb = wheel_rgb(dx * factor, dy * factor, radius)
                if rgb is None:
                    continue
                color = QColor(*rgb)
                if dist > radius - 1.5:
                    color.setAlphaF(max(0.0, (radius + 0.5 - dist) / 2.0))
                image.setPixelColor(x, y, color)
        self._image = image
        return image

    def _at(self, point):
        center = self.width() / 2
        dx = point.x() - center
        dy = point.y() - center
        rgb = wheel_rgb(dx, dy, self._radius)
        if rgb is None:
            dist = math.hypot(dx, dy) or 1
            scale = self._radius / dist
            rgb = wheel_rgb(dx * scale, dy * scale, self._radius)
        if rgb is None:
            return
        self._chosen = QColor(*rgb)
        self.update()
        self.picked.emit(self._chosen.name().upper())

    def set_color(self, name):
        self._chosen = QColor(name)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._at(event.position())
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._at(event.position())
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(QRectF(0, 0, self.width(), self.height()), self._bitmap())
        center = self.width() / 2
        hue, sat, _value, _alpha = self._chosen.getHsvF()
        if hue < 0:
            hue = 0
        angle = math.radians(hue * 360)
        dist = max(0.0, min(1.0, sat)) * self._radius
        mark_x = center + dist * math.cos(angle)
        mark_y = center + dist * math.sin(angle)
        painter.setPen(QPen(QColor("#16140F"), 2))
        painter.setBrush(self._chosen)
        painter.drawEllipse(QPointF(mark_x, mark_y), 6, 6)
        painter.end()


class ColorPick(QDialog):
    def __init__(self, color, title, parent):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.picked = None
        root = QVBoxLayout(self)
        self.disc = ColorDisc(color)
        self.disc.picked.connect(self._show_color)
        root.addWidget(self.disc, 0, Qt.AlignmentFlag.AlignHCenter)
        self.sample = QLabel("")
        self.sample.setFixedHeight(28)
        root.addWidget(self.sample)
        self.hex = QLineEdit(self.disc.color().name().upper())
        self.hex.setMaxLength(7)
        self.hex.textEdited.connect(self._typed)
        root.addWidget(self.hex)
        buttons = QHBoxLayout()
        ok = QPushButton(tr(43))
        cancel = QPushButton(tr(44))
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        root.addLayout(buttons)
        self._show_color(self.hex.text())
        self.setFixedSize(self.sizeHint())

    def _show_color(self, text):
        self.sample.setStyleSheet(
            "background: {}; border: 1px solid #5C584F;".format(text)
        )
        if self.hex.text().upper() != text:
            self.hex.setText(text)

    def _typed(self, text):
        found = hex_color(text, "")
        if not found:
            return
        self.disc.set_color(found)
        self._show_color(found)

    def _accept(self):
        found = hex_color(self.hex.text(), "")
        self.picked = found or self.disc.color().name().upper()
        self.accept()


class BoxCheck(QCheckBox):
    """A square with a visible fill, sitting on its own."""

    def __init__(self):
        super().__init__()
        self.setText("")
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._fill = QColor("#2A2824")
        self._line = QColor("#5C584F")
        self._mark = QColor("#F4F1EA")
        self._on = QColor("#9A3A52")

    def set_colors(self, fill, line, mark, on):
        self._fill = QColor(fill)
        self._line = QColor(line)
        self._mark = QColor(mark)
        self._on = QColor(on)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self._on if self.isChecked() else self._line, 1))
        painter.setBrush(self._on if self.isChecked() else self._fill)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 3, 3)
        if self.isChecked():
            painter.setPen(QPen(self._mark, 2))
            painter.drawLine(QPointF(4, 9), QPointF(7, 12))
            painter.drawLine(QPointF(7, 12), QPointF(14, 5))
        painter.end()


class RoundSwatch(QPushButton):
    def __init__(self):
        super().__init__()
        self._color = QColor("#FFFFFF")
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("swatch")

    def set_color(self, value):
        self._color = QColor(value)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.ButtonText), 1))
        painter.setBrush(self._color)
        painter.drawEllipse(QRectF(1, 1, self.width() - 2, self.height() - 2))
        painter.end()


class PencilButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("swatch")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = self.palette().color(QPalette.ColorRole.WindowText)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(-45)
        pen = QPen(color, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(-8, -2.2, 11, 4.4), 0.6, 0.6)
        tip = QPainterPath()
        tip.moveTo(3, -2.2)
        tip.lineTo(8, 0)
        tip.lineTo(3, 2.2)
        tip.closeSubpath()
        painter.drawPath(tip)
        painter.end()


class StarPassword(QLineEdit):
    """The field always shows five stars, so the length stays hidden."""

    def __init__(self, text=""):
        super().__init__()
        self._secret = str(text or "")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setAcceptDrops(False)
        self._show()

    def text(self):
        return self._secret

    def _show(self):
        super().setText("*****" if self._secret else "")
        self.setCursorPosition(len(super().text()))

    def keyPressEvent(self, event):
        if self.isReadOnly():
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.returnPressed.emit()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            pasted = QApplication.clipboard().text().replace("\n", "").replace("\r", "")
            self._secret += pasted
        elif event.matches(QKeySequence.StandardKey.Copy) or event.matches(QKeySequence.StandardKey.Cut):
            return
        elif event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._secret = self._secret[:-1]
        elif event.text() and event.text().isprintable() and not event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
        ):
            self._secret += event.text()
        else:
            return
        self._show()


class SettingsDialog(QDialog):
    release_text = Signal(str)

    def __init__(self, appearance, connection, parent, page=1):
        super().__init__(parent)
        self.setObjectName("settings")
        self.setWindowTitle(tr(15))
        self.setModal(True)
        self.appearance = None
        self.connection = None
        self.wants_connect = False
        self._theme_before = deepcopy(appearance)
        self._dev_before = deepcopy(parent._dev)
        self._panel_before = parent._panel_width
        self._saved_dev = deepcopy(parent._dev)
        self._dev_loading = False
        self._standard_reset = False
        self._side_layouts = []
        self._name_forms = []
        self._checking = False
        self._open_page = page
        self.release_text.connect(self._show_release)
        self._scrolls = []
        self._page_h = 0
        self._theme_light = False
        self._theme_dirty = False
        self._theme_timer = QTimer(self)
        self._theme_timer.setSingleShot(True)
        self._theme_timer.setInterval(40)
        self._theme_timer.timeout.connect(self._flush_theme)
        root = QVBoxLayout(self)
        self._dev_page = None
        self.tabs = QTabWidget()
        self.tabs.tabBar().setExpanding(False)
        self._dev_button = QPushButton(tr(77))
        self._dev_button.setObjectName("devtab")
        self._dev_button.setCheckable(True)
        self._dev_button.clicked.connect(self._open_dev)
        self.tabs.setCornerWidget(self._dev_button, Qt.Corner.TopRightCorner)
        self._dev_button.hide()
        self.tabs.currentChanged.connect(
            lambda _index: self._dev_button.setChecked(self.tabs.currentWidget() is self._dev_page)
        )
        root.addWidget(self.tabs)

        theme_page = QWidget()
        self._theme_page = theme_page
        theme_form = QFormLayout(theme_page)
        theme_form.setContentsMargins(23, 23, 23, 12)
        theme_form.setVerticalSpacing(12)
        theme_form.setHorizontalSpacing(32)
        theme_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._keep_side(theme_form)
        self._name_forms.append(theme_form)
        self.theme = QComboBox()
        self.theme.addItem(tr(57), "auto")
        self.theme.addItem(tr(23), "dark")
        self.theme.addItem(tr(24), "light")
        current = appearance.get("theme") or "auto"
        if current not in ("auto", "dark", "light"):
            current = "dark"
        self.theme.setCurrentIndex(max(0, self.theme.findData(current)))
        self._look_theme = _shown_theme(current)
        self._look_accent = appearance.get("accentColor")
        self.style_pick = QComboBox()
        self.style_pick.addItem(tr(72), "classic")
        self.style_pick.addItem(tr(73), "modern")
        picked_style = appearance.get("style") or "modern"
        self.style_pick.setCurrentIndex(1 if picked_style == "modern" else 0)
        self._kept_chat = hex_color(appearance.get("chatColor"), "#F4F1EA")
        self.accent = self._swatch(appearance.get("accentColor"), "#9A3A52")
        self.accent2 = self._swatch(appearance.get("accentColor2"), "#1F6A8A")
        accents = QWidget()
        accent_row = QHBoxLayout(accents)
        accent_row.setContentsMargins(0, 0, 0, 0)
        accent_row.setSpacing(0)
        accent_row.addWidget(self.accent)
        accent_row.addSpacing(28)
        accent_row.addWidget(self.accent2)
        accent_row.addStretch(1)
        row_h = max(self.theme.sizeHint().height(), self.style_pick.sizeHint().height())
        self.chat_size = StepScale(17)
        self.chat_size.setFixedHeight(row_h)
        self.chat_size.setValue(int(appearance.get("chatFontSize") or 17))
        self.ui_size = StepScale(13)
        self.ui_size.setFixedHeight(row_h)
        self.ui_size.setValue(int(appearance.get("uiFontSize") or 13))
        self.sub_size = StepScale(55)
        self.sub_size.setFixedHeight(row_h)
        self.sub_size.setValue(int(appearance.get("subFontSize") or 55))
        self.sub_font = QComboBox()
        chosen_font = font_name(appearance.get("subFont"))
        families = ["sans-serif"]
        for name in _font_families():
            if name not in families:
                families.append(name)
        if chosen_font not in families:
            families.insert(0, chosen_font)
        for name in families:
            self.sub_font.addItem(name, name)
        self.sub_font.setCurrentIndex(max(0, self.sub_font.findData(chosen_font)))
        self.sub_color = self._swatch(appearance.get("subColor"), "#FFFFFF")
        subtitles = QWidget()
        sub_row = QHBoxLayout(subtitles)
        sub_row.setContentsMargins(0, 0, 0, 0)
        sub_row.setSpacing(12)
        sub_row.addWidget(self.sub_font, 1)
        sub_row.addWidget(self.sub_color)
        theme_form.addRow(tr(22), self.theme)
        theme_form.addRow(tr(71), self.style_pick)
        theme_form.addRow(tr(26), accents)
        theme_form.addRow(tr(28), self.chat_size)
        theme_form.addRow(tr(29), self.ui_size)
        theme_form.addRow(tr(55), subtitles)
        theme_form.addRow(tr(54), self.sub_size)
        self.theme.currentIndexChanged.connect(lambda _index: self._preview_theme())
        self.style_pick.currentIndexChanged.connect(lambda _index: self._preview_theme())
        self.chat_size.valueChanged.connect(lambda _value: self._queue_theme(True))
        self.ui_size.valueChanged.connect(lambda _value: self._queue_theme(True))
        self.sub_size.valueChanged.connect(lambda _value: self._queue_theme(True))
        self.sub_font.currentIndexChanged.connect(lambda _index: self._preview_theme())
        self._theme_fields = (self.theme, self.style_pick, self.sub_font, self.chat_size,
                              self.ui_size, self.sub_size, accents, subtitles)
        for field in self._theme_fields:
            field.setFixedHeight(row_h)

        room = QWidget()
        room_box = QVBoxLayout(room)
        room_box.setContentsMargins(23, 23, 23, 12)
        self._keep_side(room_box)
        room_form = QFormLayout()
        room_form.setContentsMargins(0, 0, 0, 0)
        room_form.setHorizontalSpacing(theme_form.horizontalSpacing())
        room_form.setVerticalSpacing(theme_form.verticalSpacing())
        self._name_forms.append(room_form)
        self.host = QLineEdit(str(connection.get("host") or "syncplay.pl"))
        self.port = QLineEdit(str(connection.get("port") or 8999))
        self.name = QLineEdit(str(connection.get("name") or ""))
        self.password = StarPassword(str(connection.get("password") or ""))
        self.room_name = QLineEdit(str(connection.get("room") or ""))
        for number, field in (
            (17, self.host),
            (18, self.port),
            (19, self.name),
            (20, self.password),
            (16, self.room_name),
        ):
            room_form.addRow(tr(number), field)
            field.returnPressed.connect(self._connect_now)
        room_box.addLayout(room_form)
        connect_row = QHBoxLayout()
        connect_row.setContentsMargins(0, 0, 0, 0)
        connect_row.setSpacing(8)
        connect = QPushButton(tr(21))
        connect.clicked.connect(self._connect_now)
        self._connect = connect
        self._room_edit = PencilButton()
        self._room_edit.clicked.connect(self._edit_room)
        connect_row.addWidget(connect, 1)
        connect_row.addWidget(self._room_edit)
        room_box.addLayout(connect_row)
        self.port_error = QLabel("")
        self.port_error.setWordWrap(True)
        self.port_error.hide()
        room_box.addWidget(self.port_error)
        self._room_fields = (self.host, self.port, self.name, self.password, self.room_name)
        self._room_editing = False
        self._apply_room_lock()
        self.tabs.addTab(room, tr(16))
        self.tabs.addTab(theme_page, tr(22))

        other = QWidget()
        other_form = QFormLayout(other)
        other_form.setContentsMargins(23, 23, 23, 12)
        other_form.setVerticalSpacing(7)
        room_box.setSpacing(other_form.verticalSpacing())
        self._keep_side(other_form)
        self._name_forms.append(other_form)
        self.language = QComboBox()
        for name in languages():
            label = tr(105) if name == "English" else tr(106) if name == "Russian" else name
            self.language.addItem(label, name)
        picked = str(appearance.get("language") or "English")
        index = self.language.findData(picked)
        if index < 0:
            index = max(0, self.language.findData("English"))
        self.language.setCurrentIndex(index)
        row_h = self.language.sizeHint().height()
        self.overlay = QComboBox()
        self.overlay.addItem(tr(36), "horizontal")
        self.overlay.addItem(tr(37), "vertical")
        overlay = appearance.get("volumeOverlay") or "horizontal"
        self.overlay.setCurrentIndex(1 if overlay == "vertical" else 0)
        stepper = QWidget()
        stepper_row = QHBoxLayout(stepper)
        stepper_row.setContentsMargins(0, 0, 0, 0)
        stepper_row.setSpacing(0)
        self.vol_down = QPushButton("<")
        self.vol_down.setObjectName("step")
        self.vol_read = QLabel("100%")
        self.vol_read.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vol_up = QPushButton(">")
        self.vol_up.setObjectName("step")
        self.vol_down.clicked.connect(lambda: self._nudge_volume_max(-5))
        self.vol_up.clicked.connect(lambda: self._nudge_volume_max(5))
        stepper_row.addWidget(self.vol_down)
        stepper_row.addWidget(self.vol_read, 1)
        stepper_row.addWidget(self.vol_up)
        self.volume_max = _volume_limit(appearance.get("volumeMax"))
        self._show_volume_max()
        other_form.addRow(tr(38), self.language)
        other_form.addRow(tr(35), self.overlay)
        other_form.addRow(tr(34), stepper)
        self.autoplay = BoxCheck()
        self.autoplay.setChecked(bool(appearance.get("autoplayNext")))
        self.fastforward = BoxCheck()
        self.fastforward.setChecked(bool(appearance.get("fastforwardOnDesync", True)))
        self.slowdown = BoxCheck()
        self.slowdown.setChecked(bool(appearance.get("slowOnDesync", True)))
        self.check_updates = BoxCheck()
        self.check_updates.setChecked(bool(appearance.get("checkUpdates", True)))
        look = _palette(self._look_theme, self._look_accent)
        for box in (self.autoplay, self.fastforward, self.slowdown, self.check_updates):
            box.set_colors(look["field"], look["border"], look["on_fg"], look["accent"])
        self._check_row(other_form, tr(31), self.autoplay, row_h)
        self._check_row(other_form, tr(32), self.fastforward, row_h)
        self._check_row(other_form, tr(33), self.slowdown, row_h)
        self._check_row(other_form, tr(67), self.check_updates, row_h)
        self.check_updates.toggled.connect(lambda _checked: self._sync_update_row())
        self.reset_other = QPushButton(tr(70))
        self.reset_other.clicked.connect(self._reset_standard)
        other_form.addRow(self.reset_other)
        self.tabs.addTab(other, tr(30))

        about = QWidget()
        self._about_content = about
        self._about_page = about
        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(23, 23, 23, 12)
        self._keep_side(about_layout)
        logo_line = QHBoxLayout()
        logo_line.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setFixedSize(96, 96)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        icon = Path(__file__).resolve().parent / "icon.png"
        if icon.is_file():
            logo.setPixmap(QPixmap(str(icon)).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.installEventFilter(self)
        self._logo = logo
        self._logo_n = 0
        self._logo_at = 0.0
        logo_line.addStretch(1)
        logo_line.addWidget(logo)
        logo_line.addStretch(1)
        name = QLabel("yucha")
        name.setObjectName("heading")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        repo = QLabel('{}: <a href="https://github.com/yrmuq/yucha">{}</a>'.format(
            html.escape(tr(75)), html.escape(tr(76))))
        repo.setTextFormat(Qt.TextFormat.RichText)
        repo.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        repo.setOpenExternalLinks(True)
        from yucha import __version__
        version = QLabel(trf(42, __version__))
        heart = appearance.get("accentColor") or "#9A3A52"
        thanks = QLabel(
            '{} <span style="color: {};">♥</span> '
            '<a href="https://syncplay.pl">Syncplay</a> {} '
            '<a href="https://mpv.io">mpv</a>'.format(tr(40), heart, tr(41))
        )
        thanks.setTextFormat(Qt.TextFormat.RichText)
        thanks.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        thanks.setOpenExternalLinks(True)
        about_layout.addLayout(logo_line)
        about_layout.addWidget(name)
        about_layout.addWidget(repo)
        about_layout.addWidget(version)
        self.update_button = QPushButton(tr(62))
        self.update_button.clicked.connect(self._check_release)
        self.update_note = QLabel("")
        self.update_note.setWordWrap(True)
        self.download_button = QPushButton(tr(68))
        self.download_button.clicked.connect(self._open_release)
        self.download_button.hide()
        self._download_version = ""
        about_layout.addWidget(self.update_button, 0, Qt.AlignmentFlag.AlignLeft)
        about_layout.addWidget(self.update_note)
        about_layout.addWidget(self.download_button, 0, Qt.AlignmentFlag.AlignLeft)
        about_layout.addStretch(1)
        about_layout.addWidget(thanks, 0, Qt.AlignmentFlag.AlignLeft)
        self.tabs.addTab(about, tr(39))
        self._dev_page = None
        if bool(appearance.get("devTab")):
            self._insert_dev_tab()
        window = self.parent()
        if window is not None and hasattr(window, "release_ready"):
            window.release_ready.connect(self._on_release_ready)
        self._sync_update_row()

        buttons = QHBoxLayout()
        ok = QPushButton(tr(43))
        cancel = QPushButton(tr(44))
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

        if getattr(self, "_settings_h_saved", False):
            self._page_h = self._settings_h.value()
        else:
            self._page_h = int(self._saved_dev.get("settings_h", 375))
            if hasattr(self, "_settings_h"):
                self._settings_h.blockSignals(True)
                self._settings_h.setValue(375)
                self._settings_h.blockSignals(False)
        if getattr(self, "_settings_w_saved", False):
            self._page_w = self._settings_w.value()
        else:
            self._page_w = int(self._saved_dev.get("settings_w", 450))
            if hasattr(self, "_settings_w"):
                self._settings_w.blockSignals(True)
                self._settings_w.setValue(450)
                self._settings_w.blockSignals(False)
        kept = []
        for index in range(self.tabs.count()):
            kept.append((self.tabs.tabText(index), self.tabs.widget(index), self.tabs.isTabEnabled(index)))
        while self.tabs.count():
            self.tabs.removeTab(0)
        for title, page, enabled in kept:
            area = self._scroll_page(page)
            self.tabs.addTab(area, title)
            if not enabled:
                self.tabs.setTabEnabled(self.tabs.count() - 1, False)
            if page is self._about_page:
                self._about_page = area
            if page is self._dev_page:
                self._dev_page = area
                self.tabs.setTabVisible(self.tabs.indexOf(area), False)
        self.tabs.setCurrentIndex(self._open_page if 0 <= self._open_page < self.tabs.count() else 0)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self._apply_settings_edges()
        self._show_slider_numbers()
        self._apply_label_weight()
        self._apply_settings_font()
        hint = self._connect.sizeHint()
        self._connect.setFixedHeight(max(1, int(hint.height() * 0.9)))

    def _scroll_page(self, page):
        gutter = 12
        page.setMinimumWidth(max(1, self._page_w - gutter))
        hint_h = max(page.sizeHint().height(), 1)
        page.setMinimumHeight(hint_h)
        if page is self._about_content:
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        else:
            page.setMaximumHeight(hint_h)
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        if not page.objectName():
            page.setObjectName("settingspage")
        host = QWidget()
        host.setObjectName("settingshost")
        host.setFixedSize(self._page_w, self._page_h)
        area = QScrollArea(host)
        area.setObjectName("settingscroll")
        area.setGeometry(0, 0, self._page_w - gutter, self._page_h)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(page)
        area.setAutoFillBackground(False)
        area.viewport().setAutoFillBackground(False)
        page.setAutoFillBackground(False)
        bar = EdgeScroll(Qt.Orientation.Vertical, host)
        bar.attach(area.verticalScrollBar())
        area.viewport().installEventFilter(self)
        host.installEventFilter(self)
        self._scrolls.append((host, area, bar))
        self._place_settings_bar(host, area, bar)
        return host

    def _place_settings_bar(self, host, area, bar):
        bar.setGeometry(area.width() + 1, 8, 3, max(12, area.height() - 16))
        if bar.maximum() <= bar.minimum():
            bar.hide()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Wheel or kind == QEvent.Type.Resize:
            for host, area, bar in self._scrolls:
                if kind == QEvent.Type.Resize and watched is host:
                    self._place_settings_bar(host, area, bar)
                elif kind == QEvent.Type.Wheel and watched is area.viewport():
                    bar.bump()
        if watched is getattr(self, "_logo", None) and kind == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._logo_pressed()
                return True
        return super().eventFilter(watched, event)

    def _logo_pressed(self):
        now = time.monotonic()
        if now - self._logo_at > 2:
            self._logo_n = 0
        self._logo_at = now
        self._logo_n += 1
        if self._logo_n < 5:
            return
        self._logo_n = 0
        enabled = self._dev_page is None
        self._store_dev_tab(enabled)
        if enabled:
            self._insert_dev_tab()
            self.tabs.setCurrentWidget(self._dev_page)
        else:
            dev = self.tabs.indexOf(self._dev_page)
            self.tabs.setCurrentWidget(self._about_page)
            if dev >= 0:
                self.tabs.removeTab(dev)
            self._dev_page = None
            self._dev_button.hide()

    def _store_dev_tab(self, enabled):
        window = self.parent()
        if window is None:
            return
        window.app.store.data["appearance"]["devTab"] = bool(enabled)

    def _open_dev(self):
        self.tabs.setCurrentWidget(self._dev_page)
        self._dev_button.setChecked(True)

    def _insert_dev_tab(self):
        if self._dev_page is not None:
            return
        page = self._build_dev_page()
        if self._page_h:
            page = self._scroll_page(page)
        self._dev_page = page
        self.tabs.addTab(self._dev_page, tr(77))
        self.tabs.setTabVisible(self.tabs.indexOf(self._dev_page), False)
        self._dev_button.show()

    def _dev_defaults(self):
        family = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family() or "sans-serif"
        dark = _palette("dark")["fg"]
        light = _palette("light")["fg"]
        white = "#FFFFFF"
        dark_pal = _palette("dark")
        light_pal = _palette("light")
        face = {}
        for key in ("bg", "field", "border", "button", "button_fg"):
            face[key] = {"dark": dark_pal[key], "light": light_pal[key]}
        face["ready"] = {"dark": "#3EAD62", "light": "#3EAD62"}
        face["away"] = {"dark": "#C4453C", "light": "#C4453C"}
        face["locked"] = {"dark": "#2A2D36", "light": "#E4E0D8"}
        return {
            "ui": {"size": 13, "bold": False, "family": family, "dark": dark, "light": light},
            "alfa": {"size": 10, "bold": False, "family": family, "dark": dark, "light": light},
            "osd": {"size": 17, "bold": False, "family": family, "dark": dark, "light": light},
            "sub": {"size": 55, "bold": False, "family": "sans-serif", "dark": white, "light": white},
            "titles": {"size": 11, "bold": True, "family": family, "dark": dark, "light": light},
            "gamma": 10,
            "chat_max": 0,
            "face": face,
            "panel": PANEL_WIDTH,
            "bar": BAR_HEIGHT,
            "bar_alpha": 90,
            "panel_alpha": 90,
            "osd_alpha": 90,
            "bar_inset": 30,
            "settings_h": 375,
            "settings_w": 450,
            "settings_pad": 23,
            "settings_top": 23,
            "slider_numbers": False,
            "bold_names": False,
            "bar_buttons": {
                "play": True,
                "ready": True,
                "volume": True,
                "tracks": True,
                "chat": True,
                "room": True,
            },
        }

    def _dev_seed(self):
        window = self.parent()
        current = getattr(window, "_dev", None) if window is not None else None
        if current:
            merged = self._dev_defaults()
            for key, value in current.items():
                if isinstance(value, dict):
                    merged[key].update(deepcopy(value))
                else:
                    merged[key] = value
            return merged
        base = self._dev_defaults()
        if window is None:
            return base
        look = window.app.store.data["appearance"]
        base["ui"]["size"] = int(look.get("uiFontSize") or 13)
        base["osd"]["size"] = int(look.get("chatFontSize") or 17)
        base["sub"]["size"] = int(look.get("subFontSize") or 55)
        base["sub"]["family"] = font_name(look.get("subFont"))
        sub = hex_color(look.get("subColor"), "#FFFFFF")
        base["sub"]["dark"] = sub
        base["sub"]["light"] = sub
        base["panel"] = int(getattr(window, "_panel_width", PANEL_WIDTH) or PANEL_WIDTH)
        base["bar"] = int(getattr(window, "_bar_h", BAR_HEIGHT) or BAR_HEIGHT)
        return base

    def _build_dev_page(self):
        seed = self._dev_seed()
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        pad = int(seed.get("settings_pad", 23))
        top = int(seed.get("settings_top", 23))
        form.setContentsMargins(pad, top, pad, 12)
        form.setVerticalSpacing(12)
        self._keep_side(form)
        self._name_forms.append(form)
        reset = QPushButton(tr(70))
        export = QPushButton(tr(69))
        reset.clicked.connect(self._reset_dev)
        export.clicked.connect(self._export_dev)
        actions = QWidget()
        action_row = QHBoxLayout(actions)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.addWidget(reset, 1)
        action_row.addWidget(export, 1)
        form.addRow(actions)
        self._dev_rows = {}
        for key, title in (
            ("ui", tr(78)),
            ("alfa", tr(79)),
            ("titles", tr(80)),
            ("osd", tr(28)),
            ("sub", tr(55)),
        ):
            form.addRow(title, self._dev_font_row(key, seed[key]))
            if key == "titles":
                self.gamma_size = QuietSpin()
                self.gamma_size.setRange(1, 96)
                self.gamma_size.setValue(int(seed.get("gamma", 10)))
                self.gamma_size.valueChanged.connect(self._set_gamma_size)
                form.addRow(tr(81), self.gamma_size)
        self._face_rows = {}
        face = seed.get("face") or self._dev_defaults()["face"]
        for key, title in (
            ("bg", tr(82)),
            ("field", tr(83)),
            ("border", tr(84)),
            ("button", tr(85)),
            ("button_fg", tr(86)),
            ("ready", tr(87)),
            ("away", tr(88)),
            ("locked", tr(89)),
        ):
            form.addRow(title, self._face_row(key, face.get(key) or self._dev_defaults()["face"][key]))
        self._dev_panel = QuietSpin()
        self._dev_panel.setRange(240, 900)
        self._dev_panel.setValue(int(seed["panel"]))
        self._dev_panel.valueChanged.connect(lambda _value: self._push_dev())
        self._dev_bar = QuietSpin()
        self._dev_bar.setRange(36, 160)
        self._dev_bar.setValue(int(seed["bar"]))
        self._dev_bar.valueChanged.connect(lambda _value: self._push_dev())
        form.addRow(tr(90), self._dev_panel)
        self._chat_max = QuietSpin()
        self._chat_max.setRange(0, 2160)
        self._chat_max.setSuffix(" px")
        self._chat_max.setSpecialValueText(tr(109))
        self._chat_max.setValue(int(seed.get("chat_max", 0)))
        self._chat_max.valueChanged.connect(lambda _value: self._push_dev())
        form.addRow(tr(108), self._chat_max)
        form.addRow(tr(91), self._dev_bar)
        self._bar_inset = QuietSpin()
        self._bar_inset.setRange(0, 40)
        self._bar_inset.setSuffix("%")
        self._bar_inset.setValue(int(seed.get("bar_inset", 30)))
        self._bar_inset.valueChanged.connect(lambda _value: self._push_dev())
        form.addRow(tr(92), self._bar_inset)
        self._bar_alpha = self._alpha_spin(seed.get("bar_alpha", 90))
        self._panel_alpha = self._alpha_spin(seed.get("panel_alpha", 90))
        self._osd_alpha = self._alpha_spin(seed.get("osd_alpha", 90))
        form.addRow(tr(93), self._bar_alpha)
        form.addRow(tr(94), self._panel_alpha)
        form.addRow(tr(95), self._osd_alpha)
        saved_h = int(seed.get("settings_h") or 0)
        self._settings_h_saved = saved_h >= 240
        self._settings_h = QuietSpin()
        self._settings_h.setRange(240, 900)
        self._settings_h.setValue(saved_h if self._settings_h_saved else 375)
        self._settings_h.valueChanged.connect(self._set_settings_height)
        form.addRow(tr(96), self._settings_h)
        saved_w = int(seed.get("settings_w") or 0)
        self._settings_w_saved = saved_w >= 360
        self._settings_w = QuietSpin()
        self._settings_w.setRange(360, 1100)
        self._settings_w.setValue(saved_w if self._settings_w_saved else 450)
        self._settings_w.valueChanged.connect(self._set_settings_width)
        form.addRow(tr(97), self._settings_w)
        self._settings_pad = QuietSpin()
        self._settings_pad.setRange(0, 160)
        self._settings_pad.setValue(pad)
        self._settings_pad.valueChanged.connect(self._set_settings_pad)
        form.addRow(tr(98), self._settings_pad)
        self._settings_top = QuietSpin()
        self._settings_top.setRange(0, 160)
        self._settings_top.setValue(top)
        self._settings_top.valueChanged.connect(self._set_settings_top)
        form.addRow(tr(99), self._settings_top)
        look = _palette(self._look_theme, self._look_accent)
        self._slider_numbers = BoxCheck()
        self._slider_numbers.setChecked(bool(seed.get("slider_numbers", False)))
        self._slider_numbers.set_colors(look["field"], look["border"], look["on_fg"], look["accent"])
        self._slider_numbers.toggled.connect(lambda _value: self._toggle_slider_numbers())
        form.addRow(tr(100), self._slider_numbers)
        self._label_bold = BoxCheck()
        self._label_bold.setChecked(bool(seed.get("bold_names", False)))
        self._label_bold.set_colors(look["field"], look["border"], look["on_fg"], look["accent"])
        self._label_bold.toggled.connect(lambda _value: self._toggle_label_bold())
        form.addRow(tr(101), self._label_bold)
        if self._slider_numbers.isChecked():
            self._show_slider_numbers()
        if self._label_bold.isChecked():
            self._apply_label_weight()
        self._bar_buttons = {}
        buttons = QWidget()
        button_row = QHBoxLayout(buttons)
        button_row.setContentsMargins(0, 0, 0, 0)
        flags = seed.get("bar_buttons") or {}
        look = _palette(self._look_theme, self._look_accent)
        for key, title in (
            ("play", tr(102)),
            ("ready", tr(87)),
            ("volume", tr(103)),
            ("tracks", tr(12)),
            ("chat", tr(3)),
            ("room", tr(16)),
        ):
            box = BoxCheck()
            box.setChecked(bool(flags.get(key, True)))
            box.set_colors(look["field"], look["border"], look["on_fg"], look["accent"])
            box.toggled.connect(lambda _value: self._push_dev())
            self._bar_buttons[key] = box
            button_row.addWidget(box)
            button_row.addWidget(QLabel(title))
        button_row.addStretch(1)
        form.addRow(tr(104), buttons)
        if getattr(self, "_scrolls", None):
            self._set_settings_pad(self._settings_pad.value())
        return page

    def _dev_font_row(self, key, seed):
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        size = QuietSpin()
        size.setRange(1, 96)
        size.setValue(int(seed["size"]))
        bold = BoxCheck()
        bold.setChecked(bool(seed["bold"]))
        family = QFontComboBox()
        family.setCurrentFont(QFont(str(seed["family"])))
        family.setMaximumWidth(180)
        dark = self._dev_swatch(seed.get("dark") or seed.get("color") or "#F3EFE6", tr(23))
        light = self._dev_swatch(seed.get("light") or seed.get("color") or "#1A1A1A", tr(24))
        look = _palette(self._look_theme, self._look_accent)
        bold.set_colors(look["field"], look["border"], look["on_fg"], look["accent"])
        size.valueChanged.connect(lambda _value: self._push_dev())
        bold.toggled.connect(lambda _value: self._push_dev())
        family.currentFontChanged.connect(lambda _value: self._push_dev())
        row.addWidget(size)
        row.addWidget(bold)
        row.addWidget(family, 1)
        row.addWidget(QLabel(tr(23)))
        row.addWidget(dark)
        row.addWidget(QLabel(tr(24)))
        row.addWidget(light)
        self._dev_rows[key] = {
            "size": size,
            "bold": bold,
            "family": family,
            "dark": dark,
            "light": light,
        }
        return host

    def _face_row(self, key, seed):
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        dark = self._dev_swatch(seed.get("dark") or "#000000", tr(23))
        light = self._dev_swatch(seed.get("light") or "#FFFFFF", tr(24))
        row.addWidget(QLabel(tr(23)))
        row.addWidget(dark)
        row.addWidget(QLabel(tr(24)))
        row.addWidget(light)
        row.addStretch(1)
        self._face_rows[key] = {"dark": dark, "light": light}
        return host

    def _alpha_spin(self, value):
        spin = QuietSpin()
        spin.setRange(0, 100)
        spin.setSuffix("%")
        spin.setValue(int(value))
        spin.valueChanged.connect(lambda _value: self._push_dev())
        return spin

    def _dev_swatch(self, color, title):
        button = RoundSwatch()
        button.set_color(hex_color(color, "#FFFFFF"))
        button.clicked.connect(lambda: self._pick_dev(button, title))
        return button

    def _pick_dev(self, button, title):
        dialog = ColorPick(button._color.name(), title, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.picked:
            button.set_color(dialog.picked)
            self._push_dev()

    def _fill_dev(self, seed):
        self._dev_loading = True
        widgets = [
            self._dev_panel,
            self._dev_bar,
            self._chat_max,
            self._bar_inset,
            self._bar_alpha,
            self._panel_alpha,
            self._osd_alpha,
            self._settings_h,
            self._settings_w,
            self._settings_pad,
            self._settings_top,
            self._slider_numbers,
            self._label_bold,
            self.gamma_size,
        ]
        widgets.extend(self._bar_buttons.values())
        for row in self._dev_rows.values():
            widgets.extend((row["size"], row["bold"], row["family"]))
        for widget in widgets:
            widget.blockSignals(True)
        for key, row in self._dev_rows.items():
            item = seed[key]
            row["size"].setValue(int(item["size"]))
            row["bold"].setChecked(bool(item["bold"]))
            row["family"].setCurrentFont(QFont(str(item["family"])))
            row["dark"].set_color(hex_color(item.get("dark") or item.get("color"), "#F3EFE6"))
            row["light"].set_color(hex_color(item.get("light") or item.get("color"), "#1A1A1A"))
        face = seed.get("face") or {}
        for key, row in self._face_rows.items():
            item = face.get(key) or {}
            row["dark"].set_color(hex_color(item.get("dark"), "#000000"))
            row["light"].set_color(hex_color(item.get("light"), "#FFFFFF"))
        self._dev_panel.setValue(int(seed["panel"]))
        self._dev_bar.setValue(int(seed["bar"]))
        self._chat_max.setValue(int(seed.get("chat_max", 0)))
        self._bar_inset.setValue(int(seed.get("bar_inset", 30)))
        self._bar_alpha.setValue(int(seed.get("bar_alpha", 90)))
        self._panel_alpha.setValue(int(seed.get("panel_alpha", 90)))
        self._osd_alpha.setValue(int(seed.get("osd_alpha", 90)))
        self._settings_h.setValue(int(seed.get("settings_h") or 375))
        self._settings_w.setValue(int(seed.get("settings_w") or self._settings_w.value()))
        self._settings_pad.setValue(int(seed.get("settings_pad", 23)))
        self._settings_top.setValue(int(seed.get("settings_top", 23)))
        self._slider_numbers.setChecked(bool(seed.get("slider_numbers", False)))
        self._label_bold.setChecked(bool(seed.get("bold_names", False)))
        self.gamma_size.setValue(int(seed.get("gamma", 10)))
        flags = seed.get("bar_buttons") or {}
        for key, box in self._bar_buttons.items():
            box.setChecked(bool(flags.get(key, True)))
        for widget in widgets:
            widget.blockSignals(False)
        if getattr(self, "_scrolls", None):
            self._set_settings_height(self._settings_h.value())
            self._set_settings_width(self._settings_w.value())
            self._apply_settings_edges()
        self._show_slider_numbers()
        self._apply_label_weight()
        self._dev_loading = False

    def _reset_dev(self):
        self._fill_dev(self._dev_defaults())
        self._push_dev()

    def _dev_spec(self):
        spec = {
            "panel": self._dev_panel.value(),
            "bar": self._dev_bar.value(),
            "chat_max": self._chat_max.value(),
            "bar_alpha": self._bar_alpha.value(),
            "panel_alpha": self._panel_alpha.value(),
            "osd_alpha": self._osd_alpha.value(),
            "bar_inset": self._bar_inset.value(),
            "settings_h": self._settings_h.value(),
            "settings_w": self._settings_w.value(),
            "settings_pad": self._settings_pad.value(),
            "settings_top": self._settings_top.value(),
            "slider_numbers": self._slider_numbers.isChecked(),
            "bold_names": self._label_bold.isChecked(),
            "gamma": self.gamma_size.value(),
            "bar_buttons": {key: box.isChecked() for key, box in self._bar_buttons.items()},
            "face": {},
        }
        for key, row in self._dev_rows.items():
            spec[key] = {
                "size": row["size"].value(),
                "bold": row["bold"].isChecked(),
                "family": row["family"].currentFont().family(),
                "dark": row["dark"]._color.name().upper(),
                "light": row["light"]._color.name().upper(),
            }
        for key, row in self._face_rows.items():
            spec["face"][key] = {
                "dark": row["dark"]._color.name().upper(),
                "light": row["light"]._color.name().upper(),
            }
        return spec

    def _push_dev(self):
        window = self.parent()
        if window is None or self._dev_loading or not hasattr(self, "_bar_buttons"):
            return
        window.apply_dev(self._dev_spec())
        self._apply_room_lock()
        self._apply_label_weight()
        self._apply_settings_font()

    def _set_gamma_size(self, size):
        self.parent()._dev["gamma"] = int(size)
        self._apply_settings_font()

    def _apply_settings_font(self):
        size = int(self.parent()._dev.get("gamma", 10))
        font = self.font()
        font.setPointSize(size)
        self.setFont(font)
        self.setStyleSheet("QDialog#settings, QDialog#settings QWidget { font-size: %dpt; }" % size)
        self.ensurePolished()
        for combo in self.findChildren(QComboBox):
            self._style_popup(combo)
        row_h = max(self.theme.sizeHint().height(), QFontMetrics(font).height() + 14)
        for field in self._theme_fields:
            field.setFixedHeight(row_h)
        for scale in (self.chat_size, self.ui_size, self.sub_size):
            scale._base_h = row_h
        self._show_slider_numbers()
        self._fit_settings_pages()

    def _reset_standard(self):
        defaults = DEFAULTS["appearance"]
        self._theme_timer.stop()
        combos = ((self.theme, "theme"), (self.style_pick, "style"),
                  (self.sub_font, "subFont"), (self.language, "language"),
                  (self.overlay, "volumeOverlay"))
        scales = ((self.chat_size, "chatFontSize"), (self.ui_size, "uiFontSize"),
                  (self.sub_size, "subFontSize"))
        boxes = ((self.autoplay, "autoplayNext"), (self.fastforward, "fastforwardOnDesync"),
                 (self.slowdown, "slowOnDesync"), (self.check_updates, "checkUpdates"))
        for widget, key in combos + scales + boxes:
            widget.blockSignals(True)
            value = system_language() if key == "language" else defaults[key]
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            else:
                widget.setValue(value)
            widget.blockSignals(False)
        for widget, key in ((self.accent, "accentColor"), (self.accent2, "accentColor2"),
                            (self.sub_color, "subColor")):
            widget.set_color(defaults[key])
        self._kept_chat = defaults["chatColor"]
        self.volume_max = defaults["volumeMax"]
        self._show_volume_max()
        self._standard_reset = True
        self._push_theme(False, sync_dev=False)
        self._sync_update_row()

    def _export_dev(self):
        spec = self._dev_spec()
        lines = []
        lines.append("gamma.size={}".format(spec["gamma"]))
        for key in ("ui", "alfa", "osd", "sub", "titles"):
            row = spec[key]
            lines.append("{}.size={}".format(key, row["size"]))
            lines.append("{}.bold={}".format(key, "yes" if row["bold"] else "no"))
            lines.append("{}.family={}".format(key, row["family"]))
            lines.append("{}.color.dark={}".format(key, row["dark"]))
            lines.append("{}.color.light={}".format(key, row["light"]))
        for key, row in spec["face"].items():
            lines.append("face.{}.dark={}".format(key, row["dark"]))
            lines.append("face.{}.light={}".format(key, row["light"]))
        lines.append("panel.width={}".format(spec["panel"]))
        lines.append("chat.max-height={}".format(spec["chat_max"]))
        lines.append("bar.height={}".format(spec["bar"]))
        lines.append("bar.alpha={}".format(spec["bar_alpha"]))
        lines.append("panel.alpha={}".format(spec["panel_alpha"]))
        lines.append("osd.alpha={}".format(spec["osd_alpha"]))
        lines.append("bar.inset={}".format(spec["bar_inset"]))
        for key, shown in spec["bar_buttons"].items():
            lines.append("bar.button.{}={}".format(key, "yes" if shown else "no"))
        path, _chosen = QFileDialog.getSaveFileName(self, tr(69), "yucha-dev.txt", "{} (*.txt)".format(tr(107)))
        if not path:
            return
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _sync_update_row(self):
        auto = self.check_updates.isChecked()
        self.update_button.setVisible(not auto)
        self.download_button.hide()
        if not auto:
            self.update_note.setText("")
            return
        window = self.parent()
        state = getattr(window, "_release", None) if window is not None else None
        if state and state.get("done"):
            token = "fail" if state.get("error") else (state.get("version") or "")
            self._show_release(token)
            return
        if window is not None and getattr(window, "_release_running", False):
            self.update_note.setText("")
            return
        self.update_note.setText("")
        self._check_release()

    def _on_release_ready(self):
        if not self.check_updates.isChecked():
            return
        state = getattr(self.parent(), "_release", None) or {}
        token = "fail" if state.get("error") else (state.get("version") or "")
        self._show_release(token)

    def _open_release(self):
        version = self._download_version
        if not version:
            return
        QDesktopServices.openUrl(QUrl("https://github.com/yrmuq/yucha/releases/tag/v" + version))

    def _check_release(self):
        if self._checking:
            return
        self._checking = True
        self.update_button.setEnabled(False)
        self.update_note.setText("")
        threading.Thread(target=self._load_release, daemon=True).start()

    def _load_release(self):
        try:
            found = fetch_newer_stable(__version__)
            token = found or ""
        except Exception:
            token = "fail"
        try:
            self.release_text.emit(token)
        except RuntimeError:
            pass

    def _show_release(self, token):
        self._checking = False
        self.update_button.setEnabled(True)
        if token == "fail":
            self.update_note.setTextFormat(Qt.TextFormat.PlainText)
            self.update_note.setText(tr(65))
            self.download_button.hide()
            return
        if token:
            self._download_version = token
            self.update_note.setTextFormat(Qt.TextFormat.PlainText)
            self.update_note.setText(trf(64, token))
            self.download_button.show()
            return
        self.update_note.setTextFormat(Qt.TextFormat.RichText)
        self.update_note.setText(
            '<span style="color: #3EAD62;">✓ {}</span>'.format(html.escape(tr(63)))
        )
        self.download_button.hide()

    def _connect_now(self):
        self.wants_connect = True
        self._accept()

    def _accept(self):
        from yucha.configstore import port_number
        raw_port = self.port.text().strip()
        if raw_port and port_number(raw_port) is None:
            self.port_error.setText(tr(45))
            self.port_error.show()
            return
        self.port_error.hide()
        if self._theme_timer.isActive():
            self._theme_timer.stop()
            self._flush_theme()
        color = self._kept_chat
        accent = hex_color(self.accent._color.name(), "#9A3A52")
        accent2 = hex_color(self.accent2._color.name(), "#1F6A8A")
        self.appearance = {
            "theme": self.theme.currentData(),
            "chatColor": color,
            "accentColor": accent,
            "accentColor2": accent2,
            "chatFontSize": self.chat_size.value(),
            "uiFontSize": self.ui_size.value(),
            "subFont": font_name(self.sub_font.currentData()),
            "subFontSize": self.sub_size.value(),
            "subColor": hex_color(self.sub_color._color.name(), "#FFFFFF"),
            "autoplayNext": self.autoplay.isChecked(),
            "fastforwardOnDesync": self.fastforward.isChecked(),
            "slowOnDesync": self.slowdown.isChecked(),
            "volumeMax": self.volume_max,
            "volumeOverlay": self.overlay.currentData() or "horizontal",
            "language": self.language.currentData() or "English",
            "checkUpdates": self.check_updates.isChecked(),
            "style": self.style_pick.currentData() or "modern",
            "dev": deepcopy(self.parent()._dev),
            "devTab": bool(self.parent().app.store.data["appearance"].get("devTab")),
        }
        if self._standard_reset:
            self.appearance["panelWidth"] = DEFAULTS["appearance"]["panelWidth"]
        self.connection = {
            "host": self.host.text(),
            "port": self.port.text(),
            "name": self.name.text(),
            "password": self.password.text(),
            "room": self.room_name.text(),
        }
        self.accept()

    def _swatch(self, value, default):
        button = RoundSwatch()
        button.set_color(hex_color(value, default))
        button.clicked.connect(lambda: self._pick_swatch(button, default))
        return button

    def _pick_swatch(self, button, default):
        dialog = ColorPick(hex_color(button._color.name(), default), "", self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.picked:
            button.set_color(dialog.picked)
            self._preview_theme()

    def _keep_side(self, layout):
        self._side_layouts.append((layout, layout.contentsMargins().bottom()))

    def _apply_settings_edges(self):
        pad = self._settings_pad.value() if hasattr(self, "_settings_pad") else self._saved_dev.get("settings_pad", 23)
        top = self._settings_top.value() if hasattr(self, "_settings_top") else self._saved_dev.get("settings_top", 23)
        for layout, bottom in self._side_layouts:
            layout.setContentsMargins(int(pad), int(top), int(pad), int(bottom))
        self._fit_settings_pages()

    def _fit_settings_pages(self):
        for _host, area, _bar in self._scrolls:
            page = area.widget()
            page.setMinimumHeight(0)
            page.setMaximumHeight(16777215)
            page.layout().invalidate()
            height = max(1, page.sizeHint().height(), page.heightForWidth(area.viewport().width()))
            if page is self._about_content:
                page.setMinimumHeight(height)
            else:
                page.setFixedHeight(height)

    def _set_settings_pad(self, _pad):
        self._apply_settings_edges()
        self._push_dev()

    def _set_settings_top(self, _top):
        self._apply_settings_edges()
        self._push_dev()

    def _edit_room(self):
        window = self.parent()
        connected = bool(window is not None and getattr(window, "_connected", False))
        if not connected:
            self._room_editing = True
        else:
            self._room_editing = not self._room_editing
        self._apply_room_lock()

    def _show_slider_numbers(self):
        shown = self._slider_numbers.isChecked() if hasattr(self, "_slider_numbers") else self._saved_dev.get("slider_numbers", False)
        for scale in (self.chat_size, self.ui_size, self.sub_size):
            scale.set_numbers(shown)

    def _toggle_slider_numbers(self):
        self._show_slider_numbers()
        self._push_dev()

    def _apply_label_weight(self):
        bold = self._label_bold.isChecked() if hasattr(self, "_label_bold") else self._saved_dev.get("bold_names", False)
        for form in self._name_forms:
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item is None:
                    continue
                widget = item.widget()
                if not isinstance(widget, QLabel):
                    continue
                font = widget.font()
                font.setBold(bold)
                widget.setFont(font)
                widget.setStyleSheet("font-weight: {};".format(700 if bold else 400))

    def _toggle_label_bold(self):
        self._apply_label_weight()
        self._push_dev()

    def _locked_color(self):
        theme = self._look_theme
        window = self.parent()
        if window is not None:
            theme = _shown_theme(window.app.store.data["appearance"].get("theme"))
        row = {}
        if hasattr(self, "_face_rows"):
            picked = self._face_rows.get("locked")
            if picked:
                row = {
                    "dark": picked["dark"]._color.name(),
                    "light": picked["light"]._color.name(),
                }
        ink = _dev_ink(row, theme)
        if ink:
            return ink
        return "#E4E0D8" if theme == "light" else "#2A2D36"

    def _apply_room_lock(self):
        if not hasattr(self, "_room_fields"):
            return
        window = self.parent()
        connected = bool(window is not None and getattr(window, "_connected", False))
        locked = connected and not self._room_editing
        color = self._locked_color()
        for field in self._room_fields:
            field.setReadOnly(locked)
            if locked:
                field.setStyleSheet("QLineEdit {{ background: {}; }}".format(color))
            else:
                field.setStyleSheet("")

    def _set_settings_height(self, height):
        self._page_h = max(240, int(height))
        gutter = 12
        for host, area, bar in getattr(self, "_scrolls", []):
            host.setFixedSize(self._page_w, self._page_h)
            area.setGeometry(0, 0, max(1, self._page_w - gutter), self._page_h)
            self._place_settings_bar(host, area, bar)
        if getattr(self, "_scrolls", None):
            self.adjustSize()
        self._push_dev()

    def _set_settings_width(self, width):
        self._page_w = max(360, int(width))
        gutter = 12
        for host, area, bar in getattr(self, "_scrolls", []):
            page = area.widget()
            if page is not None:
                page.setMinimumWidth(max(1, self._page_w - gutter))
            host.setFixedSize(self._page_w, self._page_h)
            area.setGeometry(0, 0, max(1, self._page_w - gutter), self._page_h)
            self._place_settings_bar(host, area, bar)
        if getattr(self, "_scrolls", None):
            self.adjustSize()
        self._push_dev()

    def _queue_theme(self, light):
        self._theme_light = bool(light)
        self._theme_timer.start()

    def _flush_theme(self):
        self._push_theme(self._theme_light)

    def _preview_theme(self):
        self._theme_timer.stop()
        self._push_theme(False)

    def _push_theme(self, light, sync_dev=True):
        window = self.parent()
        if window is None or not hasattr(window, "apply_theme"):
            return
        look = window.app.store.data["appearance"]
        before = dict(look)
        look["theme"] = self.theme.currentData()
        look["style"] = self.style_pick.currentData() or "modern"
        look["accentColor"] = hex_color(self.accent._color.name(), "#9A3A52")
        look["accentColor2"] = hex_color(self.accent2._color.name(), "#1F6A8A")
        look["chatFontSize"] = self.chat_size.value()
        look["uiFontSize"] = self.ui_size.value()
        look["subFont"] = font_name(self.sub_font.currentData())
        look["subFontSize"] = self.sub_size.value()
        look["subColor"] = hex_color(self.sub_color._color.name(), "#FFFFFF")
        # Ordinary size controls and the development tab edit the same sizes.
        for key, setting in (("ui", "uiFontSize"), ("osd", "chatFontSize"), ("sub", "subFontSize")):
            if sync_dev and before.get(setting) != look[setting] and window._dev:
                window._dev.setdefault(key, {})["size"] = look[setting]
                if hasattr(self, "_dev_rows"):
                    spin = self._dev_rows[key]["size"]
                    spin.blockSignals(True)
                    spin.setValue(look[setting])
                    spin.blockSignals(False)
        if sync_dev and window._dev:
            sub = window._dev.setdefault("sub", {})
            if before.get("subFont") != look["subFont"]:
                sub["family"] = look["subFont"]
            if before.get("subColor") != look["subColor"]:
                sub.update(dark=look["subColor"], light=look["subColor"])
            if hasattr(self, "_dev_rows"):
                row = self._dev_rows["sub"]
                row["family"].blockSignals(True)
                row["family"].setCurrentFont(QFont(sub.get("family", look["subFont"])))
                row["family"].blockSignals(False)
                for shade in ("dark", "light"):
                    if shade in sub:
                        row[shade].set_color(sub[shade])
        self._theme_dirty = True
        window.apply_theme()
        self._apply_settings_font()

    def reject(self):
        self._theme_timer.stop()
        window = self.parent()
        if window is not None and hasattr(window, "apply_theme"):
            window.app.store.data["appearance"] = deepcopy(self._theme_before)
            window._dev = deepcopy(self._dev_before)
            window._bar_h = int(window._dev.get("bar", BAR_HEIGHT))
            window._panel_width = self._panel_before
            window.apply_theme()
        super().reject()

    def _color_row(self, value, default, title):
        edit = QLineEdit(hex_color(value, default))
        button = RoundSwatch()

        def paint():
            button.set_color(hex_color(edit.text(), default))

        paint()
        edit.textChanged.connect(lambda _text: paint())
        button.clicked.connect(lambda: self._pick_color(edit, default, title))
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return edit, host

    def _pick_color(self, edit, default, title):
        dialog = ColorPick(hex_color(edit.text(), default), title, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.picked:
            edit.setText(dialog.picked)

    def _check_row(self, form, text, box, height):
        host = QWidget()
        host.setMinimumHeight(height)
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(box)
        form.addRow(text, host)

    def _style_popup(self, combo):
        window = self.parent()
        look = window.app.store.data["appearance"]
        theme = _shown_theme(look.get("theme"))
        page = _palette(theme, look.get("accentColor"))
        page.update(window._face_paint(theme))
        view = combo.view()
        palette = view.palette()
        for role, key in ((QPalette.ColorRole.Window, "field"),
                          (QPalette.ColorRole.Base, "field"),
                          (QPalette.ColorRole.WindowText, "fg"),
                          (QPalette.ColorRole.Text, "fg"),
                          (QPalette.ColorRole.Highlight, "accent"),
                          (QPalette.ColorRole.HighlightedText, "on_fg")):
            palette.setColor(role, QColor(page[key]))
        # The popup frame paints the margins above and below the item view.
        popup = view.window()
        popup.setPalette(palette)
        popup.setObjectName("settingspopup")
        popup.setStyleSheet("QFrame#settingspopup {{ background: {}; border: 1px solid {}; }}".format(
            page["field"], page["border"]
        ))
        popup.setAutoFillBackground(True)
        view.setPalette(palette)

    def _nudge_volume_max(self, delta):
        self.volume_max = _volume_limit(self.volume_max + int(delta))
        self._show_volume_max()

    def _show_volume_max(self):
        self.vol_read.setText("{}%".format(self.volume_max))
        self.vol_down.setEnabled(self.volume_max > 100)
        self.vol_up.setEnabled(self.volume_max < VOLUME_MAX)


class MainWindow(QMainWindow):
    release_ready = Signal()

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
        self._chat_lines = []
        self._arm_play = None
        self._ready_until = {}
        self._pos_at = 0.0
        self._pos_when = time.monotonic()
        self._speed = 1.0
        self._paused = True
        self._playlist = []
        self._current_path = ""
        self._listed_path = ""
        self._repeat = 0
        self._alone_pending = False
        self._alone_until = 0.0
        self._alone_users_received = False
        self._eof_seen = False
        self._volume_until = 0
        self._hold_pause = None
        self._volume_open = False
        self._tracks_open = False
        self._room_names = set()
        self._room_was_ready = False
        self._volume_flash = False
        self._ready_people = []
        self._ready_born = None
        self._ready_leave = None
        self._tracks_lock = None
        self._muted = False
        self._chat_held = False
        self._known_names = None
        self._dev = dev_settings(app.store.data["appearance"].get("dev"))
        self._bar_h = int(self._dev.get("bar", BAR_HEIGHT))
        self._awake = SleepInhibit()
        icon = Path(__file__).resolve().parent / "icon.png"
        self._notes = Notifier(str(icon) if icon.is_file() else "")
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
        self._release = {"done": False, "version": None, "error": False}
        self._release_running = False
        self._begin_release_check()

    def _begin_release_check(self):
        if not self.app.store.data["appearance"].get("checkUpdates", True):
            return
        if self._release_running or self._release.get("done"):
            return
        self._release_running = True
        threading.Thread(target=self._release_worker, daemon=True).start()

    def _release_worker(self):
        try:
            found = fetch_newer_stable(__version__)
            self._release = {"done": True, "version": found, "error": False}
        except Exception:
            self._release = {"done": True, "version": None, "error": True}
        self._release_running = False
        try:
            self.release_ready.emit()
        except RuntimeError:
            pass

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
        self.board = NoticeBoard(column)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.video = Picture(self.app.runtime)
        self.video.fullscreenRequested.connect(self._toggle_full)
        self.video.volumeChanged.connect(self._show_volume)
        self.video.arrowPressed.connect(self._on_arrow)
        self.video.filesDropped.connect(self._add_dropped)
        self.video.enterPressed.connect(self._enter_chat)
        self.board.repaint_frame = self.video.redraw
        self.video.notes = self.board.paint_on
        col.addWidget(self.video, 1)

        self.bar = QWidget(column)
        self.bar.setObjectName("bar")
        self._overlay(self.bar)
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(10, 8, 10, 8)
        self.play = IconButton("play")
        self.elapsed = QLabel("0:00")
        self.slider = SeekBar(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.setRange(0, SEEK_STEPS)
        self.total = QLabel("0:00")
        self.volume_btn = IconButton("speaker")
        self.volume_btn.setCheckable(True)
        self.tracks_btn = IconButton("tracks")
        self.tracks_btn.setCheckable(True)
        self.tracks_btn.setEnabled(False)
        self.ready = IconButton("ready")
        self.ready.setCheckable(True)
        self.chat_btn = IconButton("chat")
        self.chat_btn.setCheckable(True)
        self.room = IconButton("room")
        self.room.setCheckable(True)
        self.play.clicked.connect(self._toggle_pause)
        self.slider.sliderReleased.connect(self._seek_released)
        self.volume_btn.clicked.connect(self._toggle_volume_popup)
        self.tracks_btn.clicked.connect(self._toggle_tracks_popup)
        self.ready.clicked.connect(self._toggle_ready)
        self.chat_btn.clicked.connect(self._toggle_chat_field)
        self.room.clicked.connect(self._toggle_room)
        for widget in (self.play, self.ready, self.elapsed, self.slider, self.total, self.volume_btn, self.tracks_btn, self.chat_btn, self.room):
            bar.addWidget(widget)
        for button in (self.play, self.ready, self.chat_btn, self.room, self.volume_btn, self.tracks_btn):
            button.setObjectName("baricon")
        bar.setStretchFactor(self.slider, 1)

        self.chat_line = QWidget(column)
        self.chat_line.setObjectName("chatline")
        self._overlay(self.chat_line)
        self.chat_line.hide()
        chat_row = QHBoxLayout(self.chat_line)
        chat_row.setContentsMargins(10, 0, 2, 0)
        chat_row.setSpacing(0)
        self.bar_message = QLineEdit()
        self._mark(self.bar_message, 4, "placeholder")
        self.bar_message.returnPressed.connect(self._send_bar_chat)
        self.bar_message.textChanged.connect(self._arm_chat_timer)
        self.bar_send = IconButton("send")
        self.bar_send.setFixedSize(32, 32)
        self.bar_send.setObjectName("baricon")
        self.bar_send.clicked.connect(self._send_bar_chat)
        chat_row.addWidget(self.bar_message, 1)
        chat_row.addWidget(self.bar_send, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.volume_box = QWidget(column)
        self.volume_box.setObjectName("volume")
        self._overlay(self.volume_box)
        self.volume_box.hide()
        volume_row = QHBoxLayout(self.volume_box)
        volume_row.setContentsMargins(12, 6, 12, 6)
        volume_row.setSpacing(12)
        self.mute_h = IconButton("mute")
        self.mute_h.setObjectName("muteicon")
        self.mute_h.setFixedSize(22, 22)
        self.mute_h.setCheckable(True)
        self.mute_h.clicked.connect(self._toggle_mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("volumebar")
        self.volume.setRange(0, VOLUME_MAX)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.valueChanged.connect(self._on_horizontal_volume)
        self.volume_text = QLabel("0")
        self.volume_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume_row.addWidget(self.mute_h)
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_text)
        self._lock_volume_digits()
        self._refresh_speaker()

        self.volume_pop = QWidget(column)
        self.volume_pop.setObjectName("volumepop")
        self._overlay(self.volume_pop)
        self.volume_pop.hide()
        self.volume_pop.setFixedWidth(56)
        volume_pop_col = QVBoxLayout(self.volume_pop)
        volume_pop_col.setContentsMargins(10, 8, 10, 10)
        volume_pop_col.setSpacing(6)
        self.volume_readout = QLabel("0")
        self.volume_readout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.volume_readout.setFixedWidth(36)
        self.volume_slider = QSlider(Qt.Orientation.Vertical)
        self.volume_slider.setObjectName("volumebar")
        self.volume_slider.setRange(0, VOLUME_MAX)
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume_slider.setFixedHeight(120)
        self.volume_slider.valueChanged.connect(self._on_vertical_volume)
        volume_pop_col.addWidget(self.volume_readout, 0, Qt.AlignmentFlag.AlignHCenter)
        volume_pop_col.addWidget(self.volume_slider, 1, Qt.AlignmentFlag.AlignHCenter)
        self.mute_v = IconButton("mute")
        self.mute_v.setParent(self.volume_pop)
        self.mute_v.setObjectName("muteicon")
        self.mute_v.setFixedSize(22, 22)
        self.mute_v.setCheckable(True)
        self.mute_v.clicked.connect(self._toggle_mute)

        self.tracks_pop = QWidget(column)
        self.tracks_pop.setObjectName("trackpop")
        self._overlay(self.tracks_pop)
        self.tracks_pop.hide()
        tracks_col = QVBoxLayout(self.tracks_pop)
        tracks_col.setContentsMargins(10, 8, 10, 8)
        tracks_col.setSpacing(2)

        row.addWidget(column, 1)

        self.panel = QWidget(column)
        self.panel.setObjectName("panel")
        self._overlay(self.panel)
        side = QVBoxLayout(self.panel)
        side.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(8)

        banner_row = QHBoxLayout()
        banner_row.setSpacing(8)
        self.banner = ClickBox()
        self.banner.setObjectName("banner")
        self.banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.banner.setAutoFillBackground(True)
        self.banner.setFixedHeight(44)
        self.banner.setCursor(Qt.CursorShape.PointingHandCursor)
        self.banner.clicked.connect(lambda: self._open_settings(0))
        inside = QHBoxLayout(self.banner)
        inside.setContentsMargins(14, 0, 14, 0)
        self.banner_text = QLabel(tr(5))
        self.banner_dot = QLabel("●")
        self.banner_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.banner_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        inside.addWidget(self.banner_text)
        inside.addStretch(1)
        inside.addWidget(self.banner_dot)
        self.gear = IconButton("gear")
        self.gear.setObjectName("panelicon")
        self.gear.clicked.connect(lambda: self._open_settings(1))
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(self.gear)
        side.addLayout(banner_row)

        self.reconnect = QPushButton()
        self._mark(self.reconnect, 10)
        self.reconnect.clicked.connect(self._reconnect)
        self.reconnect.hide()
        side.addWidget(self.reconnect)

        users_title = QLabel()
        users_title.setObjectName("heading")
        self._mark(users_title, 1)
        self.users_title = users_title
        side.addWidget(users_title)
        self.room_users = UserTable()
        side.addWidget(self.room_users)

        playlist_title = QLabel()
        playlist_title.setObjectName("heading")
        self._mark(playlist_title, 2)
        self.playlist_title = playlist_title
        side.addWidget(playlist_title)
        self.files = FileList()
        self.files.setObjectName("playlist")
        self.files.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files.removed.connect(self._remove_file)
        self.files.chosen.connect(lambda path: self._play_path(path, start=True))
        self.files.moved.connect(self._reorder_file)
        side.addWidget(self.files)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.hide()
        side.addWidget(self.status)

        chat_title = QLabel()
        chat_title.setObjectName("heading")
        self._mark(chat_title, 3)
        self.chat_title = chat_title
        side.addWidget(chat_title)
        self.chat = QTextEdit()
        self.chat.setObjectName("roomchat")
        self.chat.setReadOnly(True)
        self.chat.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side.addWidget(self.chat, 1)
        self.user_scroll = EdgeScroll(Qt.Orientation.Horizontal, self.panel)
        self.file_scroll = EdgeScroll(Qt.Orientation.Vertical, self.panel)
        self.chat_scroll = EdgeScroll(Qt.Orientation.Vertical, self.panel)
        self.user_scroll.attach(self.room_users.files_scroll.horizontalScrollBar())
        self.file_scroll.attach(self.files.verticalScrollBar())
        self.chat_scroll.attach(self.chat.verticalScrollBar())
        self.room_users.wheeled.connect(self.user_scroll.bump)
        self._panel_width = bounded_panel(self._dev.get("panel", self.app.store.data["appearance"].get("panelWidth")))
        self._grip = None
        self._chat_timer = QTimer(self)
        self._chat_timer.setSingleShot(True)
        self._chat_timer.timeout.connect(self._close_chat_if_empty)
        self.panel.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)
        hints = QGuiApplication.styleHints()
        changed = getattr(hints, "colorSchemeChanged", None)
        if changed is not None:
            changed.connect(self._on_system_theme)
        self._chat_keys = []
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self._enter_chat)
            self._chat_keys.append(shortcut)
        self._place_overlays()

    def _overlay(self, widget):
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        widget.setAutoFillBackground(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)

    def eventFilter(self, watched, event):
        if not isinstance(watched, QWidget) or watched.window() is not self:
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind == QEvent.Type.KeyPress and self._player_key(event):
            return True
        if kind == QEvent.Type.MouseButtonPress and self._press_edge(event):
            return True
        if kind == QEvent.Type.MouseButtonPress and self._press_grip(watched, event):
            return True
        if kind == QEvent.Type.MouseButtonPress:
            self._dismiss_panel(watched, event)
        if self._grip is not None and kind == QEvent.Type.MouseMove:
            self._drag_grip(event)
            return True
        if self._grip is not None and kind == QEvent.Type.MouseButtonRelease:
            self._grip = None
            self._save_panel_width()
            return True
        if kind == QEvent.Type.MouseMove and watched is self.panel:
            self._grip_cursor(event)
        if kind == QEvent.Type.MouseButtonPress and self._close_popups(watched):
            return False
        if watched is self.stage and kind == QEvent.Type.Resize:
            self._place_overlays()
        elif kind == QEvent.Type.Wheel:
            if hasattr(self, "files") and watched is self.files.viewport():
                self.file_scroll.bump()
            elif hasattr(self, "chat") and watched is self.chat.viewport():
                self.chat_scroll.bump()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._place_overlays()

    def _place_overlays(self):
        if not hasattr(self, "panel"):
            return
        width = self.stage.width()
        height = self.stage.height()
        inset = self._bar_height()
        gap = FLOAT_GAP if self._is_modern() else 0
        bar_rect = self._bar_rect()
        if self._bar_open:
            self.bar.setGeometry(bar_rect)
            self.bar.layout().activate()
        if self._panel_open:
            self.panel.setGeometry(self._panel_rect())
            self.panel.show()
        else:
            self.panel.hide()
        self._fit_playlist()
        box_w = max(1, int(round(width * 0.2)))
        box_h = 44
        if self._chat_open:
            self.chat_line.setGeometry(
                max(0, (width - box_w) // 2),
                max(0, height - inset - gap - 16 - box_h),
                box_w,
                box_h,
            )
            self.chat_line.show()
        else:
            self.chat_line.hide()
        self._place_edge_scrolls()
        box_width, box_height = 280, 40
        self.volume_box.setGeometry(
            max(0, (width - box_width) // 2),
            max(0, height - inset - gap - 90),
            min(box_width, width),
            box_height,
        )
        self._place_pops()
        self._stack_chrome()

    def _stack_chrome(self):
        if not hasattr(self, "bar"):
            return
        self.bar.raise_()
        self.panel.raise_()
        if self._chat_open:
            self.chat_line.raise_()
        self.volume_box.raise_()
        if self._volume_open or self._volume_flash:
            self.volume_pop.raise_()
        if self._tracks_open:
            self.tracks_pop.raise_()

    def _place_pops(self):
        if not hasattr(self, "volume_pop"):
            return
        show_volume = self._volume_open or self._volume_flash
        self.volume_pop.setVisible(show_volume)
        self.tracks_pop.setVisible(self._tracks_open)
        if show_volume:
            self._fit_volume_pop()
            hint = self.volume_pop.sizeHint()
            self._move_pop(self.volume_pop, self.volume_btn, self.volume_pop.width(), max(hint.height(), 1))
            self._place_volume_mute()
        if self._tracks_open:
            self.tracks_pop.layout().activate()
            hint = self.tracks_pop.sizeHint()
            width = max(160, min(280, hint.width()))
            height = max(48, hint.height())
            if self._tracks_lock is None:
                self._tracks_lock = (width, height)
            else:
                width = max(width, self._tracks_lock[0])
                height = max(height, self._tracks_lock[1])
            self._move_pop(self.tracks_pop, self.tracks_btn, width, height)

    def _fit_volume_pop(self):
        top = 8
        gap = 6
        number_h = self.volume_readout.sizeHint().height()
        above = top + number_h + gap
        layout = self.volume_pop.layout()
        layout.setContentsMargins(10, top, 10, above)
        layout.setSpacing(gap)
        self.volume_pop.setFixedWidth(max(56, self.volume_readout.width() + 20))
        layout.activate()

    def _place_volume_mute(self):
        band = self.volume_pop.layout().contentsMargins().bottom()
        side = self.mute_v.width()
        x = max(0, (self.volume_pop.width() - side) // 2)
        y = self.volume_pop.height() - band + max(0, (band - side) // 2)
        self.mute_v.setGeometry(x, y, side, side)
        self.mute_v.raise_()

    def _move_pop(self, popup, button, width, height):
        origin = button.mapTo(self.stage, QPoint(0, 0))
        x = origin.x() + button.width() // 2 - width // 2
        bar_top = self.bar.mapTo(self.stage, QPoint(0, 0)).y()
        y = bar_top - height - POP_GAP
        x = max(8, min(x, max(8, self.stage.width() - width - 8)))
        y = max(8, y)
        if popup.geometry() == QRect(x, y, width, height):
            return
        popup.setGeometry(x, y, width, height)

    def _inside(self, widget, target):
        while widget is not None:
            if widget is target:
                return True
            widget = widget.parentWidget()
        return False

    def _dismiss_panel(self, watched, event):
        if not self._panel_open:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        widget = watched if isinstance(watched, QWidget) else None
        if widget is None or widget.window() is not self:
            return
        if self._inside(widget, self.panel) or self._inside(widget, self.bar):
            return
        point = event.globalPosition().toPoint()
        if any(target.isVisible() and target.rect().contains(target.mapFromGlobal(point))
               for target in (self.panel, self.bar, self.volume_pop, self.tracks_pop, self.chat_line)):
            return
        self.set_panel(False)

    def _popup_widget(self, widget):
        while widget is not None:
            if widget in (self.volume_pop, self.tracks_pop, self.volume_btn, self.tracks_btn):
                return True
            widget = widget.parentWidget()
        return False

    def _close_popups(self, watched):
        if not self._volume_open and not self._tracks_open:
            return False
        if self._popup_widget(watched):
            return False
        self._volume_open = False
        self._tracks_open = False
        self.volume_btn.setChecked(False)
        self.tracks_btn.setChecked(False)
        self._tracks_lock = None
        self.volume_pop.hide()
        self.tracks_pop.hide()
        return False

    def _toggle_volume_popup(self):
        self._volume_open = not self._volume_open
        self.volume_btn.setChecked(self._volume_open)
        if self._volume_open:
            self._tracks_open = False
            self.tracks_btn.setChecked(False)
            self.tracks_pop.hide()
            self._sync_volume_slider(self.volume.value())
            self._set_bar(True)
        self._place_overlays()

    def _on_vertical_volume(self, value):
        level = int(value)
        self._set("volume", level)
        ceiling = self.volume_slider.maximum()
        if self.volume.maximum() != ceiling:
            self.volume.setRange(0, ceiling)
        self.volume.blockSignals(True)
        self.volume.setValue(level)
        self.volume.blockSignals(False)
        self.volume_text.setText(str(level))
        self.volume_readout.setText(str(level))

    def _on_horizontal_volume(self, value):
        level = int(value)
        self._set("volume", level)
        self.volume_text.setText(str(level))
        self._sync_volume_slider(level)

    def _sync_volume_slider(self, level):
        if not hasattr(self, "volume_slider"):
            return
        ceiling = self.volume.maximum()
        self.volume_slider.blockSignals(True)
        if self.volume_slider.maximum() != ceiling:
            self.volume_slider.setRange(0, ceiling)
        self.volume_slider.setValue(int(level))
        self.volume_slider.blockSignals(False)
        self.volume_readout.setText(str(int(level)))
        self._refresh_speaker()

    def _refresh_speaker(self):
        if not hasattr(self, "volume_btn"):
            return
        level = self.volume.value() if hasattr(self, "volume") else 0
        self.volume_btn.set_silent(self._muted or int(level) <= 0)

    def _toggle_tracks_popup(self):
        if not self._playlist:
            self._tracks_open = False
            self.tracks_btn.setChecked(False)
            self.tracks_pop.hide()
            return
        self._tracks_open = not self._tracks_open
        self.tracks_btn.setChecked(self._tracks_open)
        if self._tracks_open:
            self._volume_open = False
            self.volume_btn.setChecked(False)
            self.volume_pop.hide()
            self._tracks_lock = None
            self._fill_tracks()
            self._set_bar(True)
        else:
            self._tracks_lock = None
        self._place_overlays()

    def _track_name(self, track):
        title = str(track.get("title") or "").strip()
        lang = str(track.get("lang") or "").strip()
        if title and lang and lang.lower() not in title.lower():
            return "{} ({})".format(title, lang)
        if title:
            return title
        if lang:
            return lang
        return trf(14, track.get("id"))

    def _fill_tracks(self):
        layout = self.tracks_pop.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        raw = self._get("track-list") or []
        if not isinstance(raw, list):
            raw = []
        subs = [track for track in raw if isinstance(track, dict) and track.get("type") == "sub"]
        audios = [track for track in raw if isinstance(track, dict) and track.get("type") == "audio"]
        if subs:
            self._track_heading(layout, tr(12))
            for track in subs:
                self._track_row(layout, track, "sid")
        self._track_heading(layout, tr(13))
        for track in audios:
            self._track_row(layout, track, "aid")
        layout.activate()

    def _track_heading(self, layout, text):
        label = QLabel(text)
        label.setObjectName("heading")
        layout.addWidget(label)

    def _track_row(self, layout, track, kind):
        button = QPushButton(self._track_name(track))
        button.setObjectName("trackrow")
        button.setCheckable(True)
        button.setChecked(bool(track.get("selected")))
        button.setMinimumHeight(28)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        ident = track.get("id")
        button.clicked.connect(lambda _checked=False, name=kind, track_id=ident: self._pick_track(name, track_id))
        layout.addWidget(button)

    def _pick_track(self, kind, track_id):
        if track_id is None:
            return
        self._set(kind, track_id)
        self._fill_tracks()
        self._place_overlays()

    def _is_modern(self):
        return self.app.store.data["appearance"].get("style") == "modern"

    def _bar_height(self):
        return getattr(self, "_bar_h", BAR_HEIGHT)

    def apply_dev(self, spec):
        self._dev = dev_settings(spec)
        self._bar_h = int(spec["bar"])
        self._panel_width = bounded_panel(spec["panel"])
        self.apply_theme()

    def _fill_from_store(self):
        self._refresh_banner()

    def apply_theme(self, light=False):
        appearance = self.app.store.data["appearance"]
        theme = _shown_theme(appearance.get("theme"))
        state = (theme, {key: appearance.get(key) for key in (
            "accentColor", "accentColor2", "uiFontSize", "chatFontSize",
            "subFont", "subFontSize", "subColor", "style")}, deepcopy(self._dev))
        if state == getattr(self, "_theme_state", None):
            return
        self._theme_state = state
        accent = appearance.get("accentColor")
        self.setStyleSheet(_stylesheet(theme, accent, self._face_paint(theme)) + self._chrome_css(theme))
        dev = self._dev or {}
        ui = dev.get("ui") or {}
        ui_point = max(1, min(96, int(ui.get("size") or appearance.get("uiFontSize") or 13)))
        font = QFont()
        if ui.get("family"):
            font.setFamily(ui["family"])
        font.setBold(bool(ui.get("bold")))
        font.setPointSize(ui_point)
        if QApplication.instance().font() != font:
            QApplication.instance().setFont(font)
        self.setFont(font)
        alfa_spec = dev.get("alfa") or {}
        alfa = max(1, min(96, int(alfa_spec.get("size") or 10)))
        block = QFont(font)
        if alfa_spec.get("family"):
            block.setFamily(alfa_spec["family"])
        block.setBold(bool(alfa_spec.get("bold")))
        block.setPointSize(alfa)
        self.chat.setFont(block)
        self.chat.document().setDefaultFont(block)
        text_css = "{}pt".format(alfa)
        self.room_users._text_css = text_css
        self.files.setFont(block)
        self.room_users.setFont(block)
        plain = QFont(block)
        plain.setBold(False)
        if hasattr(self, "volume_text"):
            self.volume_text.setFont(plain)
        if hasattr(self, "volume_readout"):
            self.volume_readout.setFont(plain)
        self._lock_volume_digits()
        titles = dev.get("titles") or {}
        beta = max(1, min(96, int(titles.get("size") or ui_point)))
        alfa_family = _css_family(alfa_spec.get("family"))
        beta_family = _css_family(titles.get("family"))
        ui_family = _css_family(ui.get("family"))
        alfa_weight = 700 if alfa_spec.get("bold") else 400
        beta_weight = 700 if titles.get("bold", True) else 400
        ui_weight = 700 if ui.get("bold") else 400
        alfa_ink = _dev_ink(alfa_spec, theme)
        beta_ink = _dev_ink(titles, theme)
        alfa_color = " color: {};".format(alfa_ink) if alfa_ink else ""
        beta_color = " color: {};".format(beta_ink) if beta_ink else ""
        self.setStyleSheet(
            self.styleSheet()
            + """
            QMainWindow, QDialog, QWidget {{
                font-size: {ui_size}pt;
                font-weight: {ui_weight};{ui_family}
            }}
            QTextEdit#roomchat, QListWidget#playlist, QListWidget#playlist::item,
            QWidget#usersbox QLabel {{
                font-size: {size};
                font-weight: {alfa_weight};{alfa_family}{alfa_color}
            }}
            QWidget#volume QLabel, QWidget#volumepop QLabel, QPushButton#trackrow {{
                font-size: {alfa}pt;
                font-weight: 400;{alfa_family}{alfa_color}
            }}
            QWidget#trackpop QLabel#heading {{
                font-size: {beta}pt;
                font-weight: {beta_weight};{beta_family}{beta_color}
            }}
            """.format(
                ui_size=ui_point,
                ui_weight=ui_weight,
                ui_family=ui_family,
                size=text_css,
                alfa=alfa,
                beta=beta,
                alfa_family=alfa_family,
                alfa_weight=alfa_weight,
                alfa_color=alfa_color,
                beta_family=beta_family,
                beta_weight=beta_weight,
                beta_color=beta_color,
            )
        )
        ink = _dev_ink(ui, theme)
        if ink:
            self.setStyleSheet(self.styleSheet() + " QLabel {{ color: {}; }}".format(ink))
        self.setFont(font)
        self._apply_subtitles()
        self._refresh_osd()
        pal = _palette(theme, appearance.get("accentColor"))
        for button in (self.play, self.ready, self.chat_btn, self.room, self.gear, self.bar_send, self.volume_btn, self.tracks_btn, self.mute_h, self.mute_v):
            button.set_ink(pal["button_fg"], pal["on_fg"], pal["accent"])
        self._refresh_banner()
        self._refresh_files()
        self._paint_chat()
        self._paint_users()
        self._style_titles()
        self._apply_skin()
        self._apply_bar_buttons()
        self._place_overlays()

    def _face_paint(self, theme):
        face = (self._dev or {}).get("face") or {}
        paint = {}
        for key in ("bg", "field", "border", "button", "button_fg"):
            ink = _dev_ink(face.get(key), theme)
            if ink:
                paint[key] = ink
        return paint

    def _chrome_css(self, theme):
        pal = _palette(theme, self.app.store.data["appearance"].get("accentColor"))
        pal.update(self._face_paint(theme))
        dev = self._dev or {}
        modern = self._is_modern()
        radius = 12 if modern else 0
        bar_alpha = dev.get("bar_alpha", 90)
        panel_alpha = dev.get("panel_alpha", 90)
        bar = _rgba(pal["bg"], bar_alpha)
        panel = _rgba(pal["bg"], panel_alpha)
        return (
            "QWidget#bar {{"
            " background-color: {bar}; border: none; border-radius: {radius}px; }}"
            "QWidget#panel {{"
            " background-color: {panel}; border: none; border-radius: {radius}px; }}"
            "QWidget#chatline, QWidget#volume, QWidget#volumepop, QWidget#trackpop {{"
            " background-color: {bar}; border: none; }}"
            "QWidget#bar QLabel, QWidget#volume QLabel {{ background: transparent; }}"
        ).format(bar=bar, panel=panel, radius=radius)

    def _apply_bar_buttons(self):
        flags = (self._dev or {}).get("bar_buttons") or {}
        modern = self._is_modern()
        mapping = {
            "play": self.play,
            "ready": self.ready,
            "volume": self.volume_btn,
            "tracks": self.tracks_btn,
            "chat": self.chat_btn,
            "room": self.room,
        }
        shown = {key: bool(flags.get(key, True)) for key in mapping}
        shown["ready"] &= not modern
        shown["chat"] &= not modern
        shown["tracks"] &= self._tracks_useful()
        changed = False
        for key, widget in mapping.items():
            if widget.isHidden() == shown[key]:
                widget.setVisible(shown[key])
                changed = True
        if not shown["volume"]:
            self._volume_open = False
            self.volume_pop.hide()
        if not shown["tracks"]:
            self._tracks_open = False
            self.tracks_btn.setChecked(False)
            self.tracks_pop.hide()
        if not modern and not shown["chat"]:
            self._chat_open = False
            self.chat_line.hide()
        if changed:
            self._place_overlays()

    def _tracks_useful(self):
        raw = self._get("track-list") or []
        if not isinstance(raw, list):
            return False
        subs = 0
        audios = 0
        for track in raw:
            if not isinstance(track, dict):
                continue
            kind = track.get("type")
            if kind == "sub":
                subs += 1
            elif kind == "audio":
                audios += 1
        return subs > 0 or audios > 1

    def _bar_cut(self):
        if not self._is_modern():
            return 0
        cut = (self._dev or {}).get("bar_inset", 30)
        try:
            return max(0, min(40, int(cut)))
        except (TypeError, ValueError):
            return 30

    def _apply_skin(self):
        theme = _shown_theme(self.app.store.data["appearance"].get("theme"))
        face = (self._dev or {}).get("face") or {}
        ready = _dev_ink(face.get("ready"), theme) or "#3EAD62"
        away = _dev_ink(face.get("away"), theme) or "#C4453C"
        if hasattr(self, "ready"):
            self.ready._ready_on = QColor(ready)
            self.ready._ready_off = QColor(away)
            self.ready.update()
        if hasattr(self, "board"):
            self.board.ready_on = ready
            self.board.ready_off = away
            percent = int((self._dev or {}).get("osd_alpha", 90))
            self.board.plate_alpha = max(0, min(255, int(round(percent / 100.0 * 255))))

    def _style_titles(self):
        spec = (self._dev or {}).get("titles") or {}
        theme = _shown_theme(self.app.store.data["appearance"].get("theme"))
        ink = _dev_ink(spec, theme)
        css = "background: transparent; font-size: {}pt; font-weight: {};".format(
            int(spec.get("size") or 11),
            700 if spec.get("bold", True) else 400,
        )
        if spec.get("family"):
            css += ' font-family: "{}";'.format(spec["family"])
        if ink:
            css += " color: {};".format(ink)
        for label in (self.users_title, self.playlist_title, self.chat_title):
            label.setStyleSheet(css)

    def set_player(self, player):
        listener = getattr(player, "_listener", None) if player is not None else None
        self.ctl = getattr(listener, "mpvpipe", None)
        self._apply_volume_max()
        self._apply_subtitles()

    def _apply_subtitles(self):
        if self.ctl is None:
            return
        look = self.app.store.data["appearance"]
        theme = _shown_theme(look.get("theme"))
        dev = (self._dev or {}).get("sub")
        if dev:
            family = font_name(dev.get("family"))
            size = int(dev.get("size") or 55)
            color = hex_color(_dev_ink(dev, theme), "#FFFFFF")
            bold = "yes" if dev.get("bold") else "no"
        else:
            family = font_name(look.get("subFont"))
            size = int(look.get("subFontSize") or 55)
            color = hex_color(look.get("subColor"), "#FFFFFF")
            bold = "no"
        self._set("sub-font", family)
        self._set("sub-font-size", size)
        self._set("sub-bold", bold)
        self._set("sub-color", "#FF" + color[1:])
        self._set("sub-ass-override", "force")

    def set_panel(self, open_, animate=True):
        open_ = bool(open_)
        was_open = self._panel_open
        if was_open == open_:
            if open_ and not self._bar_open:
                self._set_bar(True)
            else:
                self._place_overlays()
            return
        self._panel_open = open_
        self.room.setChecked(open_)
        if was_open and not open_:
            self._last_move = time.monotonic()
        self._slide_panel(animate)
        if open_ and not self._bar_open:
            self._set_bar(True)
        else:
            self._place_overlays()

    def _bar_rect(self):
        width = self.stage.width()
        height = self.stage.height()
        inset = self._bar_height()
        gap = FLOAT_GAP if self._is_modern() else 0
        side = max(gap, int(round(width * self._bar_cut() / 100.0)))
        # Fixed-size controls must fit even when the floating bar is narrow.
        minimum = self.bar.layout().minimumSize().width()
        side = max(0, min(side, (width - minimum) // 2))
        return QRect(side, max(0, height - inset - gap), max(1, width - side * 2), inset)

    def _panel_rect(self):
        width = self.stage.width()
        height = self.stage.height()
        inset = self._bar_height()
        gap = FLOAT_GAP if self._is_modern() else 0
        lift = POP_GAP if gap else 0
        panel_width = self._panel_span(width)
        panel_height = max(0, height - inset - gap - lift - gap)
        return QRect(max(0, width - panel_width - gap), gap, panel_width, panel_height)

    def _slide_panel(self, animate):
        end = self._panel_rect()
        self.panel.setGeometry(end)
        self.panel.setVisible(self._panel_open)

    def _slide_bar(self, animate):
        end = self._bar_rect()
        self.bar.setGeometry(end)
        self.bar.setVisible(self._bar_open)

    def _panel_span(self, width):
        room = max(PANEL_MIN, width - 80)
        return max(PANEL_MIN, min(self._panel_width, PANEL_MAX, room))

    def _press_edge(self, event):
        if not self.isFullScreen():
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._panel_open and self.panel.rect().contains(self.panel.mapFromGlobal(event.globalPosition().toPoint())):
            return False
        screen = self.screen()
        if screen is None:
            return False
        if event.globalPosition().x() < screen.geometry().right() - (EDGE_PX - 1):
            return False
        self.set_panel(not self._panel_open)
        return True

    def _press_grip(self, watched, event):
        if watched is not self.panel or not self._panel_open:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        local = self.panel.mapFromGlobal(event.globalPosition().toPoint())
        if local.x() > GRIP_PX or local.y() < 0 or local.y() > self.panel.height():
            return False
        self._grip = (event.globalPosition().x(), self._panel_width)
        return True

    def _drag_grip(self, event):
        start_x, start_w = self._grip
        delta = start_x - event.globalPosition().x()
        self._panel_width = bounded_panel(start_w + delta)
        self._place_overlays()

    def _save_panel_width(self):
        self.app.store.data["appearance"]["panelWidth"] = bounded_panel(self._panel_width)
        if self._dev:
            self._dev["panel"] = bounded_panel(self._panel_width)
            self.app.store.data["appearance"]["dev"] = deepcopy(self._dev)
        self.app.store.save()

    def _grip_cursor(self, event):
        local = self.panel.mapFromGlobal(event.globalPosition().toPoint())
        if 0 <= local.x() <= GRIP_PX:
            self.panel.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.panel.unsetCursor()

    def _on_system_theme(self, *_args):
        if self.app.store.data["appearance"].get("theme") == "auto":
            self.apply_theme()

    def _toggle_room(self):
        self.set_panel(not self._panel_open)

    def _set_bar(self, open_):
        if self._panel_open or self._chat_open or self._volume_open or self._tracks_open:
            open_ = True
        if open_ == self._bar_open:
            return
        self._bar_open = open_
        self._slide_bar(True)
        self._place_overlays()

    def _toggle_chat_field(self):
        if self._chat_open:
            self._close_chat_field()
            return
        self._open_chat_field()

    def _enter_chat(self):
        if not (self._chat_open and self.chat_line.isVisible()):
            self._open_chat_field()
            return
        if not self.bar_message.hasFocus():
            self.chat_line.raise_()
            self.bar_message.setFocus()
            return
        self._send_bar_chat()

    def _open_chat_field(self):
        self._chat_open = True
        self.chat_btn.setChecked(True)
        self._set_bar(True)
        self._place_overlays()
        self.bar_message.setFocus()
        self._arm_chat_timer()

    def _close_chat_field(self):
        self._chat_open = False
        self.chat_btn.setChecked(False)
        self._chat_timer.stop()
        self._last_move = time.monotonic()
        self._place_overlays()

    def _close_chat_if_empty(self):
        if self._chat_open and not self.bar_message.text().strip():
            self._close_chat_field()

    def _arm_chat_timer(self, *_args):
        if not self._chat_open:
            return
        if self.bar_message.text().strip():
            self._chat_timer.stop()
            return
        self._chat_timer.start(5000)

    def _lock_volume_digits(self):
        if not hasattr(self, "volume_text"):
            return
        metrics = QFontMetrics(self.volume_text.font())
        width = max(metrics.horizontalAdvance(str(level)) for level in range(VOLUME_MAX + 1))
        self.volume_text.setFixedWidth(width)
        if hasattr(self, "volume_readout"):
            self.volume_readout.setFixedWidth(width)

    def _show_volume(self, level):
        if self._muted:
            self._set_muted(False)
        ceiling = self._volume_ceiling()
        level = max(0, min(ceiling, int(level)))
        if self.volume.maximum() != ceiling:
            self.volume.setRange(0, ceiling)
        self.volume.blockSignals(True)
        self.volume.setValue(level)
        self.volume.blockSignals(False)
        self.volume_text.setText(str(level))
        self._sync_volume_slider(level)
        self._volume_until = time.monotonic() + VOLUME_LIFE
        if self._volume_overlay() == "vertical":
            self.volume_box.hide()
            self._volume_flash = True
            self._place_overlays()
            return
        self._volume_flash = False
        if not self._volume_open:
            self.volume_pop.hide()
        self.volume_box.show()
        self.volume_box.raise_()

    def _toggle_mute(self):
        self._set_muted(not self._muted)

    def _set_muted(self, muted):
        self._muted = bool(muted)
        self._set("mute", "yes" if self._muted else "no")
        for button in (self.mute_h, self.mute_v):
            button.blockSignals(True)
            button.setChecked(self._muted)
            button.blockSignals(False)
            button.update()
        self._refresh_speaker()

    def _volume_overlay(self):
        mode = self.app.store.data["appearance"].get("volumeOverlay") or "horizontal"
        return "vertical" if mode == "vertical" else "horizontal"

    def _saved_volume_max(self):
        return _volume_limit(self.app.store.data["appearance"].get("volumeMax", 100))

    def _apply_volume_max(self):
        ceiling = self._saved_volume_max()
        self._set("volume-max", ceiling)
        if hasattr(self, "volume"):
            self.volume.setRange(0, ceiling)
        if hasattr(self, "volume_slider"):
            self.volume_slider.blockSignals(True)
            self.volume_slider.setRange(0, ceiling)
            self.volume_slider.blockSignals(False)
        raw = self._get("volume")
        try:
            level = int(round(float(raw)))
        except (TypeError, ValueError):
            return
        if level > ceiling:
            self._set("volume", ceiling)
            level = ceiling
        if hasattr(self, "volume"):
            self.volume.blockSignals(True)
            self.volume.setValue(level)
            self.volume.blockSignals(False)
            self.volume_text.setText(str(level))
        self._sync_volume_slider(level)

    def _volume_ceiling(self):
        raw = self._get("volume-max")
        try:
            value = int(round(float(raw)))
        except (TypeError, ValueError):
            value = self._saved_volume_max()
        return max(100, min(VOLUME_MAX, value))

    def _typing(self):
        widget = QApplication.focusWidget()
        if isinstance(widget, (QLineEdit, QSpinBox)):
            return True
        return isinstance(widget, QTextEdit) and not widget.isReadOnly()

    def _player_key(self, event):
        if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
            return False
        if self._typing():
            return False
        key = int(event.key())
        if key == int(Qt.Key.Key_Space):
            if not event.isAutoRepeat():
                self._toggle_pause()
            return True
        # XKB adds eight to Linux key codes, independently of the layout.
        physical = event.nativeScanCode() if QGuiApplication.platformName() in ("xcb", "wayland", "wayland-egl") else 0
        if key == int(Qt.Key.Key_M) or physical == 58:
            if not event.isAutoRepeat():
                self._toggle_mute()
            return True
        if key == int(Qt.Key.Key_R) or physical == 27:
            if not event.isAutoRepeat():
                self._repeat = (self._repeat + 1) % 3
                self._refresh_osd()
            return True
        if key in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter)):
            if not event.isAutoRepeat():
                self._enter_chat()
            return True
        return self._on_arrow(key)

    def keyPressEvent(self, event):
        if not self._typing() and self._on_arrow(int(event.key())):
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_arrow(self, key):
        if self._typing():
            return False
        if key == int(Qt.Key.Key_Left):
            self._seek_by(-5)
        elif key == int(Qt.Key.Key_Right):
            self._seek_by(5)
        elif key == int(Qt.Key.Key_Up):
            self._volume_step(10)
        elif key == int(Qt.Key.Key_Down):
            self._volume_step(-10)
        else:
            return False
        return True

    def _seek_by(self, delta):
        shown = self._shown_position() + delta
        if self._duration > 0:
            shown = min(self._duration, shown)
        shown = max(0.0, shown)
        self._pos_at = shown
        self._pos_when = time.monotonic()
        self._cmd("seek", str(delta), "relative")
        self._move_knob()

    def _volume_step(self, delta):
        ceiling = self._volume_ceiling()
        raw = self._get("volume")
        try:
            level = int(round(float(raw)))
        except (TypeError, ValueError):
            level = 0
        level = max(0, min(ceiling, level + int(delta)))
        self._set("volume", level)
        self._show_volume(level)

    def _place_edge_scrolls(self):
        if not hasattr(self, "user_scroll") or not self._panel_open:
            return
        layout = self.panel.layout()
        if layout is not None:
            layout.activate()
        box = self.room_users.geometry()
        self.user_scroll.setGeometry(box.x() + 8, box.bottom() + 1, max(12, box.width() - 16), 3)
        for widget, bar in ((self.files, self.file_scroll), (self.chat, self.chat_scroll)):
            geo = widget.geometry()
            bar.setGeometry(geo.right() + 1, geo.y() + 6, 3, max(12, geo.height() - 12))
        for bar in (self.user_scroll, self.file_scroll, self.chat_scroll):
            if bar.isVisible():
                bar.raise_()

    def _toggle_pause(self):
        loaded = str(self._get("path") or "")
        wanted = self._current_path
        same = bool(wanted) and bool(loaded) and (
            loaded == wanted or Path(loaded).name == Path(wanted).name
        )
        if wanted and not same:
            self._play_path(wanted, start=True)
            return
        self._hold_pause = None
        eof = self._get("eof-reached")
        if eof in (True, "yes", "true", 1) and len(self._playlist) == 1:
            self._restart_current()
            return
        self._cmd("cycle", "pause")

    def _restart_current(self):
        self._arm_play = None
        self._hold_pause = None
        self._cmd("seek", "0", "absolute")
        self._set("pause", "no")
        self._paused = False
        self._pos_at = 0
        self._pos_when = time.monotonic()
        self._eof_seen = True

    def _add_dropped(self, paths):
        batch = []
        known = {item["path"] for item in self._playlist}
        for path in paths:
            if not path or path in known:
                continue
            batch.append({"path": path, "name": Path(path).name})
            known.add(path)
        batch.sort(key=lambda item: _natural(item["name"]))
        fresh = not self._playlist
        self._playlist.extend(batch)
        if not batch:
            self._refresh_files()
            return
        if fresh:
            # Open paused so the room sees the file. Do not start playback.
            self._play_path(batch[0]["path"], start=False)
            return
        self._refresh_files()

    def _play_path(self, path, start=False):
        self._current_path = path
        self._eof_seen = True
        self._paused = not start
        self._pos_at = 0
        self._pos_when = time.monotonic()
        self._arm_play = path if start else None
        self._hold_pause = None if start else path
        client = getattr(self.app, "client", None)
        player = getattr(client, "_player", None) if client is not None else None
        if player is not None:
            from twisted.internet import reactor
            reactor.callFromThread(client.openFile, path, True)
        elif self.video.mpv is not None:
            try:
                if start:
                    self.video.mpv.command("loadfile", path, "replace", "start=0")
                else:
                    self.video.mpv.command("loadfile", path, "replace", "pause=yes")
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
        self._play_path(self._playlist[nxt]["path"], start=True)

    def _reorder_file(self, path, dest):
        index = next((i for i, item in enumerate(self._playlist) if item["path"] == path), -1)
        if index < 0:
            return
        move_entry(self._playlist, index, dest)
        self._refresh_files()

    def _advance(self):
        index = next((i for i, item in enumerate(self._playlist) if item["path"] == self._current_path), -1)
        if index < 0:
            return
        next_index = index if self._repeat == 1 else index + 1
        if next_index >= len(self._playlist):
            if self._repeat != 2:
                return
            next_index = 0
        auto = bool(self._repeat or self.app.store.data["appearance"].get("autoplayNext"))
        path = self._playlist[next_index]["path"]
        if path == self._current_path:
            self._restart_current()
        else:
            client = getattr(self.app, "client", None)
            if auto and getattr(client, "_player", None) is not None:
                from twisted.internet import reactor
                # Match Syncplay's advance marker so its rewind guard does not re-pause playback.
                reactor.callFromThread(setattr, client, "lastAdvanceTime", time.time())
            self._play_path(path, start=auto)

    def _refresh_files(self):
        if not hasattr(self, "files"):
            return
        appearance = self.app.store.data["appearance"]
        theme = _shown_theme(appearance.get("theme"))
        pal = _palette(theme, appearance.get("accentColor"))
        pal.update(self._face_paint(theme))
        row_h = max(24, QFontMetrics(self.files.font()).height() + 12)
        scroll = self.files.verticalScrollBar().value()
        self.files.clear()
        for index, item in enumerate(self._playlist, start=1):
            row = QListWidgetItem("{}. {}".format(index, item["name"]))
            row.setSizeHint(QSize(0, row_h))
            row.setData(Qt.ItemDataRole.UserRole, item["path"])
            if item["path"] == self._current_path:
                row.setBackground(QColor(pal["accent"]))
                row.setForeground(QColor(pal["on_fg"]))
            self.files.addItem(row)
        self.files.set_mark(pal["accent"], pal["border"])
        resized = self._fit_playlist()
        if self._listed_path != self._current_path:
            self._center_current_file()
        elif not resized:
            self.files.verticalScrollBar().setValue(scroll)
        self._listed_path = self._current_path
        has_files = bool(self._playlist)
        self.tracks_btn.setEnabled(has_files)
        if not has_files and self._tracks_open:
            self._tracks_open = False
            self.tracks_btn.setChecked(False)
            self.tracks_pop.hide()
        self._place_edge_scrolls()

    def _fit_playlist(self):
        if not hasattr(self, "chat"):
            return False
        layout = self.panel.layout()
        chat_max = int(self._dev.get("chat_max") or 16777215)
        self.chat.setMaximumHeight(chat_max)
        margins = layout.contentsMargins()
        visible = [layout.itemAt(index) for index in range(layout.count()) if not layout.itemAt(index).isEmpty()]
        fixed = 0
        width = max(1, self.panel.width() - margins.left() - margins.right())
        for item in visible:
            if item.widget() in (self.files, self.chat):
                continue
            fixed += max(item.minimumSize().height(), item.heightForWidth(width) if item.hasHeightForWidth() else 0)
        panel_height = self._panel_rect().height()
        available = panel_height - margins.top() - margins.bottom() - fixed - layout.spacing() * max(0, len(visible) - 1)
        chat_min = min(chat_max, max(self.chat.minimumSizeHint().height(), QFontMetrics(self.chat.font()).lineSpacing() * 3 + 12))
        row_h = max(24, QFontMetrics(self.files.font()).height() + 12)
        frame = self.files.frameWidth() * 2
        rows = min(12, max(3, self.files.count()), max(0, (available - chat_min - frame) // row_h))
        height = rows * row_h + frame
        changed = self.files.height() != height
        self.files.setFixedHeight(height)
        unused = max(0, available - height - chat_max)
        self.panel.resize(self.panel.width(), panel_height - unused)
        layout.activate()
        if changed:
            self._center_current_file()
        return changed

    def _center_current_file(self):
        self.files.doItemsLayout()
        if self.files.verticalScrollBar().maximum() <= 0:
            return
        for index in range(self.files.count()):
            item = self.files.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == self._current_path:
                rows = max(1, self.files.viewport().height() // max(1, item.sizeHint().height()))
                self.files.verticalScrollBar().setValue(index - (rows - 1) // 2)
                break

    def _toggle_ready(self):
        client = getattr(self.app, "client", None)
        if client is None:
            return
        from twisted.internet import reactor
        reactor.callFromThread(client.toggleReady)

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

    def _connection_changed(self, values):
        old = self.app.store.data["connection"]

        def norm(key, value):
            if key == "port":
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 8999
            return str(value or "")

        return any(norm(key, old.get(key)) != norm(key, values.get(key)) for key in ("host", "port", "name", "password", "room"))

    def _mark(self, widget, number, kind="text"):
        widget.setProperty("phrase", int(number))
        widget.setProperty("phraseKind", kind)
        self._apply_phrase(widget, number)

    def _apply_phrase(self, widget, number):
        shown = tr(number)
        if widget.property("phraseKind") == "placeholder":
            widget.setPlaceholderText(shown)
        else:
            widget.setText(shown)

    def _retranslate(self):
        for widget in self.findChildren(QWidget):
            number = widget.property("phrase")
            if number:
                self._apply_phrase(widget, number)
        self._refresh_banner()
        if self._tracks_open:
            self._fill_tracks()

    def _open_settings(self, page=1):
        dialog = SettingsDialog(
            self.app.store.data["appearance"],
            self.app.store.data["connection"],
            self,
            page,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.appearance:
            return
        before = deepcopy(self.app.store.data["appearance"])
        self.app.on_command({"c": "appearance", **dialog.appearance})
        after = self.app.store.data["appearance"]
        if any(before.get(key) != after.get(key) for key in (
                "theme", "style", "accentColor", "accentColor2", "uiFontSize",
                "chatFontSize", "subFont", "subFontSize", "subColor")):
            self.apply_theme()
        if before.get("volumeMax") != after.get("volumeMax"):
            self._apply_volume_max()
        if before.get("language") != after.get("language"):
            self._retranslate()
        if before.get("panelWidth") != after.get("panelWidth") and "panel" not in self._dev:
            self._panel_width = bounded_panel(after["panelWidth"])
            self._place_overlays()
        if dialog.connection and (dialog.wants_connect or self._connection_changed(dialog.connection)):
            self.app.on_command({"c": "connect", **dialog.connection})
            self._refresh_banner()

    def _send_bar_chat(self):
        text = self.bar_message.text().strip()
        if not text:
            self._close_chat_field()
            return
        client = getattr(self.app, "client", None)
        running = client is not None and getattr(client, "_running", False)
        if not self._connected or not running:
            self._chat_held = True
            self._refresh_banner()
            return
        self._chat_held = False
        self.app.on_command({"c": "chat", "text": text})
        self.bar_message.clear()
        self._close_chat_field()

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
        if self.video.error:
            self._set_status(self.video.error)
        self._follow_cursor()
        if self.volume_box.isVisible() and time.monotonic() >= self._volume_until:
            self.volume_box.hide()
        if self._volume_flash and time.monotonic() >= self._volume_until:
            self._volume_flash = False
            if not self._volume_open:
                self.volume_pop.hide()
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
        was = self._connected
        self._connected = state == "connected"
        if not self._connected:
            self._alone_pending = False
            self._alone_until = 0.0
            self._alone_users_received = False
        elif not was:
            self._alone_pending = True
            self._alone_until = 0.0
            if self._alone_users_received:
                self._check_alone_on_entry()
        self._failed = state == "failed"
        if state == "failed":
            self._set_status(event.get("text") or "")
        if state == "connected":
            self._set_status("")
        if self._connected and not was:
            self._notify_background("yucha", tr(6))
        self._refresh_banner()
        if event.get("openPanel"):
            self.set_panel(True)

    def _set_status(self, text):
        self.status.setText(text or "")
        self.status.setVisible(bool(text))
        self._fit_playlist()

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
        pal = _palette(_shown_theme(self.app.store.data["appearance"].get("theme")))
        if not self._configured():
            text, color = tr(5), "#D6B23A"
        elif self._connected:
            self._chat_held = False
            text, color = tr(6), "#3EAD62"
        elif self._chat_held:
            text, color = tr(7), "#D6B23A"
        elif self._failed:
            text, color = tr(8), pal["bad"]
        else:
            text, color = tr(9), "#D6B23A"
        self.banner_text.setText(text)
        if self._connected and self._configured():
            self.banner_text.setStyleSheet("color: {}; font-size: {}pt; background: transparent;".format(
                color, max(1, self.font().pointSize() - 1)
            ))
        else:
            self.banner_text.setStyleSheet("")
        self.banner_dot.setStyleSheet("color: {}; background: transparent;".format(color))
        self.reconnect.setVisible(bool(self._failed and self._configured()))
        self._fit_playlist()

    def _on_users(self, event):
        now = time.monotonic()
        people = []
        ready_names = set()
        for person in event.get("list") or []:
            name = str(person.get("name") or "")
            if not name:
                continue
            ready = bool(person.get("ready"))
            people.append({
                "name": name,
                "ready": ready,
                "file": str(person.get("file") or ""),
                "size": person.get("size"),
                "duration": person.get("duration"),
            })
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
        self._alone_users_received = True
        self._check_alone_on_entry()
        me = str(self.app.store.data["connection"].get("name") or "")
        self._known_names, joined = people_joined(self._known_names, [person["name"] for person in people], me)
        line = join_line(joined)
        if line:
            self._notify_background("yucha", line)
        self._paint_users()
        self._start_when_everyone_ready(people)

    def _check_alone_on_entry(self):
        if not self._alone_users_received:
            return
        if len(self._users) != 1:
            self._alone_until = 0.0
        if self._alone_pending and self._connected and self._users:
            self._alone_pending = False
            if len(self._users) == 1:
                self._alone_until = time.monotonic() + CHAT_LIFE

    def _start_when_everyone_ready(self, people):
        names = {person["name"] for person in people}
        someone_left = bool(self._room_names) and bool(self._room_names - names)
        self._room_names = names
        all_ready = bool(people) and all(person["ready"] for person in people)
        if someone_left:
            self._room_was_ready = all_ready
            return
        if all_ready and not self._room_was_ready and self._connected:
            self._play_for_room()
        self._room_was_ready = all_ready

    def _play_for_room(self):
        loaded = str(self._get("path") or "")
        if not self._current_path and not loaded:
            return
        client = getattr(self.app, "client", None)
        if client is not None:
            from twisted.internet import reactor
            reactor.callFromThread(client.setPaused, False)
        self._set("pause", "no")
        self._paused = False
        self._pos_when = time.monotonic()

    def _nick_colors(self):
        appearance = self.app.store.data["appearance"]
        theme = _shown_theme(appearance.get("theme"))
        mine = _palette(theme, appearance.get("accentColor"))["accent"]
        other = str(appearance.get("accentColor2") or "#1F6A8A")
        if len(other) != 7 or not other.startswith("#"):
            other = "#1F6A8A"
        me = str(self.app.store.data["connection"].get("name") or "")
        return me, mine, other

    def _paint_users(self):
        if not hasattr(self, "room_users"):
            return
        me, mine, other = self._nick_colors()
        appearance = self.app.store.data["appearance"]
        theme = _shown_theme(appearance.get("theme"))
        pal = _palette(theme, appearance.get("accentColor"))
        pal.update(self._face_paint(theme))
        self.room_users.set_people(self._users, me, mine, other, pal["border"])
        self._fit_playlist()
        me = str(self.app.store.data["connection"].get("name") or "")
        mine = next((person for person in self._users if person["name"] == me), None)
        if mine is not None and hasattr(self, "ready"):
            self.ready.blockSignals(True)
            self.ready.setChecked(bool(mine["ready"]))
            self.ready.blockSignals(False)
        self._place_edge_scrolls()

    def _paint_chat(self):
        if not hasattr(self, "chat"):
            return
        me, mine, other = self._nick_colors()
        bad = _palette(_shown_theme(self.app.store.data["appearance"].get("theme")))["bad"]
        self.chat.clear()
        for spans in self._chat_lines:
            self.chat.append(_spans_html(spans, me, mine, other, bad))

    def _append_chat_line(self, spans):
        if not hasattr(self, "chat"):
            return
        me, mine, other = self._nick_colors()
        bad = _palette(_shown_theme(self.app.store.data["appearance"].get("theme")))["bad"]
        self.chat.append(_spans_html(spans, me, mine, other, bad))

    def _add_chat(self, user, text):
        if not text or _hidden_line(text):
            return
        alone = not user and text.strip().rstrip(".!").casefold() in ("you're alone in the room", "you are alone in the room")
        if user:
            spans = [{"k": "nick", "v": user}, {"k": "text", "v": ": " + text}]
        elif re.match(r"^.+ has left\s*$", text):
            spans = [{"k": "leave", "v": text}]
        elif alone:
            self._check_alone_on_entry()
            spans = [{"k": "text", "v": tr(110)}]
        else:
            spans = _status_spans(text) or [{"k": "text", "v": text}]
            if any(span["k"] == "nick" and span["v"] in ("", "None") for span in spans):
                return
        self._chat_lines.append(spans)
        if len(self._chat_lines) > CHAT_CAP:
            del self._chat_lines[:-CHAT_CAP]
            self._paint_chat()
        else:
            self._append_chat_line(spans)
        if alone:
            self._refresh_osd()
        elif not _startup_line(text) and (user or not _PLAYING_LINE.fullmatch(" ".join(text.split()))):
            now = time.monotonic()
            if not replace_seek_toast(self._osd, spans, now, SLIDE):
                self._osd.append({"born": now, "fresh": now, "spans": spans, "leave": None})
            self._refresh_osd()
        me = str(self.app.store.data["connection"].get("name") or "")
        if user and user != me:
            self._notify_background(user, text)

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
        self._sync_chapters()
        try:
            position = float(position or 0)
        except (TypeError, ValueError):
            position = 0
        if not self.slider.isSliderDown():
            self._pos_at = position
            self._pos_when = time.monotonic()
        self.total.setText(_clock(self._duration))

        eof = self._get("eof-reached")
        ended = eof in (True, "yes", "true", 1) and self._duration > 0
        if ended:
            if not self._eof_seen:
                self._eof_seen = True
                self._advance()
        else:
            self._eof_seen = False
        if self._arm_play and self._duration > 0:
            current = self._get("path") or ""
            same = current == self._arm_play or Path(str(current)).name == Path(self._arm_play).name
            if same and current:
                self._set("pause", "no")
                self._paused = False
                self._arm_play = None
        elif self._hold_pause and self._duration > 0:
            current = self._get("path") or ""
            same = current == self._hold_pause or Path(str(current)).name == Path(self._hold_pause).name
            if same and current:
                self._set("pause", "yes")
                self._paused = True
                self._hold_pause = None
        self._move_knob()
        loaded = bool(self._current_path) or bool(self._get("path"))
        self._awake.set_playing(loaded and not self._paused and not ended)
        self._apply_bar_buttons()

    def _sync_chapters(self):
        raw = self._get("chapter-list") if self.ctl is not None else None
        times = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                try:
                    times.append(float(item.get("time")))
                except (TypeError, ValueError):
                    continue
        key = (round(self._duration, 3), tuple(round(mark, 3) for mark in times))
        if key == getattr(self, "_chapter_key", None):
            return
        self._chapter_key = key
        self.slider.set_chapters(times, self._duration)

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
        if self.ctl is not None and not getattr(self, "_osd_cleared", False):
            try:
                self.ctl.command("osd-overlay", 1, "none", "", 1, 1, 0)
            except Exception:
                pass
            self._osd_cleared = True
        now = time.monotonic()
        kept = []
        for item in self._osd:
            if not isinstance(item, dict):
                item = {"born": item[0], "spans": item[1], "leave": item[2] if len(item) > 2 else None}
            stamp = item.get("fresh", item["born"])
            if item.get("leave") is None and now - stamp >= CHAT_LIFE:
                item["leave"] = now
            if item.get("leave") is not None and now - item["leave"] >= SLIDE:
                continue
            kept.append(item)
        self._osd = kept
        appearance = self.app.store.data["appearance"]
        theme = _shown_theme(appearance.get("theme"))
        point = int(appearance.get("chatFontSize") or 17)
        osd = (getattr(self, "_dev", None) or {}).get("osd")
        if osd:
            self.board.force = osd
            point = int(osd.get("size") or point)
        else:
            self.board.force = None
        point = max(1, min(96, point))
        self.board.bar_h = self._bar_height() + (FLOAT_GAP if self._is_modern() else 0)
        page = _palette(theme, appearance.get("accentColor"))
        page["border"] = self._face_paint(theme).get("border", page["border"])
        self.board.repeat = self._repeat
        ink = _dev_ink(osd, theme) if osd else ""
        if ink:
            page = dict(page)
            page["fg"] = ink
        other = str(appearance.get("accentColor2") or "#1F6A8A")
        if len(other) != 7 or not other.startswith("#"):
            other = "#1F6A8A"
        me = str(self.app.store.data["connection"].get("name") or "")
        people = []
        for person in self._users:
            if person["ready"] and now >= self._ready_until.get(person["name"], 0):
                continue
            people.append(person)
        differ, missing = room_file_notes(self._users)
        notices = []
        if self._connected and now < self._alone_until:
            notices.append(tr(110))
        if differ:
            notices.append(tr(11))
        notices.extend(trf(58, name) for name in missing)
        self.board.show_state(point, page, me, page["accent"], other, notices, people, self._osd)

    def accept_files(self, paths, token=""):
        self._add_dropped(list(paths))
        if token:
            os.environ["XDG_ACTIVATION_TOKEN"] = token
        self.show()
        self.raise_()
        self.activateWindow()
        if token:
            os.environ.pop("XDG_ACTIVATION_TOKEN", None)

    def _notify_background(self, summary, body):
        if self.isActiveWindow():
            return
        self._notes.show(summary, body)

    def closeEvent(self, event):
        self._ui_timer.stop()
        self._knob_timer.stop()
        self._awake.close()
        self.video.shutdown()
        event.accept()
        QApplication.instance().quit()
