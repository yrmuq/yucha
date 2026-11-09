# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""YouTube video identity and the stream metadata shown by yucha."""

import re
from urllib.parse import parse_qs, urlsplit


def video_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        return ""
    try:
        url = urlsplit(value.strip())
        if url.scheme not in ("http", "https") or url.username is not None or url.port is not None:
            return ""
    except ValueError:
        return ""
    path = url.path.strip("/").split("/")
    if url.hostname == "youtu.be" and len(path) == 1:
        ident = path[0]
    elif url.hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if path == ["watch"]:
            ident = parse_qs(url.query).get("v", [""])[0]
        elif len(path) == 2 and path[0] in ("shorts", "embed", "live"):
            ident = path[1]
        else:
            return ""
    else:
        return ""
    return "https://www.youtube.com/watch?v=" + ident if re.fullmatch(r"[\w-]{11}", ident, re.ASCII) else ""


def stream_title(value):
    return " ".join(value[:400].split()) if isinstance(value, str) else ""


def resolution(value):
    return value if type(value) is int and 0 < value <= 16384 else 0


def quality_tracks(tracks):
    by_height = {}
    for track in tracks:
        if track.get("type") != "video" or track.get("albumart") or track.get("id") is None:
            continue
        height = resolution(track.get("demux-h"))
        if height and (height not in by_height or track.get("selected")):
            by_height[height] = track
    return [(height, by_height[height]) for height in sorted(by_height, reverse=True)]
