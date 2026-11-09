# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "third_party" / "syncplay"))

from twisted.internet import reactor
from twisted.internet.testing import StringTransport

from syncplay.server import SyncFactory
from yucha.player_ui import PlayerUI, room_file_notes
from yucha.session import RoomClient
from yucha.youtube import video_url


class YouTubeTests(unittest.TestCase):
    def test_video_identity_rejects_other_hosts_and_collapses_link_variants(self):
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        self.assertEqual(video_url("https://youtu.be/jNQXAC9IVRw?t=30"), url)
        self.assertEqual(video_url("https://www.youtube.com/shorts/jNQXAC9IVRw"), url)
        self.assertEqual(video_url("https://youtube.com.evil.test/watch?v=jNQXAC9IVRw"), "")
        self.assertEqual(video_url("https://www.youtube.com/playlist?list=example"), "")
        people = [{"name": "a", "youtube": url, "height": 720},
                  {"name": "b", "youtube": url, "height": 1080}]
        self.assertEqual(room_file_notes(people), (False, []))

    def test_room_server_preserves_stream_metadata_for_other_clients(self):
        before = set(reactor.getDelayedCalls())

        def cancel_server_timers():
            for call in reactor.getDelayedCalls():
                if call not in before:
                    call.cancel()

        self.addCleanup(cancel_server_timers)
        with redirect_stdout(io.StringIO()):
            server = SyncFactory(salt="test")

        def peer(name):
            protocol = server.buildProtocol(None)
            transport = StringTransport()
            protocol.makeConnection(transport)
            protocol.handleHello({"username": name, "room": {"name": "room"},
                                  "version": "1.7.7", "features": {}})
            return protocol, transport

        first, _ = peer("first")
        second, transport = peer("second")
        transport.clear()
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        client = RoomClient.__new__(RoomClient)
        current = SimpleNamespace(file={"name": url, "size": 0, "duration": 20, "path": url})
        client.userlist = SimpleNamespace(currentUser=current)
        client._protocol = SimpleNamespace(logged=True,
                                           sendFileSetting=lambda file: first.handleSet({"file": file}))
        client.set_youtube_info(url, "A video", 720)
        second.sendList()
        updates = [json.loads(line) for line in transport.value().splitlines()]
        broadcast = updates[0]["Set"]["user"]["first"]["file"]
        listed = updates[-1]["List"]["room"]["first"]["file"]
        self.assertEqual(broadcast, listed)
        self.assertNotIn("path", listed)
        self.assertNotIn("yucha_youtube", current.file)
        watcher = SimpleNamespace(file=listed, room="room", username="first", isReady=lambda: True)
        ui = PlayerUI(Mock())
        ui.addClient(SimpleNamespace(userlist=SimpleNamespace(currentUser=None, _users={"first": watcher})))
        ui.userListChange()
        person = ui.bridge.emit.call_args.args[0]["list"][0]
        self.assertEqual((person["youtube"], person["title"], person["height"]), (url, "A video", 720))
