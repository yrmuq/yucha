# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""mpv draws into its own native window. The interface is other windows, so the
two can refresh at different rates."""

import os
import re
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QWidget

from yucha.i18n import trf

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "third_party" / "syncplay" / "syncplay" / "resources" / "syncplayintf.lua"
# Syncplay reads this line from mpv to learn the filename and duration.
PLAYING_MSG = (
    "<SyncplayUpdateFile>\n"
    "ANS_filename=${filename}\n"
    "ANS_length=${=duration:${=length:0}}\n"
    "ANS_path=${path}\n"
    "</SyncplayUpdateFile>"
)


def _library_version(player):
    raw = None
    try:
        raw = player.mpv_version
    except Exception:
        raw = None
    found = re.search(r"(\d+)\.(\d+)", str(raw or ""))
    if not found:
        return None
    return int(found.group(1)), int(found.group(2))


def _import_mpv():
    import ctypes.util

    forced = os.environ.get("YUCHA_LIBMPV")
    if forced:
        real = ctypes.util.find_library

        def find_library(name):
            if name == "mpv":
                return forced
            return real(name)

        ctypes.util.find_library = find_library
    import mpv
    return mpv


class Picture(QWidget):
    """The video window. Right click and Space pause. The wheel changes volume."""

    fullscreenRequested = Signal()
    volumeChanged = Signal(int)
    arrowPressed = Signal(int)
    filesDropped = Signal(list)
    enterPressed = Signal()

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setUpdatesEnabled(False)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)
        self.error = None
        self.ctx = None
        self.mpv = None
        self._mpv_mod = None
        self._started = False
        self.ipc_path = Path(runtime) / "mpv.sock"
        try:
            if self.ipc_path.exists():
                self.ipc_path.unlink()
        except OSError:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_player()

    def _ensure_player(self):
        if self._started:
            return
        self.winId()
        self._started = True
        self._start_engine()

    def _start_engine(self):
        try:
            mpv = _import_mpv()
        except Exception as exc:
            self.error = trf(47, exc)
            return
        self._mpv_mod = mpv
        try:
            self.mpv = mpv.MPV(
                wid=str(int(self.winId())),
                vo="gpu",
                idle="yes",
                keep_open="yes",
                keep_open_pause="yes",
                hr_seek="always",
                osc="no",
                config="no",
                input_terminal="no",
                terminal="no",
                input_default_bindings="no",
                input_vo_keyboard="no",
                input_cursor="no",
                hwdec="auto-safe",
                input_ipc_server=str(self.ipc_path),
                term_playing_msg=PLAYING_MSG,
            )
        except Exception as exc:
            self.error = trf(47, exc)
            self.mpv = None
            return
        found = _library_version(self.mpv)
        if found is None or (found[0] == 0 and found[1] < 23):
            self.error = "yucha needs libmpv 0.23 or newer"
            return
        try:
            self.mpv.audio_client_name = "yucha"
        except Exception:
            pass
        # "script" is only a command-line alias. libmpv does not accept it
        # as an option, and the player quit before the window opened.
        try:
            self.mpv.command("load-script", str(SCRIPT))
        except Exception as exc:
            self.error = trf(47, exc)
            return
        for _ in range(50):
            if self.ipc_path.exists():
                return
            time.sleep(0.02)
        self.error = "mpv did not open its control socket"

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.RightButton:
            self._pause()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._pause()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.enterPressed.emit()
            event.accept()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.arrowPressed.emit(int(key))
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.fullscreenRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps and self.mpv is not None:
            try:
                self.mpv.command("add", "volume", 2 * steps)
                level = int(round(float(self.mpv.volume)))
            except Exception:
                level = None
            if level is not None:
                self.volumeChanged.emit(level)
        event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = []
        for url in urls:
            path = url.toLocalFile() or url.toString()
            if path:
                paths.append(path)
        if paths:
            self.filesDropped.emit(paths)
        event.acceptProposedAction()

    def _pause(self):
        if self.mpv is None:
            return
        try:
            self.mpv.command("cycle", "pause")
        except Exception:
            pass

    def shutdown(self):
        self.ctx = None
        player, self.mpv = self.mpv, None
        if player is not None:
            try:
                player.terminate()
            except Exception:
                pass
