# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""UI object Syncplay calls. The window draws. This only forwards what Syncplay would show itself."""

import re

from syncplay import constants
from syncplay.messages import getMessage
from yucha.youtube import resolution, stream_title, video_url


_CHAT = re.compile(r"^<([^>\n]+)> (.*)$", re.DOTALL)


def room_file_notes(people):
    """Whether loaded files differ, and who has not opened one.

    Local files use size and duration. YouTube uses the canonical video URL.
    """
    if len(people) < 2:
        return False, []
    loaded = []
    missing = []
    for person in people:
        if person.get("youtube"):
            loaded.append(person["youtube"])
            continue
        size = _file_size(person.get("size"))
        duration = _file_duration(person.get("duration"))
        if size is None and duration is None:
            missing.append(str(person.get("name") or ""))
            continue
        if size is None or duration is None:
            continue
        loaded.append((size, duration))
    differ = len(loaded) >= 2 and any(item != loaded[0] for item in loaded[1:])
    return differ, [name for name in missing if name]


def _file_size(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    if size < 0:
        return None
    return size


def _file_duration(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return round(duration, 3)


def _is_seek(spans):
    return any(span.get("k") == "mark" and span.get("v") == "jump" for span in spans or [])


def replace_seek_toast(items, spans, now, slide):
    """Update the newest visible seek toast instead of stacking another one.

    Returns True when the existing toast was reused. Its hide timer starts over
    and it does not slide in again.
    """
    if not _is_seek(spans):
        return False
    latest = None
    for item in items:
        leave = item.get("leave")
        if leave is not None and now - leave >= slide:
            continue
        latest = item
    if latest is None or not _is_seek(latest.get("spans")):
        return False
    latest["spans"] = spans
    latest["fresh"] = now
    latest["leave"] = None
    return True


class PlayerUI(object):
    """Methods Syncplay's UiManager expects. Unknown calls are ignored."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.uiMode = constants.CONSOLE_UI_MODE
        self._syncplayClient = None
        self._connected = False
        self._fail_text = None

    def addClient(self, client):
        self._syncplayClient = client

    def _fail(self, text):
        generic = (
            getMessage("disconnection-notification"),
            getMessage("connection-failed-notification"),
        )
        # Keep the specific reason (wrong password, and so on). A later
        # "disconnected" from the same attempt would hide it.
        if self._fail_text and text in generic:
            return
        self._fail_text = text
        self._connected = False
        self.bridge.emit({
            "e": "conn",
            "state": "failed",
            "text": text,
            "openPanel": True,
        })

    def showMessage(self, message, noTimestamp=False, isMotd=False):
        text = "" if message is None else str(message)
        if text == getMessage("ready-to-unpause-notification"):
            return
        chat = _CHAT.match(text)
        if chat:
            self.bridge.emit({
                "e": "chat",
                "user": chat.group(1),
                "text": chat.group(2),
            })
        elif text:
            self.bridge.emit({"e": "chat-local", "text": text})
        # "Successfully reached" is only the TCP socket. The room is joined
        # when Syncplay says it connected to the server.
        joined = getMessage("connected-successful-notification")
        failed = getMessage("connection-failed-notification")
        dropped = getMessage("disconnection-notification")
        if text.startswith(joined):
            self._connected = True
            self._fail_text = None
            self.bridge.emit({"e": "conn", "state": "connected", "text": "connected"})
        elif text.startswith(failed) or text.startswith(dropped):
            self._fail(text)
        elif (text == getMessage("reconnection-attempt-notification") or
              text.startswith(getMessage("connection-attempt-notification").split("{", 1)[0])):
            self._connected = False
            self._fail_text = None
            self.bridge.emit({"e": "conn", "state": "connecting", "text": text})

    def showErrorMessage(self, message, criticalerror=False):
        text = "" if message is None else str(message)
        if not text:
            return
        # Plain servers answer the TLS probe with this and then continue.
        if text == getMessage("startTLS-not-supported-server"):
            return
        # Syncplay prints the Twisted failure object on every socket close.
        if text.startswith("<class ") or text.startswith("[Failure") or "Traceback" in text:
            return
        if text in ("Connection was closed cleanly.", "Connection lost"):
            return
        self.bridge.emit({"e": "chat-local", "text": text})
        fatal_keys = (
            "connection-failed-notification",
            "disconnection-notification",
            "server-timeout-error",
            "password-required-server-error",
            "wrong-password-server-error",
            "hello-server-error",
        )
        fatal = criticalerror or any(
            text.startswith(getMessage(key).split("{", 1)[0]) for key in fatal_keys
        )
        if fatal or not self._connected:
            self._fail(text)

    def userListChange(self):
        client = self._syncplayClient
        userlist = getattr(client, "userlist", None) if client is not None else None
        if userlist is None:
            return
        current = userlist.currentUser
        room = current.room if current is not None else None
        people = []

        def add(user):
            if user is None or not user.username:
                return
            if room and user.room and user.room != room:
                return
            filename = ""
            size = None
            duration = None
            stream = {}
            current_file = getattr(user, "file", None)
            if isinstance(current_file, dict) and current_file.get("name"):
                filename = str(current_file.get("name") or "")
                raw = current_file.get("size")
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    size = raw
                raw_duration = current_file.get("duration")
                if isinstance(raw_duration, (int, float)) and not isinstance(raw_duration, bool):
                    duration = raw_duration
                url = video_url(filename)
                if url:
                    info = current_file.get("yucha_youtube")
                    info = info if isinstance(info, dict) else {}
                    stream = {
                        "youtube": url,
                        "title": stream_title(info.get("title")),
                        "height": resolution(info.get("height")),
                    }
            people.append({
                "name": user.username,
                "ready": bool(user.isReady()),
                "file": filename,
                "size": size,
                "duration": duration,
                **stream,
            })

        add(current)
        for user in userlist._users.values():
            add(user)
        self.bridge.emit({"e": "users", "list": people})

    def showDebugMessage(self, message):
        return None

    def promptFor(self, prompt=">", message=""):
        return ""

    def addFileToPlaylist(self, newPlaylistItem):
        client = self._syncplayClient
        if client is not None:
            client.playlist.addToPlaylist(newPlaylistItem)

    def drop(self):
        return None

    def __getattr__(self, name):
        def _unused(*args, **kwargs):
            return None
        return _unused
