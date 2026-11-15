# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Labels from languages/*.ini. A line is `id = English original = text shown`."""

import os
import re
from collections import Counter
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "languages"
_phrases = {}
_name = "English"


_codes = {"en": "English", "ru": "Russian"}


def system_language():
    """The language file for this machine. An unknown language stays English."""
    choices = os.environ.get("LANGUAGE", "").split(":")
    choices.append(os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "")
    for raw in choices:
        code = re.split(r"[_.@-]", raw.strip().lower())[0]
        name = _codes.get(code)
        if name in languages():
            return name
    return "English"


def languages():
    """File names in languages/, without .ini. English stays first."""
    names = []
    if FOLDER.is_dir():
        names = sorted(path.stem for path in FOLDER.glob("*.ini") if path.is_file())
    if "English" in names:
        names.remove("English")
    names.insert(0, "English")
    return names


def use(name):
    """Load one language file over the English originals. A missing file stays on English."""
    global _phrases, _name
    base = _read(_file("English"))
    chosen = str(name or "").strip() or "English"
    if chosen == "System":
        chosen = system_language()
    path = _file(chosen)
    if path is None:
        chosen = "English"
        overlay = {}
    else:
        overlay = _read(path)
    merged = {}
    for number in set(base) | set(overlay):
        original = base.get(number, {}).get("en") or overlay.get(number, {}).get("en") or ""
        shown = overlay.get(number, {}).get("text") if number in overlay else ""
        merged[number] = {"en": original, "text": shown if shown and _same_fields(original, shown) else original}
    _name = chosen
    _phrases = merged


def current():
    return _name


def tr(number):
    """The label shown for this numeric id."""
    number = _number(number)
    row = _phrases.get(number)
    if row is None:
        return "" if number is None else str(number)
    return row["text"] or row["en"] or str(number)


def _same_fields(original, translated):
    def fields(pattern):
        return Counter((name, spec, conversion) for _, name, spec, conversion in Formatter().parse(pattern)
                       if name is not None)
    try:
        return fields(original) == fields(translated)
    except ValueError:
        return False


def trf(number, *args, **kwargs):
    """Like tr, but keeps the English original when a translation drops a {}."""
    number = _number(number)
    row = _phrases.get(number)
    if row is None:
        return "" if number is None else str(number)
    original = row["en"]
    pattern = row["text"] or original
    if not _same_fields(original, pattern):
        pattern = original
    try:
        return pattern.format(*args, **kwargs)
    except (IndexError, KeyError, ValueError):
        try:
            return original.format(*args, **kwargs)
        except (IndexError, KeyError, ValueError):
            return original or str(number)


def _number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _file(name):
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    folder = FOLDER.resolve()
    path = (folder / "{}.ini".format(name)).resolve()
    if path.parent != folder or not path.is_file():
        return None
    return path


def _read(path):
    table = {}
    if path is None:
        return table
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return table
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(";") or line.startswith("["):
            continue
        if line.count("=") < 2:
            continue
        left, rest = line.split("=", 1)
        original, shown = rest.rsplit("=", 1)
        number = left.strip()
        if not number.isdigit():
            continue
        original = original.strip()
        shown = shown.strip()
        table[int(number)] = {"en": original, "text": shown or original}
    return table


use("English")
