#!/bin/bash
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
# Standalone dev test only; never deploys a remote or a stable Flatpak branch.
set -euo pipefail
cd "$(dirname "$0")/../.."
test "$(uname -m)" = x86_64
sudo apt-get update
sudo apt-get install -y flatpak
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user --noninteractive flathub org.freedesktop.Platform/x86_64/25.08
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
flatpak build-init --arch=x86_64 "$work/app" org.yqhome.yucha org.freedesktop.Platform org.freedesktop.Platform 25.08
mkdir -p "$work/app/files/lib" "$work/app/files/bin" "$work/app/files/share/applications" \
    "$work/app/files/share/icons/hicolor/256x256/apps"
cp -a packaging/appimage/build/AppDir "$work/app/files/lib/yucha"
printf '#!/bin/sh\nexec /app/lib/yucha/AppRun "$@"\n' > "$work/app/files/bin/yucha"
chmod +x "$work/app/files/bin/yucha"
cp packaging/appimage/yucha.png "$work/app/files/share/icons/hicolor/256x256/apps/org.yqhome.yucha.png"
sed 's/^Icon=.*/Icon=org.yqhome.yucha/; s/^Exec=.*/Exec=yucha %F/' packaging/appimage/yucha.desktop \
    > "$work/app/files/share/applications/org.yqhome.yucha.desktop"
flatpak build-finish "$work/app" --command=yucha --share=network --share=ipc --device=dri \
    --socket=wayland --socket=fallback-x11 --socket=pulseaudio --filesystem=xdg-videos:ro
flatpak build-export --arch=x86_64 "$work/repo" "$work/app" test
flatpak build-bundle --arch=x86_64 --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$work/repo" dist/yucha-x86_64-test.flatpak org.yqhome.yucha test
flatpak install --user --noninteractive dist/yucha-x86_64-test.flatpak
flatpak run --command=sh org.yqhome.yucha//test -ec '
    export LD_LIBRARY_PATH=/app/lib/yucha/usr/lib/yucha
    export PYTHONPATH=/app/lib/yucha/payload
    export YUCHA_LIBMPV=/app/lib/yucha/usr/lib/yucha/libmpv.so.2
    /app/lib/yucha/python/bin/python3 -c "import yucha; from yucha.engine import _import_mpv; print(yucha.__version__); _import_mpv()"
'
flatpak uninstall --user --noninteractive org.yqhome.yucha//test
python3 packaging/appimage/verify.py dist --write
