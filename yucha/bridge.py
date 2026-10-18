# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Line-delimited JSON from this process to the window.

events.jsonl   Python -> window
A slow reader can see one repeated line after a trim.
"""

import json
import os
import threading


KEEP = 100_000


class Bridge(object):
    def __init__(self, directory, keep=KEEP):
        self.directory = directory
        self.events_path = directory / "events.jsonl"
        self.keep = keep
        self.events_path.write_text("", encoding="utf-8")
        try:
            os.chmod(directory, 0o700)
            os.chmod(self.events_path, 0o600)
        except OSError:
            pass
        self._lock = threading.Lock()
        self._base = 0

    def emit(self, event):
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            with self.events_path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                size = handle.tell()
            if size <= self.keep:
                return
            raw = self.events_path.read_bytes()
            start = max(0, len(raw) - self.keep)
            nl = raw.find(b"\n", start)
            if nl < 0 or nl + 1 >= len(raw):
                tail = b""
                dropped = len(raw)
            else:
                tail = raw[nl + 1:]
                dropped = nl + 1
            self.events_path.write_bytes(tail)
            self._base += dropped

    def read_new(self, pos):
        """Events written since absolute byte offset pos. Returns (events, new_pos)."""
        with self._lock:
            try:
                raw = self.events_path.read_bytes()
            except OSError:
                return [], pos
            local = pos - self._base
            if local < 0:
                local = 0
            if local > len(raw):
                return [], self._base + len(raw)
            chunk = raw[local:]
            cut = chunk.rfind(b"\n")
            if cut < 0:
                return [], pos
            chunk = chunk[:cut + 1]
            new_pos = self._base + local + len(chunk)
        events = []
        for line in chunk.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events, new_pos
