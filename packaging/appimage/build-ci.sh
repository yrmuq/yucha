#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
# Keep native libraries on glibc 2.41 even when ubuntu-latest advances.
docker run --rm --mount "type=bind,src=$ROOT,dst=/src" --workdir /src \
    debian:trixie-slim sh -ec '
        test "$(getconf GNU_LIBC_VERSION)" = "glibc 2.41"
        apt-get update
        apt-get install -y --no-install-recommends \
            bash ca-certificates curl xz-utils git file binutils zsync \
            libmpv2 pipewire-bin libpipewire-0.3-modules libspa-0.2-modules \
            libegl1 libgl1 libxcb-cursor0 fonts-dejavu-core python3
        bash packaging/appimage/build.sh
    '
