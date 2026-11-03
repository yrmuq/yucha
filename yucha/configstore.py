# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Saved room login and appearance. The file is the user's, mode 0600."""

import json
import math
import os
from pathlib import Path


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    path = root / "yucha"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def port_number(value):
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None


def bounded_int(value, default, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def hex_color(value, default):
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        digits = text[1:]
        if all(char in "0123456789abcdefABCDEF" for char in digits):
            return "#" + digits.upper()
    return default


def font_name(value, default="sans-serif"):
    text = " ".join(str(value or "").split())
    if not text or len(text) > 80:
        return default
    return text


def wheel_rgb(dx, dy, radius):
    """One point on the color disc. The rim is a hue, the middle is white."""
    dist = math.hypot(dx, dy)
    if radius <= 0 or dist > radius:
        return None
    hue = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
    return _hsv_rgb(hue, dist / radius, 1.0)


def _hsv_rgb(hue, sat, val):
    column = val * sat
    sector = (hue / 60.0) % 6.0
    mix = column * (1 - abs(sector % 2 - 1))
    base = val - column
    if sector < 1:
        red, green, blue = column, mix, 0
    elif sector < 2:
        red, green, blue = mix, column, 0
    elif sector < 3:
        red, green, blue = 0, column, mix
    elif sector < 4:
        red, green, blue = 0, mix, column
    elif sector < 5:
        red, green, blue = mix, 0, column
    else:
        red, green, blue = column, 0, mix
    return (
        int(round((red + base) * 255)),
        int(round((green + base) * 255)),
        int(round((blue + base) * 255)),
    )


def runtime_dir():
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else config_dir()
    path = root / "yucha"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


DEFAULTS = {
    "connection": {
        "host": "",
        "port": 8999,
        "name": "",
        "password": "",
        "room": "",
    },
    "appearance": {
        "theme": "dark",
        "chatColor": "#F4F1EA",
        "accentColor": "#9A3A52",
        "accentColor2": "#1F6A8A",
        "chatFontSize": 18,
        "uiFontSize": 16,
        "autoplayNext": False,
        "fastforwardOnDesync": True,
        "slowOnDesync": True,
        "volumeMax": 100,
        "volumeOverlay": "horizontal",
        "language": "English",
        "subFont": "sans-serif",
        "subFontSize": 55,
        "subColor": "#FFFFFF",
    },
}


class ConfigStore(object):
    def __init__(self):
        self.path = config_dir() / "config.json"
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        if not self.path.is_file():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for section in ("connection", "appearance"):
            if isinstance(loaded.get(section), dict):
                self.data[section].update(loaded[section])
        look = self.data["appearance"]
        look["uiFontSize"] = bounded_int(look.get("uiFontSize"), 16, 1, 32)
        look["chatFontSize"] = bounded_int(look.get("chatFontSize"), 18, 12, 48)
        look["subFontSize"] = bounded_int(look.get("subFontSize"), 55, 8, 120)
        look["subColor"] = hex_color(look.get("subColor"), "#FFFFFF")
        look["subFont"] = font_name(look.get("subFont"))

    def save(self):
        payload = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def has_connection(self):
        conn = self.data["connection"]
        return bool(
            str(conn.get("host") or "").strip()
            and str(conn.get("name") or "").strip()
            and str(conn.get("room") or "").strip()
        )
