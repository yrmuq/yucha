# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wire the saved config, the mpv window, and the Syncplay client."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "syncplay"))

from twisted.internet import reactor

from yucha.bridge import Bridge
from yucha.configstore import ConfigStore, bounded_int, font_name, hex_color, port_number, runtime_dir
from yucha.i18n import languages, tr, use
from yucha.player_ui import PlayerUI
from yucha.session import launch_player, make_client, submit_login


class App(object):
    def __init__(self):
        self.store = ConfigStore()
        use(self.store.data["appearance"].get("language"))
        self.runtime = runtime_dir()
        self.bridge = Bridge(self.runtime)
        self.ui = PlayerUI(self.bridge)
        self.client = make_client(self.ui, self.store)
        self.ui.addClient(self.client)

    def boot(self):
        if self.store.has_connection():
            reactor.callWhenRunning(lambda: self._connect_saved())

    def _connect_saved(self):
        conn = self.store.data["connection"]
        self._connect(
            str(conn.get("host") or ""),
            conn.get("port") or 8999,
            str(conn.get("name") or ""),
            str(conn.get("room") or ""),
            str(conn.get("password") or ""),
        )

    def _connect(self, host, port, name, room, password):
        host = host.strip()
        name = name.strip()
        room = room.strip()
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 0
        if not host or not name or not room or not (1 <= port <= 65535):
            self.bridge.emit({
                "e": "conn",
                "state": "failed",
                "text": tr(46),
                "openPanel": True,
            })
            return
        self.bridge.emit({"e": "conn", "state": "connecting", "text": tr(9)})
        submit_login(self.client, host, port, name, room, password)

    def on_command(self, command):
        kind = command.get("c")
        if kind == "connect":
            host = str(command.get("host") or "").strip()
            name = str(command.get("name") or "").strip()
            room = str(command.get("room") or "").strip()
            password = str(command.get("password") or "")
            raw_port = command.get("port")
            if raw_port is None or str(raw_port).strip() == "":
                port = 8999
            else:
                port = port_number(raw_port)
            if port is None or not host or not name or not room:
                self.bridge.emit({
                    "e": "conn",
                    "state": "failed",
                    "text": tr(46),
                    "openPanel": True,
                })
                return
            self.store.data["connection"].update({
                "host": host,
                "port": port,
                "name": name,
                "password": password,
                "room": room,
            })
            self.store.save()
            reactor.callFromThread(self._connect, host, port, name, room, password)
        elif kind == "chat":
            text = str(command.get("text") or "").strip()
            if text and self.client._running:
                reactor.callFromThread(self.client.sendChat, text)
        elif kind == "appearance":
            appearance = self.store.data["appearance"]
            theme = command.get("theme")
            if theme in ("dark", "light", "auto"):
                appearance["theme"] = theme
            color = hex_color(command.get("chatColor"), appearance.get("chatColor") or "#F4F1EA")
            appearance["chatColor"] = color
            accent = hex_color(command.get("accentColor"), appearance.get("accentColor") or "#9A3A52")
            appearance["accentColor"] = accent
            second = hex_color(command.get("accentColor2"), appearance.get("accentColor2") or "#1F6A8A")
            appearance["accentColor2"] = second
            try:
                size = int(command.get("chatFontSize"))
            except (TypeError, ValueError):
                size = appearance.get("chatFontSize") or 18
            appearance["chatFontSize"] = max(1, min(48, size))
            appearance["checkUpdates"] = bool(command.get("checkUpdates", appearance.get("checkUpdates", True)))
            if command.get("uiFontSize") is not None:
                try:
                    ui = int(command.get("uiFontSize"))
                except (TypeError, ValueError):
                    ui = appearance.get("uiFontSize") or 16
                appearance["uiFontSize"] = max(1, min(32, ui))
            appearance["autoplayNext"] = bool(command.get("autoplayNext"))
            appearance["fastforwardOnDesync"] = bool(command.get("fastforwardOnDesync", True))
            appearance["slowOnDesync"] = bool(command.get("slowOnDesync", True))
            try:
                ceiling = int(command.get("volumeMax", 100))
            except (TypeError, ValueError):
                ceiling = 100
            appearance["volumeMax"] = max(100, min(130, ceiling))
            overlay = command.get("volumeOverlay") or "horizontal"
            appearance["volumeOverlay"] = "vertical" if overlay == "vertical" else "horizontal"
            language = command.get("language", appearance.get("language") or "English")
            language = str(language or "English")
            if language not in languages():
                language = "English"
            appearance["language"] = language
            appearance["subFont"] = font_name(command.get("subFont", appearance.get("subFont")))
            appearance["subFontSize"] = bounded_int(command.get("subFontSize"), 55, 8, 120)
            appearance["subColor"] = hex_color(command.get("subColor"), "#FFFFFF")
            style = command.get("style") or appearance.get("style") or "classic"
            appearance["style"] = "modern" if style == "modern" else "classic"
            use(language)
            self.client._config["pauseOnLeave"] = True
            self.client._config["fastforwardOnDesync"] = appearance["fastforwardOnDesync"]
            self.client._config["slowOnDesync"] = appearance["slowOnDesync"]
            self.store.save()

def main():
    from pathlib import Path

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    # The desktop scale is the only scale. Fontconfig's own DPI was a second
    # one, so the same point size grew again on a 2K screen.
    os.environ["QT_FONT_DPI"] = "96"
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from yucha.configstore import runtime_dir
    from yucha.system import FileBridge, handoff, media_paths
    from yucha.window import MainWindow

    paths = media_paths(sys.argv[1:])
    sock = runtime_dir() / "open.sock"
    if paths and handoff(paths, sock, os.environ.get("XDG_ACTIVATION_TOKEN") or ""):
        return

    qt = QApplication([])
    qt.setApplicationName("yucha")
    qt.setDesktopFileName("yucha")
    icon = Path(__file__).resolve().parent / "icon.png"
    if icon.is_file():
        qt.setWindowIcon(QIcon(str(icon)))
    # Twisted only finishes name lookup after its startup. iterate() alone
    # never runs that, so a room connect would stay on "Connecting...".
    reactor.startRunning(installSignalHandlers=False)
    app = App()
    window = MainWindow(app)
    window.show()
    bridge = FileBridge(sock)
    bridge.opened.connect(window.accept_files)
    bridge.start()
    qt.processEvents()
    player = launch_player(app.client, app.runtime, window.video.ipc_path)
    window.set_player(player)
    if paths:
        window.accept_files(paths, "")
    app.boot()

    def tick():
        try:
            reactor.iterate(0)
        except Exception as exc:
            if not getattr(tick, "reported", False):
                tick.reported = True
                print("yucha: {}".format(exc), file=sys.stderr)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(10)
    qt.aboutToQuit.connect(bridge.stop)
    qt.aboutToQuit.connect(timer.stop)
    qt.exec()
