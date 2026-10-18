# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "syncplay"))

from yucha.bridge import Bridge
from yucha.configstore import ConfigStore, port_number
from yucha.session import load_client_tls


class Guards(unittest.TestCase):
    def test_port(self):
        self.assertIsNone(port_number("abc"))
        self.assertEqual(port_number("8999"), 8999)
        self.assertEqual(port_number(8999), 8999)
        self.assertIsNone(port_number(0))
        self.assertIsNone(port_number(65536))
        self.assertIsNone(port_number(""))

    def test_font_clamp(self):
        previous = os.environ.get("XDG_CONFIG_HOME")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["XDG_CONFIG_HOME"] = tmp
            folder = Path(tmp) / "yucha"
            folder.mkdir()
            (folder / "config.json").write_text(
                '{"appearance": {"uiFontSize": "large", "chatFontSize": 99}}',
                encoding="utf-8",
            )
            store = ConfigStore()
            self.assertEqual(store.data["appearance"]["uiFontSize"], 16)
            self.assertEqual(store.data["appearance"]["chatFontSize"], 48)
        if previous is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = previous

    def test_missing_cert_is_not_encrypted(self):
        self.assertIsNone(load_client_tls("example.test", "/no/such/yucha-certs.pem"))

    def test_bridge_trim_does_not_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = Bridge(Path(tmp), keep=120)
            for index in range(3):
                bridge.emit({"e": "old", "i": index})
            events, pos = bridge.read_new(0)
            self.assertEqual([item["i"] for item in events], [0, 1, 2])
            bridge.emit({"e": "new", "i": 9, "pad": "x" * 80})
            fresh, pos = bridge.read_new(pos)
            self.assertTrue(fresh)
            self.assertTrue(all(item["e"] == "new" for item in fresh))
            self.assertEqual(bridge.read_new(pos)[0], [])
            again, end = bridge.read_new(0)
            self.assertEqual(bridge.read_new(end)[0], [])
            self.assertEqual(len(again), len({item["i"] for item in again}))


if __name__ == "__main__":
    unittest.main()
