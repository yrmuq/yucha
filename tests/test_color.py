# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from yucha.configstore import font_name, hex_color, wheel_rgb


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


if __name__ == "__main__":
    unittest.main()
