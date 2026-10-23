# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Labels from languages/*.ini. A line is `id = English original = text shown`."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "languages"
_phrases = {}
_name = "English"


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
        merged[number] = {"en": original, "text": shown or original}
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


def trf(number, *args):
    """Like tr, but keeps the English original when a translation drops a {}."""
    number = _number(number)
    row = _phrases.get(number)
    if row is None:
        return "" if number is None else str(number)
    original = row["en"]
    pattern = row["text"] or original
    if pattern.count("{}") != original.count("{}"):
        pattern = original
    try:
        return pattern.format(*args)
    except (IndexError, KeyError, ValueError):
        try:
            return original.format(*args)
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
