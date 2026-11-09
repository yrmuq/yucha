# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""YouTube video identity and the stream metadata shown by yucha."""

import re
from functools import lru_cache
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QLocale


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
        if height >= 480 and (height not in by_height or track.get("selected")):
            by_height[height] = track
    return [(height, by_height[height]) for height in sorted(by_height, reverse=True)]


def quality_label(height):
    return {1440: "2K", 2160: "4K"}.get(height, "{}p".format(height)) if height else "—"


def track_language(track):
    code = str(track.get("lang") or "").replace("_", "-").split("-")[0]
    return _track_language(code, str(track.get("title") or "").casefold())


@lru_cache(maxsize=256)
def _track_language(code, title):
    locale = QLocale(code)
    if code and locale.language() != QLocale.Language.C:
        return locale.language()
    # libmpv's all-formats hook keeps yt-dlp's language in the title, not lang.
    for language in QLocale.Language:
        if language in (QLocale.Language.AnyLanguage, QLocale.Language.C):
            continue
        names = (QLocale.languageToString(language), QLocale(language).nativeLanguageName())
        if any(name and re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", title)
               for name in names):
            return language
    return QLocale.Language.AnyLanguage


def subtitle_tracks(tracks):
    allowed = {QLocale.system().language(), QLocale.Language.English}
    return [track for track in tracks if track.get("type") == "sub" and track_language(track) in allowed]


def audio_tracks(tracks):
    by_language = {}
    for track in tracks:
        if track.get("type") != "audio":
            continue
        language = track_language(track)
        previous = by_language.get(language)
        rank = lambda item: tuple(item.get(key) or 0 for key in
                                  ("demux-bitrate", "demux-channel-count", "demux-samplerate"))
        if previous is None or rank(track) > rank(previous):
            by_language[language] = track
    return [(QLocale.languageToString(language) if language != QLocale.Language.AnyLanguage else "Audio", track)
            for language, track in by_language.items()]
