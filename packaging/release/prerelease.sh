#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
# Reserve the next dependency version in both retained tags and a durable record.
# The caller publishes assets only after the build succeeds.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git fetch origin --tags
file_ver="$(sed -n 's/^__version__ = "\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)"/\1/p' yucha/__init__.py | head -n 1)"
major="$(printf '%s\n' "$file_ver" | awk -F. '{ print $1 }')"
minor="$(printf '%s\n' "$file_ver" | awk -F. '{ print $2 }')"
max="$(printf '%s\n' "$file_ver" | awk -F. '{ print $3 }')"
allocated=.github/allocated-versions.txt
for version in $(git tag -l "v${major}.${minor}.*"; sed -n '/^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$/p' "$allocated" 2>/dev/null || true); do
    version="${version#v}"
    case "$version" in
        "${major}.${minor}."*) ;;
        *) continue ;;
    esac
    patch="${version##*.}"
    case "$patch" in *[!0-9]*|'') continue ;; esac
    if [ "$patch" -gt "$max" ]; then max="$patch"; fi
done
new="${major}.${minor}.$((max + 1))"
if git rev-parse -q --verify "refs/tags/v${new}" >/dev/null; then
    echo "tag v${new} already exists" >&2
    exit 1
fi

git diff origin/main -- requirements.txt .github packaging/appimage/build.sh \
    | python3 packaging/release/notes.py deps > notes.md
python3 packaging/release/bump.py "$new"
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-github-actions[bot]}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"
mkdir -p .github
printf '%s\n' "$new" >> "$allocated"
git add yucha/__init__.py "$allocated"
git commit -m "Version ${new}."
git -c core.commentChar=% tag -a "v${new}" -F notes.md
printf '%s\n' "$new"
