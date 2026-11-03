# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "syncplay"))

from yucha.configstore import font_name, hex_color, move_entry, wheel_rgb
from yucha.i18n import system_language
from yucha.player_ui import room_file_notes


class Color(unittest.TestCase):
    def test_hex_color_keeps_a_real_value(self):
        self.assertEqual(hex_color("#a1b2c3", "#FFFFFF"), "#A1B2C3")
        self.assertEqual(hex_color("red", "#FFFFFF"), "#FFFFFF")
        self.assertEqual(hex_color("#abc", "#FFFFFF"), "#FFFFFF")

    def test_font_name_rejects_a_blank_or_a_long_value(self):
        self.assertEqual(font_name("  DejaVu Sans  "), "DejaVu Sans")
        self.assertEqual(font_name("   "), "sans-serif")
        self.assertEqual(font_name("x" * 81), "sans-serif")

    def test_wheel_is_white_in_the_middle_and_red_at_the_right(self):
        self.assertEqual(wheel_rgb(0, 0, 100), (255, 255, 255))
        self.assertEqual(wheel_rgb(100, 0, 100), (255, 0, 0))
        self.assertIsNone(wheel_rgb(101, 0, 100))

    def test_move_entry_inserts_before_the_destination(self):
        items = ["a", "b", "c"]
        move_entry(items, 0, 3)
        self.assertEqual(items, ["b", "c", "a"])
        move_entry(items, 2, 0)
        self.assertEqual(items, ["a", "b", "c"])

    def test_system_language_uses_russian_or_english(self):
        previous_all = os.environ.get("LC_ALL")
        previous = os.environ.get("LANG")
        try:
            os.environ["LC_ALL"] = "ru_RU.UTF-8"
            self.assertEqual(system_language(), "Russian")
            os.environ["LC_ALL"] = "fr_FR.UTF-8"
            self.assertEqual(system_language(), "English")
        finally:
            if previous_all is None:
                os.environ.pop("LC_ALL", None)
            else:
                os.environ["LC_ALL"] = previous_all
            if previous is None:
                os.environ.pop("LANG", None)
            else:
                os.environ["LANG"] = previous

    def test_room_files_compare_size_and_duration_not_the_name(self):
        same = [
            {"name": "a", "file": "one.mkv", "size": 10, "duration": 90.0},
            {"name": "b", "file": "other.mkv", "size": 10, "duration": 90.0},
        ]
        self.assertEqual(room_file_notes(same), (False, []))
        different_size = [
            {"name": "a", "file": "one.mkv", "size": 10, "duration": 90.0},
            {"name": "b", "file": "one.mkv", "size": 11, "duration": 90.0},
        ]
        self.assertEqual(room_file_notes(different_size), (True, []))
        close_duration = [
            {"name": "a", "size": 10, "duration": 90.0},
            {"name": "b", "size": 10, "duration": 92.0},
        ]
        self.assertEqual(room_file_notes(close_duration)[0], True)
        missing = [
            {"name": "a", "size": 10, "duration": 90.0},
            {"name": "c", "file": "", "size": None, "duration": None},
        ]
        self.assertEqual(room_file_notes(missing), (False, ["c"]))


if __name__ == "__main__":
    unittest.main()
