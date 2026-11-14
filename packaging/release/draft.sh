#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
cd "$(dirname "$0")/../.."
python3 packaging/appimage/verify.py dist
current="$(git ls-remote origin refs/heads/dev | cut -f1)"
if [ "$current" != "$GITHUB_SHA" ]; then
    echo "Skipping superseded draft build $GITHUB_SHA"
    exit 0
fi
draft="$(gh release list --repo "$GITHUB_REPOSITORY" --limit 100 --json tagName,name,isDraft \
    --jq '.[] | select(.isDraft and .name == "yucha dev") | .tagName' | head -n 1)"
printf 'Development build from dev. Not a release.\nCommit: %s\n' "$GITHUB_SHA" > notes.md
if [ -z "$draft" ]; then
    # GitHub leaves the tag uncreated while this release remains a draft.
    draft=dev
    gh release create "$draft" --draft --target "$GITHUB_SHA" --title "yucha dev" \
        --notes-file notes.md --repo "$GITHUB_REPOSITORY"
fi
gh release upload "$draft" dist/* --clobber --repo "$GITHUB_REPOSITORY"
if [ ! -f dist/yucha-x86_64-test.flatpak ]; then
    if gh release view "$draft" --repo "$GITHUB_REPOSITORY" --json assets \
        --jq '.assets[].name' | grep -Fxq yucha-x86_64-test.flatpak; then
        gh release delete-asset "$draft" yucha-x86_64-test.flatpak --yes --repo "$GITHUB_REPOSITORY"
    fi
fi
gh release edit "$draft" --draft --target "$GITHUB_SHA" --notes-file notes.md --repo "$GITHUB_REPOSITORY"

python3 packaging/release/verify-upload.py "$draft" true
