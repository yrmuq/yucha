#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
exec python3 "$(dirname "$0")/pin-tools.py"
