# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Labels from languages/*.txt. Left of '=' is shown. Right is the English original."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "languages"
_phrases = {}
_name = "English"


def languages():
    """File names in languages/, without .txt. English stays first."""
    names = []
    if FOLDER.is_dir():
        names = sorted(path.stem for path in FOLDER.glob("*.txt") if path.is_file())
    if "English" in names:
        names.remove("English")
    names.insert(0, "English")
    return names


def use(name):
    """Load one language file. A missing file stays on English."""
    global _phrases, _name
    chosen = str(name or "").strip() or "English"
    path = _file(chosen)
    if path is None:
        chosen = "English"
        path = _file(chosen)
    _name = chosen
    _phrases = _read(path)


def current():
    return _name


def tr(english):
    """The label shown for this English original."""
    return _phrases.get(english, english)


def trf(english, *args):
    """Like tr, but keeps the original when a translation drops a {}."""
    pattern = tr(english)
    if pattern.count("{}") != english.count("{}"):
        pattern = english
    try:
        return pattern.format(*args)
    except (IndexError, KeyError, ValueError):
        return english.format(*args)


def _file(name):
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    folder = FOLDER.resolve()
    path = (folder / "{}.txt".format(name)).resolve()
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
        if not line or line.startswith("#") or "=" not in line:
            continue
        left, right = line.rsplit("=", 1)
        right = right.strip()
        left = left.strip()
        if right:
            table[right] = left or right
    return table
