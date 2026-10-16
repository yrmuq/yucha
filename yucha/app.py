# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wire the saved config, the mpv window, and the Syncplay client."""

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "third_party" / "syncplay"))

from twisted.internet import reactor

from yucha.bridge import Bridge
from yucha.configstore import runtime_dir
from yucha.configstore import ConfigStore
from yucha.player_ui import PlayerUI
from yucha.session import launch_player, make_client, submit_login


class App(object):
    def __init__(self):
        self.store = ConfigStore()
        self.runtime = runtime_dir()
        self.bridge = Bridge(self.runtime)
        self.ui = PlayerUI(self.bridge)
        self.client = make_client(self.ui, self.store)
        self.ui.addClient(self.client)

    def boot(self):
        conn = self.store.data["connection"]
        self.bridge.emit({
            "e": "boot",
            "openPanel": not self.store.has_connection(),
            "form": {
                "host": conn.get("host") or "syncplay.pl",
                "port": str(conn.get("port") or 8999),
                "name": conn.get("name") or "",
                "password": conn.get("password") or "",
                "room": conn.get("room") or "",
            },
            "appearance": self.store.data["appearance"],
        })
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
                "text": "Need a server, a username, a room, and a port.",
                "openPanel": True,
            })
            return
        self.bridge.emit({"e": "conn", "state": "connecting", "text": "Connecting..."})
        submit_login(self.client, host, port, name, room, password)

    def on_command(self, command):
        kind = command.get("c")
        if kind == "connect":
            self.store.data["connection"].update({
                "host": str(command.get("host") or "").strip(),
                "port": int(command.get("port") or 8999),
                "name": str(command.get("name") or "").strip(),
                "password": str(command.get("password") or ""),
                "room": str(command.get("room") or "").strip(),
            })
            self.store.save()
            reactor.callFromThread(
                self._connect,
                self.store.data["connection"]["host"],
                self.store.data["connection"]["port"],
                self.store.data["connection"]["name"],
                self.store.data["connection"]["room"],
                self.store.data["connection"]["password"],
            )
        elif kind == "chat":
            text = str(command.get("text") or "").strip()
            if text and self.client._running:
                reactor.callFromThread(self.client.sendChat, text)
        elif kind == "appearance":
            appearance = self.store.data["appearance"]
            theme = command.get("theme")
            if theme in ("dark", "light"):
                appearance["theme"] = theme
            color = str(command.get("chatColor") or "")
            if len(color) == 7 and color.startswith("#"):
                appearance["chatColor"] = color
            accent = str(command.get("accentColor") or "")
            if len(accent) == 7 and accent.startswith("#"):
                appearance["accentColor"] = accent
            try:
                size = int(command.get("chatFontSize"))
            except (TypeError, ValueError):
                size = appearance.get("chatFontSize") or 18
            appearance["chatFontSize"] = max(12, min(48, size))
            if command.get("uiFontSize") is not None:
                try:
                    ui = int(command.get("uiFontSize"))
                except (TypeError, ValueError):
                    ui = appearance.get("uiFontSize") or 16
                appearance["uiFontSize"] = max(12, min(32, ui))
            self.store.save()

    def serve_commands(self):
        def loop():
            import time
            while True:
                for command in self.bridge.read_commands():
                    try:
                        self.on_command(command)
                    except Exception as exc:
                        self.bridge.emit({
                            "e": "conn",
                            "state": "failed",
                            "text": str(exc),
                            "openPanel": True,
                        })
                time.sleep(0.05)
        thread = threading.Thread(target=loop, name="yucha-commands", daemon=True)
        thread.start()


def main():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from yucha.window import MainWindow

    qt = QApplication([])
    qt.setApplicationName("yucha")
    # Twisted only finishes name lookup after its startup. iterate() alone
    # never runs that, so a room connect would stay on "Connecting...".
    reactor.startRunning(installSignalHandlers=False)
    app = App()
    window = MainWindow(app)
    window.show()
    qt.processEvents()
    player = launch_player(app.client, app.runtime, window.video.ipc_path)
    window.set_player(player)
    app.boot()
    app.serve_commands()

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
    qt.aboutToQuit.connect(timer.stop)
    qt.exec()
