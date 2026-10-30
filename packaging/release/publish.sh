#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish dist/yucha-x86_64.AppImage for one annotated tag.
# X.Y.0 is a normal release. Any other X.Y.Z is a prerelease.
set -eu

TAG="${1:?tag}"
ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

case "$TAG" in
    *-test)
        echo "leaving the old test tag alone"
        exit 0
        ;;
esac
VER="${TAG#v}"
VER="${VER%-alpha}"
printf '%s\n' "$VER" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || {
    echo "tag ${TAG} is not a version" >&2
    exit 1
}
git fetch origin "+refs/tags/${TAG}:refs/tags/${TAG}" 2>/dev/null || true
git tag -l --format='%(contents)' "$TAG" > notes.md
if ! grep -q '[^[:space:]]' notes.md; then
    echo "the annotated tag message is the release notes, and it is empty" >&2
    exit 1
fi
if grep -E 'Test build|chmod |\./yucha' notes.md; then
    echo "release notes must not include run commands or a test-build banner" >&2
    exit 1
fi

case "$VER" in
    *.*.0)
        title="yucha ${VER}"
        extra=""
        ;;
    *)
        title="yucha ${VER}"
        extra="--prerelease"
        ;;
esac

if gh release view "$TAG" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
    gh release upload "$TAG" dist/yucha-x86_64.AppImage \
        --repo "$GITHUB_REPOSITORY" \
        --clobber
    # shellcheck disable=SC2086
    gh release edit "$TAG" \
        --repo "$GITHUB_REPOSITORY" \
        $extra \
        --title "$title" \
        --notes-file notes.md
else
    # shellcheck disable=SC2086
    gh release create "$TAG" dist/yucha-x86_64.AppImage \
        --repo "$GITHUB_REPOSITORY" \
        $extra \
        --title "$title" \
        --notes-file notes.md
fi
