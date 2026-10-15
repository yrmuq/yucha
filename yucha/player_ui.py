# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""UI object Syncplay calls. Drawing happens in the mpv script, not here."""

import re

from syncplay import constants
from syncplay.messages import getMessage


_CHAT = re.compile(r"^<([^>\n]+)> (.*)$", re.DOTALL)


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
        chat = _CHAT.match(text)
        if chat:
            self.bridge.emit({
                "e": "chat",
                "user": chat.group(1),
                "text": chat.group(2),
            })
            return
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
