# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""yucha — mpv window plus the Syncplay client, without Syncplay's window."""

__version__ = "0.3.1"


def version_tuple(text):
    raw = str(text).strip()
    if raw[:1] in ("v", "V"):
        raw = raw[1:]
    parts = []
    for piece in raw.split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            return None
        parts.append(int(digits))
    return tuple(parts) or None


def newer_stable(current, releases):
    """Newest stable release newer than current. Drafts and prereleases do not count."""
    current_v = version_tuple(current)
    if current_v is None:
        return None
    best = None
    best_v = None
    for item in releases:
        if not isinstance(item, dict) or item.get("draft") or item.get("prerelease"):
            continue
        found = version_tuple(item.get("tag_name") or "")
        if found is None or found <= current_v:
            continue
        if best_v is None or found > best_v:
            best_v = found
            best = found
    if best is None:
        return None
    return ".".join(str(part) for part in best)
