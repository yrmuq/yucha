# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""The yucha window. Fields and buttons are real widgets. mpv only draws
the picture into the video area."""

import html
import re
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontInfo,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
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
VOLUME_MAX = 130


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
    QLabel#heading {{
        font-weight: 700;
        background: transparent;
    }}
    QWidget#bar, QWidget#chatline {{ border-top: 1px solid {border}; }}
    QWidget#panel {{ border-left: 1px solid {border}; }}
    QWidget#banner {{
        background: {field};
        border: 1px solid {border};
        border-radius: 8px;
    }}
    QWidget#banner QLabel {{ background: transparent; }}
    QPushButton#icon, QPushButton#baricon {{
        padding: 0px;
        min-width: 40px;
        max-width: 40px;
        min-height: 36px;
        max-height: 36px;
    }}
    QPushButton#baricon, QPushButton#baricon:hover, QPushButton#baricon:pressed, QPushButton#baricon:checked {{
        background: transparent;
        border: none;
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
    QTabWidget::pane {{
        border: 1px solid {border};
        background: {bg};
    }}
    QTabBar::tab {{
        background: {field};
        color: {fg};
        padding: 8px 16px;
        border: 1px solid {border};
    }}
    QTabBar::tab:selected {{
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
    QWidget#panel QScrollBar#edgescroll:vertical {{
        background: transparent;
        width: 3px;
        margin: 0px;
    }}
    QWidget#panel QScrollBar#edgescroll:horizontal {{
        background: transparent;
        height: 3px;
        margin: 0px;
    }}
    QWidget#panel QScrollBar#edgescroll::handle:vertical {{
        background: {muted};
        min-height: 18px;
        border-radius: 1px;
    }}
    QWidget#panel QScrollBar#edgescroll::handle:horizontal {{
        background: {muted};
        min-width: 18px;
        border-radius: 1px;
    }}
    QWidget#panel QScrollBar#edgescroll::add-line:vertical, QWidget#panel QScrollBar#edgescroll::sub-line:vertical,
    QWidget#panel QScrollBar#edgescroll::add-line:horizontal, QWidget#panel QScrollBar#edgescroll::sub-line:horizontal {{
        height: 0px;
        width: 0px;
        background: none;
    }}
    QWidget#panel QScrollBar#edgescroll::add-page:vertical, QWidget#panel QScrollBar#edgescroll::sub-page:vertical,
    QWidget#panel QScrollBar#edgescroll::add-page:horizontal, QWidget#panel QScrollBar#edgescroll::sub-page:horizontal {{
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
            ("text", " || " + m.group(2)),
        )),
        (r"^(.+?) unpaused$", lambda m: (
            ("nick", m.group(1)),
            ("text", " ▶"),
        )),
        (r"^(.+?) jumped from (" + _TIME + r") to (" + _TIME + r")$", lambda m: (
            ("nick", m.group(1)),
            ("text", " " + m.group(2) + " → " + m.group(3)),
        )),
        (r"^Rewinded due to time difference with (.+)$", lambda m: (
            ("text", "◀◀ "),
            ("nick", m.group(1)),
        )),
        (r"^Fast-forwarded due to time difference with (.+)$", lambda m: (
            ("text", "▶▶ "),
            ("nick", m.group(1)),
        )),
        (r"^Slowing down due to time difference with (.+)$", lambda m: (
            ("text", "↓ "),
            ("nick", m.group(1)),
        )),
        (r"^Reverting speed back to normal$", lambda m: (
            ("text", "1×"),
        )),
        (r"^(.+?) is playing '(.+?)' \([^)]*\)(?: in room: '.*')?$", lambda m: (
            ("nick", m.group(1)),
            ("text", " ▶ " + m.group(2)),
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
        else:
            bits.append(safe)
    return "".join(bits)


def _wrap_spans(spans, metrics, width):
    words = []
    for span in spans:
        for part in re.split(r"(\s+)", span["v"]):
            if part:
                words.append({"k": span["k"], "v": part})
    lines = []
    current = []
    used = 0
    for word in words:
        wide = metrics.horizontalAdvance(word["v"])
        if current and used + wide > width and word["v"].strip():
            lines.append(current)
            current = []
            used = 0
        current.append(word)
        used += wide
    if current:
        lines.append(current)
    return lines or [[{"k": "text", "v": ""}]]


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
    """The episode list. A left click plays a row. A right click removes it."""

    removed = Signal(str)
    chosen = Signal(str)

    def __init__(self):
        super().__init__()
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setItemDelegate(FileDelegate(self))

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        path = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        if item is not None and event.button() == Qt.MouseButton.RightButton:
            self.removed.emit(path or "")
            event.accept()
            return
        if item is not None and event.button() == Qt.MouseButton.LeftButton and path:
            self.chosen.emit(path)
            event.accept()
            return
        super().mousePressEvent(event)


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
        self.files_scroll.viewport().setAutoFillBackground(False)
        self.files_scroll.setWidget(self.files_host)
        self.files_scroll.viewport().installEventFilter(self)
        self.names.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.names.installEventFilter(self)
        self.sizes = QWidget()
        self.sizes_col = QVBoxLayout(self.sizes)
        self.sizes_col.setContentsMargins(0, 0, 0, 0)
        self.sizes_col.setSpacing(0)
        self.sizes.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row.addWidget(self.names, 4)
        row.addWidget(self.files_scroll, 11)
        row.addWidget(self.sizes, 0)
        self._row_h = 0
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
        faded = QColor(line)
        faded.setAlpha(56)
        self._line = faded
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
        self.sizes.setMinimumWidth(metrics.horizontalAdvance("0000 MB") + 8)
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
        left = self.names.geometry().right()
        right = self.files_scroll.geometry().left()
        file_right = self.files_scroll.geometry().right()
        size_left = self.sizes.geometry().left()
        self._lines.rows = len(self._full_names)
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
            label.setText(metrics.elidedText(full, Qt.TextElideMode.ElideRight, width))

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


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
        self._accent = QColor("#9A3A52")
        self.setObjectName("icon")
        self.setFixedSize(40, 36)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_kind(self, kind):
        if self.kind != kind:
            self.kind = kind
            self.update()

    def set_ink(self, ink, ink_on, accent):
        self._ink = QColor(ink)
        self._ink_on = QColor(ink_on)
        self._accent = QColor(accent)
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
        elif kind == "ready":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#3EAD62" if self.isChecked() else "#C4453C"))
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
    def __init__(self, appearance, connection, parent, page=1):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.appearance = None
        self.connection = None
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        room = QWidget()
        room_form = QFormLayout(room)
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
            room_form.addRow(label, field)
            field.returnPressed.connect(self._accept)
        tabs.addTab(room, "Room")

        theme_page = QWidget()
        theme_form = QFormLayout(theme_page)
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        current = appearance.get("theme") or "dark"
        self.theme.setCurrentIndex(0 if current != "light" else 1)
        self.color = QLineEdit(str(appearance.get("chatColor") or "#F4F1EA"))
        self.accent = QLineEdit(str(appearance.get("accentColor") or "#9A3A52"))
        self.accent2 = QLineEdit(str(appearance.get("accentColor2") or "#1F6A8A"))
        self.chat_size = QSpinBox()
        self.chat_size.setRange(12, 48)
        self.chat_size.setValue(int(appearance.get("chatFontSize") or 18))
        self.ui_size = QSpinBox()
        self.ui_size.setRange(1, 32)
        self.ui_size.setValue(int(appearance.get("uiFontSize") or 16))
        theme_form.addRow("Theme", self.theme)
        theme_form.addRow("Chat color", self.color)
        theme_form.addRow("Accent color", self.accent)
        theme_form.addRow("Second accent", self.accent2)
        theme_form.addRow("Chat size", self.chat_size)
        theme_form.addRow("Interface size", self.ui_size)
        tabs.addTab(theme_page, "Theme")

        other = QWidget()
        other_form = QFormLayout(other)
        self.autoplay = QCheckBox("Play the next episode automatically")
        self.autoplay.setChecked(bool(appearance.get("autoplayNext")))
        other_form.addRow(self.autoplay)
        tabs.addTab(other, "Other")

        about = QWidget()
        about_layout = QVBoxLayout(about)
        title = QLabel("yucha")
        title.setObjectName("heading")
        from yucha import __version__
        version = QLabel("{} beta".format(__version__))
        heart = appearance.get("accentColor") or "#9A3A52"
        thanks = QLabel(
            'Thanks <span style="color: {};">♥</span> '
            '<a href="https://syncplay.pl">Syncplay</a> and '
            '<a href="https://mpv.io">mpv</a>'.format(heart)
        )
        thanks.setTextFormat(Qt.TextFormat.RichText)
        thanks.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        thanks.setOpenExternalLinks(True)
        about_layout.addWidget(title)
        about_layout.addWidget(version)
        about_layout.addStretch(1)
        about_layout.addWidget(thanks)
        about_layout.addStretch(2)
        tabs.addTab(about, "About")

        buttons = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

        wide = 0
        tall = 0
        for index in range(tabs.count()):
            hint = tabs.widget(index).sizeHint()
            wide = max(wide, hint.width())
            tall = max(tall, hint.height())
        for index in range(tabs.count()):
            tabs.widget(index).setMinimumSize(max(360, wide), tall)
        tabs.setCurrentIndex(page if 0 <= page < tabs.count() else 0)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

    def _accept(self):
        color = self.color.text().strip()
        if len(color) != 7 or not color.startswith("#"):
            color = "#F4F1EA"
        accent = self.accent.text().strip()
        if len(accent) != 7 or not accent.startswith("#"):
            accent = "#9A3A52"
        accent2 = self.accent2.text().strip()
        if len(accent2) != 7 or not accent2.startswith("#"):
            accent2 = "#1F6A8A"
        self.appearance = {
            "theme": self.theme.currentData(),
            "chatColor": color,
            "accentColor": accent,
            "accentColor2": accent2,
            "chatFontSize": self.chat_size.value(),
            "uiFontSize": self.ui_size.value(),
            "autoplayNext": self.autoplay.isChecked(),
        }
        self.connection = {
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
        self._chat_lines = []
        self._arm_play = None
        self._ready_until = {}
        self._pos_at = 0.0
        self._pos_when = time.monotonic()
        self._speed = 1.0
        self._paused = True
        self._playlist = []
        self._current_path = ""
        self._eof_seen = False
        self._volume_until = 0
        self._hold_pause = None
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
        self.video.arrowPressed.connect(self._on_arrow)
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
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.setRange(0, SEEK_STEPS)
        self.total = QLabel("0:00")
        self.ready = IconButton("ready")
        self.ready.setCheckable(True)
        self.chat_btn = IconButton("chat")
        self.chat_btn.setCheckable(True)
        self.room = IconButton("room")
        self.room.setCheckable(True)
        self.play.clicked.connect(self._toggle_pause)
        self.slider.sliderReleased.connect(self._seek_released)
        self.ready.clicked.connect(self._toggle_ready)
        self.chat_btn.clicked.connect(self._toggle_chat_field)
        self.room.clicked.connect(self._toggle_room)
        for widget in (self.play, self.elapsed, self.slider, self.total, self.ready, self.chat_btn, self.room):
            bar.addWidget(widget)
        for button in (self.play, self.ready, self.chat_btn, self.room):
            button.setObjectName("baricon")
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
        self.volume.setObjectName("volumebar")
        self.volume.setRange(0, VOLUME_MAX)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume_text = QLabel("0")
        self.volume_text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_text)
        self._lock_volume_digits()

        row.addWidget(column, 1)

        self.panel = QWidget(column)
        self.panel.setObjectName("panel")
        self._overlay(self.panel)
        side = QVBoxLayout(self.panel)
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
        self.banner_text = QLabel("Not configured")
        self.banner_dot = QLabel("●")
        self.banner_text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.banner_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        inside.addWidget(self.banner_text)
        inside.addStretch(1)
        inside.addWidget(self.banner_dot)
        self.gear = IconButton("gear")
        self.gear.clicked.connect(lambda: self._open_settings(1))
        banner_row.addWidget(self.banner, 1)
        banner_row.addWidget(self.gear)
        side.addLayout(banner_row)

        self.reconnect = QPushButton("Reconnect")
        self.reconnect.clicked.connect(self._reconnect)
        self.reconnect.hide()
        side.addWidget(self.reconnect)

        users_title = QLabel("Users")
        users_title.setObjectName("heading")
        side.addWidget(users_title)
        self.room_users = UserTable()
        side.addWidget(self.room_users)

        playlist_title = QLabel("Playlist")
        playlist_title.setObjectName("heading")
        side.addWidget(playlist_title)
        self.files = FileList()
        self.files.setObjectName("playlist")
        self.files.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files.removed.connect(self._remove_file)
        self.files.chosen.connect(lambda path: self._play_path(path, start=True))
        side.addWidget(self.files)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.hide()
        side.addWidget(self.status)

        chat_title = QLabel("Chat")
        chat_title.setObjectName("heading")
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
        self.files.viewport().installEventFilter(self)
        self.chat.viewport().installEventFilter(self)
        self.stage.installEventFilter(self)
        self._place_overlays()

    def _overlay(self, widget):
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
        widget.setAutoFillBackground(True)

    def eventFilter(self, watched, event):
        if watched is self.stage and event.type() == QEvent.Type.Resize:
            self._place_overlays()
        elif event.type() == QEvent.Type.Wheel:
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
        self._place_edge_scrolls()
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
        font.setPointSize(max(1, min(32, size)))
        QApplication.instance().setFont(font)
        info = QFontInfo(self.chat.document().defaultFont())
        point = info.pointSize()
        if point < 1:
            point = font.pointSize()
        shared = QFont(font)
        shared.setFamily(info.family() or font.family())
        shared.setPointSize(point)
        self.chat.setFont(shared)
        self.chat.document().setDefaultFont(shared)
        text_css = "{}pt".format(point)
        self.room_users._text_css = text_css
        self.files.setFont(shared)
        self.room_users.setFont(shared)
        self._lock_volume_digits()
        self.setStyleSheet(
            self.styleSheet()
            + """
            QTextEdit#roomchat, QListWidget#playlist, QListWidget#playlist::item,
            QWidget#usersbox QLabel {{
                font-size: {size};
            }}
            """.format(size=text_css)
        )
        pal = _palette(theme, appearance.get("accentColor"))
        for button in (self.play, self.ready, self.chat_btn, self.room, self.gear, self.bar_send):
            button.set_ink(pal["button_fg"], pal["on_fg"], pal["accent"])
        self._refresh_banner()
        self._refresh_files()
        self._paint_chat()
        self._paint_users()

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

    def _lock_volume_digits(self):
        if not hasattr(self, "volume_text"):
            return
        width = QFontMetrics(self.volume_text.font()).horizontalAdvance("000") + 8
        self.volume_text.setFixedWidth(width)

    def _show_volume(self, level):
        ceiling = self._volume_ceiling()
        level = max(0, min(ceiling, int(level)))
        if self.volume.maximum() != ceiling:
            self.volume.setRange(0, ceiling)
        self.volume.setValue(level)
        self.volume_text.setText(str(level))
        self._volume_until = time.monotonic() + VOLUME_LIFE
        self.volume_box.show()
        self.volume_box.raise_()

    def _volume_ceiling(self):
        raw = self._get("volume-max")
        try:
            return max(101, int(round(float(raw))))
        except (TypeError, ValueError):
            return VOLUME_MAX

    def _typing(self):
        return isinstance(QApplication.focusWidget(), (QLineEdit, QTextEdit, QSpinBox))

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
            self._cmd("seek", "0", "absolute")
            self._set("pause", "no")
            self._paused = False
            self._pos_at = 0
            self._pos_when = time.monotonic()
            self._eof_seen = True
            return
        self._cmd("cycle", "pause")

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
        staying = bool(self._playlist) and self._current_path == self._playlist[0]["path"]
        self._playlist.extend(batch)
        if not batch:
            self._refresh_files()
            return
        if fresh:
            self._current_path = batch[0]["path"]
            self._paused = True
            self._refresh_files()
            return
        if staying:
            self._refresh_files()
            return
        self._play_path(batch[0]["path"], start=True)

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

    def _advance(self):
        if len(self._playlist) <= 1:
            return
        index = next((i for i, item in enumerate(self._playlist) if item["path"] == self._current_path), -1)
        if index < 0 or index + 1 >= len(self._playlist):
            return
        auto = bool(self.app.store.data["appearance"].get("autoplayNext"))
        self._play_path(self._playlist[index + 1]["path"], start=auto)

    def _refresh_files(self):
        if not hasattr(self, "files"):
            return
        appearance = self.app.store.data["appearance"]
        pal = _palette(appearance.get("theme"), appearance.get("accentColor"))
        self.files.clear()
        for index, item in enumerate(self._playlist, start=1):
            row = QListWidgetItem("{}. {}".format(index, item["name"]))
            row.setData(Qt.ItemDataRole.UserRole, item["path"])
            if item["path"] == self._current_path:
                row.setBackground(QColor(pal["accent"]))
                row.setForeground(QColor(pal["on_fg"]))
            self.files.addItem(row)
        row_h = max(24, QFontMetrics(self.files.font()).height() + 12)
        rows = max(2, self.files.count())
        self.files.setFixedHeight(rows * row_h + 2 * self.files.frameWidth())
        self._place_edge_scrolls()

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

    def _open_settings(self, page=1):
        dialog = SettingsDialog(
            self.app.store.data["appearance"],
            self.app.store.data["connection"],
            self,
            page,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.appearance:
            return
        self.app.on_command({"c": "appearance", **dialog.appearance})
        self.apply_theme()
        if dialog.connection and self._connection_changed(dialog.connection):
            self.app.on_command({"c": "connect", **dialog.connection})
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
        if state == "failed":
            self._set_status(event.get("text") or "")
        if state == "connected":
            self._set_status("")
        self._refresh_banner()
        if event.get("openPanel"):
            self.set_panel(True)

    def _set_status(self, text):
        self.status.setText(text or "")
        self.status.setVisible(bool(text))

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
            people.append({
                "name": name,
                "ready": ready,
                "file": str(person.get("file") or ""),
                "size": person.get("size"),
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
        self._paint_users()

    def _nick_colors(self):
        appearance = self.app.store.data["appearance"]
        theme = appearance.get("theme") or "dark"
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
        border = _palette(appearance.get("theme"), appearance.get("accentColor"))["border"]
        self.room_users.set_people(self._users, me, mine, other, border)
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
        bad = _palette(self.app.store.data["appearance"].get("theme"))["bad"]
        self.chat.clear()
        for spans in self._chat_lines:
            self.chat.append(_spans_html(spans, me, mine, other, bad))

    def _add_chat(self, user, text):
        if not text or _hidden_line(text):
            return
        if user:
            spans = [{"k": "nick", "v": user}, {"k": "text", "v": ": " + text}]
        elif re.match(r"^.+ has left\s*$", text):
            spans = [{"k": "leave", "v": text}]
        else:
            spans = _status_spans(text) or [{"k": "text", "v": text}]
            if any(span["k"] == "nick" and span["v"] in ("", "None") for span in spans):
                return
        self._chat_lines.append(spans)
        if not _startup_line(text):
            self._osd.append((time.monotonic(), spans))
        self._paint_chat()

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
        page = _palette(theme, appearance.get("accentColor"))
        color = _bgr(page["fg"])
        accent = _bgr(page["accent"])
        other = str(appearance.get("accentColor2") or "#1F6A8A")
        if len(other) != 7 or not other.startswith("#"):
            other = "#1F6A8A"
        accent2 = _bgr(other)
        me = str(self.app.store.data["connection"].get("name") or "")
        width = max(1, self.video.width())
        height = max(1, self.video.height())
        people = []
        for person in self._users:
            name = person["name"]
            ready = person["ready"]
            if ready and now >= self._ready_until.get(name, 0):
                continue
            people.append(person)
        lines = []
        row_h = metrics.height()
        y = 16
        pad = 8
        if people:
            widest = max(metrics.horizontalAdvance(person["name"]) for person in people)
            circle_w = max(metrics.height() + 8, 28)
            name_w = widest + 16
            ready_w = min(max(96, width - 16), name_w + circle_w + pad * 2)
            inner = ready_w - pad * 2
            name_col = max(24, inner - circle_w)
            ready_h = pad * 2 + len(people) * row_h
            ready_x = max(8, width - 8 - ready_w)
            lines.append(
                "{{\\an7\\pos({},{})\\bord0\\shad0\\1c&H{}&\\p1}}{}".format(
                    ready_x, y, _bgr(page["bg"]), _round_box(ready_w, ready_h, 8)
                )
            )
            text_y = y + pad
            for person in people:
                dot = "00FF00" if person["ready"] else "0000FF"
                ink = accent if person["name"] == me else accent2
                shown = metrics.elidedText(person["name"], Qt.TextElideMode.ElideRight, max(8, name_col - 4))
                mid_y = int(text_y + row_h / 2)
                lines.append(
                    "{{\\an5\\pos({},{})\\bord0\\shad0\\fs{}\\1c&H{}&}}{}".format(
                        int(ready_x + pad + name_col / 2), mid_y, size, ink, _ass_escape(shown)
                    )
                )
                lines.append(
                    "{{\\an5\\pos({},{})\\bord0\\shad0\\fs{}\\1c&H{}&}}●".format(
                        int(ready_x + pad + name_col + (inner - name_col) / 2), mid_y, size, dot
                    )
                )
                text_y += row_h
            y += ready_h + 8
        floor = max(24, height - BAR_HEIGHT - 8)
        box_w = min(CHAT_BOX, max(160, width - 24))
        x = max(8, width - 8 - box_w)
        inner = max(40, box_w - pad * 2)
        for _born, spans in self._osd:
            wrapped = _wrap_spans(spans, metrics, inner)
            block_h = pad * 2 + max(1, len(wrapped)) * row_h
            if y + block_h > floor:
                break
            lines.append(
                "{{\\an7\\pos({},{})\\bord0\\shad0\\1c&H{}&\\p1}}{}".format(
                    x, y, _bgr(page["bg"]), _round_box(box_w, block_h, 8)
                )
            )
            body = []
            for line in wrapped:
                bits = []
                for span in line:
                    if span["k"] == "nick":
                        ink = accent if span["v"] == me else accent2
                    else:
                        ink = color
                    bits.append("{{\\1c&H{}&}}{}".format(ink, _ass_escape(span["v"])))
                body.append("".join(bits))
            lines.append(
                "{{\\an4\\pos({},{})\\p0\\bord0\\shad0\\q2\\fs{}\\1c&H{}&}}{}".format(
                    x + pad, int(y + block_h / 2), size, color, "\\N".join(body)
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
