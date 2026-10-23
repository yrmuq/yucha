# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""mpv's engine inside the yucha window. It does not open a window of its own.
Frames are drawn into this widget the same way mpv's own OpenGL example draws
them: into the widget's framebuffer."""

import os
import re
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtGui import QOpenGLFunctions
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QSizePolicy

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
GL_COLOR_BUFFER_BIT = 0x00004000


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


class Picture(QOpenGLWidget):
    """The video area. Right click and Space pause. The wheel changes volume."""

    fullscreenRequested = Signal()
    volumeChanged = Signal(int)
    arrowPressed = Signal(int)
    filesDropped = Signal(list)

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.PartialUpdate)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)
        self.error = None
        self.ctx = None
        self.mpv = None
        self._mpv_mod = None
        self.ipc_path = Path(runtime) / "mpv.sock"
        try:
            if self.ipc_path.exists():
                self.ipc_path.unlink()
        except OSError:
            pass
        self._start_engine()

    def _start_engine(self):
        mpv = _import_mpv()
        self._mpv_mod = mpv
        self.mpv = mpv.MPV(
            vo="libmpv",
            idle="yes",
            force_window="no",
            keep_open="yes",
            keep_open_pause="yes",
            hr_seek="always",
            osc="no",
            config="no",
            input_terminal="no",
            terminal="no",
            hwdec="auto-safe",
            input_ipc_server=str(self.ipc_path),
            term_playing_msg=PLAYING_MSG,
        )
        found = _library_version(self.mpv)
        if found is None or (found[0] == 0 and found[1] < 23):
            raise RuntimeError("yucha needs libmpv 0.23 or newer")
        try:
            self.mpv.audio_client_name = "yucha"
        except Exception:
            pass
        # "script" is only a command-line alias. libmpv does not accept it
        # as an option, and the player quit before the window opened.
        self.mpv.command("load-script", str(SCRIPT))
        for _ in range(50):
            if self.ipc_path.exists():
                return
            time.sleep(0.02)
        raise RuntimeError("mpv did not open its control socket")

    def _addr(self, _ctx, name):
        gl = self.context()
        if gl is None or not name:
            return None
        if not isinstance(name, (bytes, bytearray)):
            name = str(name).encode()
        ptr = gl.getProcAddress(QByteArray(name))
        if not ptr:
            return None
        value = int(ptr)
        return value or None

    def initializeGL(self):
        mpv = self._mpv_mod
        self._proc_cb = mpv.MpvGlGetProcAddressFn(self._addr)
        try:
            self.ctx = mpv.MpvRenderContext(
                self.mpv,
                "opengl",
                opengl_init_params={"get_proc_address": self._proc_cb},
            )
        except Exception as exc:
            self.error = trf("The picture could not start: {}", exc)
            self.ctx = None
            return
        self.ctx.update_cb = self.update

    def paintGL(self):
        gl = QOpenGLFunctions()
        gl.initializeOpenGLFunctions()
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT)
        if self.ctx is None:
            return
        ratio = self.devicePixelRatioF()
        width = max(1, int(round(self.width() * ratio)))
        height = max(1, int(round(self.height() * ratio)))
        try:
            self.ctx.render(
                flip_y=True,
                opengl_fbo={
                    "fbo": int(self.defaultFramebufferObject()),
                    "w": width,
                    "h": height,
                    "internal_format": 0,
                },
            )
            self.ctx.report_swap()
        except Exception as exc:
            self.error = trf("The picture stopped: {}", exc)
            self.ctx = None

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
        ctx, self.ctx = self.ctx, None
        player, self.mpv = self.mpv, None
        if ctx is not None:
            try:
                ctx.free()
            except Exception:
                pass
        if player is not None:
            try:
                player.terminate()
            except Exception:
                pass
