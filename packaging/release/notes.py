# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Release notes from a dependency diff or from commit subjects."""

import re
import sys

SECTIONS = ("Added", "Changed", "Fixed", "Removed", "Security")


def deps_notes(diff):
    pairs = []
    path = None
    minus = []
    plus = []

    def flush():
        if path == "requirements.txt":
            pairs.extend(_req_pairs(minus, plus))
        elif path is not None and path.endswith((".yml", ".yaml")):
            pairs.extend(_action_pairs(minus, plus))
        elif path == "packaging/appimage/build.sh":
            pairs.extend(_tool_pairs(minus, plus))

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            flush()
            found = re.search(r" b/(.+)$", line)
            path = found.group(1) if found else None
            minus = []
            plus = []
            continue
        if line.startswith(("---", "+++", "@@", "index ", "new file", "deleted file")):
            continue
        if line.startswith("-"):
            minus.append(line[1:])
        elif line.startswith("+"):
            plus.append(line[1:])
    flush()
    if not pairs:
        return ""
    pairs = sorted(set(pairs))
    lines = ["Dependency updates."]
    for name, old, new in pairs:
        lines.append("- `%s` %s -> %s" % (name, old, new))
    return "\n".join(lines) + "\n"


def commit_notes(subjects):
    buckets = {name: [] for name in SECTIONS}
    for subject in subjects:
        section, text = _classify(subject)
        if section is None:
            continue
        buckets[section].append(text)
    lines = []
    for name in SECTIONS:
        if not buckets[name]:
            continue
        if lines:
            lines.append("")
        lines.append(name)
        for text in buckets[name]:
            lines.append("- %s" % text)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _classify(subject):
    text = subject.strip()
    lowered = text.lower()
    if lowered.startswith("merge ") or lowered.startswith("version "):
        return None, None
    if re.search(r"chmod |\./yucha|Test build", text):
        return None, None
    if not text.endswith("."):
        text = text + "."
    if re.match(r"^(add|implement)\b", lowered):
        return "Added", text
    if re.match(r"^(fix|resolve|prevent)\b", lowered):
        return "Fixed", text
    if re.match(r"^remove\b", lowered):
        return "Removed", text
    if re.match(r"^(redact|restrict)\b", lowered):
        return "Security", text
    return "Changed", text


def _req_pairs(minus, plus):
    old = _requirements(minus)
    new = _requirements(plus)
    pairs = []
    for name in old:
        if name in new and old[name] != new[name]:
            pairs.append((name, old[name], new[name]))
    return pairs


def _requirements(lines):
    found = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)(.*)$", line)
        if not match:
            continue
        constraint = match.group(2).strip()
        if not re.search(r"[0-9]", constraint):
            continue
        found[match.group(1)] = constraint
    return found


def _action_pairs(minus, plus):
    old = _actions(minus)
    new = _actions(plus)
    pairs = []
    for name in old:
        if name in new and old[name] != new[name]:
            pairs.append((name, old[name], new[name]))
    return pairs


def _actions(lines):
    found = {}
    pattern = re.compile(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(\S+)")
    for line in lines:
        match = pattern.search(line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def _tool_pairs(minus, plus):
    old = _tool(minus)
    new = _tool(plus)
    if old and new and old != new:
        return [("appimagetool", old, new)]
    return []


def _tool(lines):
    pattern = re.compile(r"download/([^/\s\"]+)/appimagetool")
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(1)
    return None


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("deps", "commits"):
        sys.exit(2)
    data = sys.stdin.read()
    if sys.argv[1] == "deps":
        text = deps_notes(data)
    else:
        text = commit_notes(data.splitlines())
    if not text:
        sys.exit(1)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
