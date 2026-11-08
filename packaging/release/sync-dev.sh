#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
# Run only after publishing the release at HEAD.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

released="$(git rev-parse HEAD)"
git fetch origin refs/heads/dev:refs/remotes/origin/dev
if git merge-base --is-ancestor "$released" origin/dev; then
    exit 0
fi

git checkout --detach origin/dev
git merge --no-ff "$released" -m "Merge released main into dev"
git push origin HEAD:refs/heads/dev
