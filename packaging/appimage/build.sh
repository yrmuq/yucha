#!/bin/sh
# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
# Build a test AppImage. Not a 1.0 release. x86_64 only.
# Flatpak waits until 1.0. See packaging/appimage/BUNDLED.txt.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
PACK="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
WORK="$PACK/build"
CACHE="$WORK/cache"
APPDIR="$WORK/AppDir"
DIST="$ROOT/dist"
mkdir -p "$CACHE" "$DIST"

PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%2B20261013-x86_64-unknown-linux-gnu-install_only.tar.gz"
PY_TAR="$CACHE/cpython-3.12.15-install_only.tar.gz"
MPV_URL="https://github.com/pkgforge-dev/mpv-AppImage/releases/download/v0.41.0@2026-10-07_1791382432/mpv-v0.41.0-anylinux-x86_64.AppImage"
MPV_FILE="${MPV_APPIMAGE:-$CACHE/mpv-v0.41.0-anylinux-x86_64.AppImage}"
TOOL="$CACHE/appimagetool-x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

fetch() {
    url="$1"
    dest="$2"
    if [ -s "$dest" ]; then
        return 0
    fi
    echo "fetch $url"
    curl -fL --retry 3 -o "$dest.part" "$url"
    mv "$dest.part" "$dest"
}

fetch "$PY_URL" "$PY_TAR"
fetch "$MPV_URL" "$MPV_FILE"
fetch "$TOOL_URL" "$TOOL"
chmod +x "$TOOL" "$MPV_FILE"

if ! command -v file >/dev/null 2>&1; then
    echo "appimagetool needs the file(1) command. Install the 'file' package and rerun." >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
    "$APPDIR/payload/third_party"

tar -xzf "$PY_TAR" -C "$APPDIR"
test -x "$APPDIR/python/bin/python3"

"$APPDIR/python/bin/python3" -m pip install \
    --disable-pip-version-check \
    --no-warn-script-location \
    -r "$ROOT/requirements.txt"

EXTRACT="$WORK/mpv-extract"
rm -rf "$EXTRACT"
mkdir -p "$EXTRACT"
(
    cd "$EXTRACT"
    APPIMAGE_EXTRACT_AND_RUN=1 "$MPV_FILE" --appimage-extract >/dev/null
)
# The pkgforge runtime extracts into ./AppDir and also drops a relative
# symlink squashfs-root -> ./AppDir. Move the real directory, not the link.
if [ -d "$EXTRACT/AppDir" ] && [ ! -L "$EXTRACT/AppDir" ]; then
    mv "$EXTRACT/AppDir" "$APPDIR/mpv-bundle"
elif [ -d "$EXTRACT/squashfs-root" ] && [ ! -L "$EXTRACT/squashfs-root" ]; then
    mv "$EXTRACT/squashfs-root" "$APPDIR/mpv-bundle"
else
    echo "mpv extract layout was not recognized" >&2
    ls -la "$EXTRACT" >&2
    exit 1
fi
test -x "$APPDIR/mpv-bundle/AppRun"
# These hooks ask to download yt-dlp and to update the AppImage. Inside
# yucha that prompt is the wrong program, and it prints an error when no
# terminal emulator is installed. Host yt-dlp on PATH still works.
rm -f "$APPDIR/mpv-bundle/bin/05-get-yt-dlp.hook" \
    "$APPDIR/mpv-bundle/bin/10-self-updater.hook"

cp -a "$ROOT/yucha" "$ROOT/ui" "$ROOT/LICENSE" "$ROOT/NOTICE" "$ROOT/README.md" \
    "$APPDIR/payload/"
cp -a "$ROOT/third_party/syncplay" "$ROOT/third_party/README.md" \
    "$APPDIR/payload/third_party/"
cp -a "$PACK/BUNDLED.txt" "$APPDIR/payload/BUNDLED.txt"
find "$APPDIR/payload" -type d -name __pycache__ -print0 | xargs -0r rm -rf
find "$APPDIR/payload" -name '*.pyc' -delete

cp "$PACK/AppRun" "$APPDIR/AppRun"
cp "$PACK/mpv-launch" "$APPDIR/mpv-launch"
chmod +x "$APPDIR/AppRun" "$APPDIR/mpv-launch"
ln -s ../../AppRun "$APPDIR/usr/bin/yucha"
cp "$PACK/yucha.desktop" "$APPDIR/yucha.desktop"
cp "$PACK/yucha.desktop" "$APPDIR/usr/share/applications/yucha.desktop"
cp "$PACK/yucha.png" "$APPDIR/yucha.png"
cp "$PACK/yucha.png" "$APPDIR/.DirIcon"
cp "$PACK/yucha.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/yucha.png"

OUT="$DIST/yucha-x86_64.AppImage"
rm -f "$OUT"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "wrote $OUT"
ls -lh "$OUT"
