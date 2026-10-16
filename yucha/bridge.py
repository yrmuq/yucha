# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Line-delimited JSON between this process and the mpv UI script.

events.jsonl   Python -> Lua
commands.jsonl Lua -> Python
"""

import json
import os
import threading


class Bridge(object):
    def __init__(self, directory):
        self.directory = directory
        self.events_path = directory / "events.jsonl"
        self.commands_path = directory / "commands.jsonl"
        self.events_path.write_text("", encoding="utf-8")
        self.commands_path.write_text("", encoding="utf-8")
        try:
            os.chmod(directory, 0o700)
            os.chmod(self.events_path, 0o600)
            os.chmod(self.commands_path, 0o600)
        except OSError:
            pass
        self._lock = threading.Lock()
        self._cmd_lines = 0

    def emit(self, event):
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._lock:
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()

    def read_commands(self):
        try:
            text = self.commands_path.read_text(encoding="utf-8")
        except OSError:
            return []
        lines = text.splitlines()
        if text and not text.endswith("\n") and lines:
            lines = lines[:-1]
        fresh = lines[self._cmd_lines:]
        self._cmd_lines = len(lines)
        commands = []
        for line in fresh:
            line = line.strip()
            if not line:
                continue
            try:
                commands.append(json.loads(line))
            except ValueError:
                continue
        return commands

    def read_new(self, pos):
        """Events written since byte offset pos. Returns (events, new_pos)."""
        try:
            raw = self.events_path.read_bytes()
        except OSError:
            return [], pos
        if pos < 0 or pos > len(raw):
            pos = 0
        chunk = raw[pos:]
        cut = chunk.rfind(b"\n")
        if cut < 0:
            return [], pos
        chunk = chunk[:cut + 1]
        pos += len(chunk)
        events = []
        for line in chunk.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events, pos
