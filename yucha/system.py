# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop integration that is the same on GNOME and KDE.

Sleep and notifications use the freedesktop session bus both desktops
already provide. A second launch hands its files to the open window.
"""

import json
import os
import socket
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QObject, Signal
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

from yucha.i18n import tr, trf


# Idle keeps the screen from blanking. Suspend keeps the machine awake.
_AWAKE_FLAGS = 4 | 8
_SAVERS = (
    ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver"),
    ("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
    ("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver"),
    ("org.kde.screensaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver"),
)


def media_paths(argv):
    """File arguments from a file manager or the command line."""
    paths = []
    force = False
    for arg in argv:
        if arg == "--":
            force = True
            continue
        if not force and str(arg).startswith("-"):
            continue
        path = _local_path(arg)
        if path:
            paths.append(path)
    return paths


def _local_path(arg):
    text = str(arg or "").strip()
    if text.startswith("file://"):
        return unquote(urlparse(text).path)
    return text


def people_joined(known, names, me):
    """First sight of the room is not a join. Later new names are."""
    current = {str(name) for name in names if name}
    if known is None:
        if not current:
            return None, []
        return current, []
    fresh = sorted(name for name in current - known if name != me)
    return current, fresh


def join_line(names):
    if not names:
        return ""
    if len(names) == 1:
        return trf(50, names[0])
    if len(names) == 2:
        return trf(51, names[0], names[1])
    return trf(52, len(names))


def handoff(paths, socket_path, token="", timeout=1.0):
    """Give paths to a running yucha. False when nothing is listening."""
    paths = [str(path) for path in paths if path]
    if not paths:
        return False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        payload = json.dumps({"paths": paths, "token": token or ""}) + "\n"
        client.sendall(payload.encode("utf-8"))
        ack = b""
        while b"\n" not in ack and len(ack) < 32:
            chunk = client.recv(32)
            if not chunk:
                break
            ack += chunk
    except OSError:
        return False
    finally:
        client.close()
    return ack.startswith(b"ok")


def _read_message(conn):
    data = b""
    while b"\n" not in data and len(data) < 1024 * 1024:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    line = data.split(b"\n", 1)[0]
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeError, ValueError):
        return [], ""
    if not isinstance(message, dict):
        return [], ""
    paths = [str(path) for path in message.get("paths") or [] if path]
    token = str(message.get("token") or "")
    return paths, token


class FileBridge(QObject):
    """Listens for files from a second launch."""

    opened = Signal(list, str)

    def __init__(self, socket_path):
        super().__init__()
        self.path = Path(socket_path)
        self._stop = threading.Event()
        self._thread = None
        self._server = None

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                return False
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.path))
        except OSError:
            server.close()
            return False
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        server.listen(4)
        server.settimeout(0.4)
        self._server = server
        self._thread = threading.Thread(target=self._loop, name="yucha-open", daemon=True)
        self._thread.start()
        return True

    def _loop(self):
        server = self._server
        while not self._stop.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                paths, token = _read_message(conn)
                if paths:
                    self.opened.emit(paths, token)
                conn.sendall(b"ok\n")
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def stop(self):
        self._stop.set()
        server = self._server
        if server is not None:
            try:
                server.close()
            except OSError:
                pass
        try:
            self.path.unlink()
        except OSError:
            pass


class SleepInhibit(object):
    """Hold the awake lock only while playback is actually running."""

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else DBusSleep()
        self._want = False
        self._held = False

    def set_playing(self, playing):
        playing = bool(playing)
        if playing == self._want:
            return
        self._want = playing
        if playing:
            try:
                self._held = bool(self._backend.acquire("yucha", tr(53)))
            except Exception:
                self._held = False
            return
        if self._held:
            try:
                self._backend.release()
            except Exception:
                pass
            self._held = False

    def close(self):
        self.set_playing(False)


class DBusSleep(object):
    def __init__(self):
        self._portal = ""
        self._saver = None

    def acquire(self, app, reason):
        self.release()
        if self._inhibit_portal(reason):
            return True
        return self._inhibit_screensaver(app, reason)

    def release(self):
        if self._portal:
            _call(
                "org.freedesktop.portal.Desktop",
                self._portal,
                "org.freedesktop.portal.Request",
                "Close",
                [],
            )
            self._portal = ""
        if self._saver is not None:
            service, path, interface, cookie = self._saver
            _call(service, path, interface, "UnInhibit", [cookie])
            self._saver = None

    def _inhibit_portal(self, reason):
        reply = _call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Inhibit",
            "Inhibit",
            ["", _AWAKE_FLAGS, {"reason": reason}],
        )
        if not reply:
            return False
        handle = str(reply[0] or "")
        if not handle.startswith("/"):
            return False
        self._portal = handle
        return True

    def _inhibit_screensaver(self, app, reason):
        for service, path, interface in _SAVERS:
            reply = _call(service, path, interface, "Inhibit", [app, reason])
            if not reply:
                continue
            try:
                cookie = int(reply[0])
            except (TypeError, ValueError):
                continue
            if cookie <= 0:
                continue
            self._saver = (service, path, interface, cookie)
            return True
        return False


class Notifier(object):
    def __init__(self, icon=""):
        self.icon = icon or ""

    def show(self, summary, body):
        summary = str(summary or "")
        body = str(body or "")
        if not summary and not body:
            return
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return
        msg = QDBusMessage.createMethodCall(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
        )
        msg.setArguments([
            "yucha",
            0,
            self.icon,
            summary,
            body,
            [],
            {},
            5000,
        ])
        bus.asyncCall(msg)


def _call(service, path, interface, method, args):
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None
    msg = QDBusMessage.createMethodCall(service, path, interface, method)
    msg.setArguments(list(args))
    reply = bus.call(msg, QDBus.CallMode.Block, 800)
    if reply.type() != QDBusMessage.MessageType.ReplyMessage:
        return None
    return reply.arguments()
