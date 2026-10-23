# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Saved room login and appearance. The file is the user's, mode 0600."""

import json
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
