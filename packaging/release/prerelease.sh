#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
# Number the next dependency prerelease and tag it locally. The caller pushes
# only after the AppImage build succeeds. Old tags stay, so the number climbs.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

git fetch origin --tags --force
file_ver="$(sed -n 's/^__version__ = "\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)"/\1/p' yucha/__init__.py | head -n 1)"
major="$(printf '%s\n' "$file_ver" | awk -F. '{ print $1 }')"
minor="$(printf '%s\n' "$file_ver" | awk -F. '{ print $2 }')"
max="$(printf '%s\n' "$file_ver" | awk -F. '{ print $3 }')"
for tag in $(git tag -l "v${major}.${minor}.*"); do
    case "$tag" in
        v[0-9]*.[0-9]*.[0-9]*) ;;
        *) continue ;;
    esac
    patch="$(printf '%s\n' "$tag" | awk -F. '{ print $3 }' | tr -cd '0-9')"
    if [ -n "$patch" ] && [ "$patch" -gt "$max" ]; then
        max="$patch"
    fi
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
git add yucha/__init__.py chit/lore.md
git commit -m "Version ${new}."
git -c core.commentChar=% tag -a "v${new}" -F notes.md
printf '%s\n' "$new"
