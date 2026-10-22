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

PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%2B20261013-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA="178d3d83b6e8e99285a65d3fce9c16b87952cc5efdb4d1a0e3ff3be18ff0fc9c"
PY_TAR="$CACHE/cpython-3.12.15-install_only_stripped.tar.gz"
TOOL="$CACHE/appimagetool-x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
TOOL_SHA="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

fetch() {
    url="$1"
    dest="$2"
    want="$3"
    if [ -s "$dest" ] && echo "$want  $dest" | sha256sum -c - >/dev/null 2>&1; then
        return 0
    fi
    echo "fetch $url"
    curl -fL --retry 3 -o "$dest.part" "$url"
    mv "$dest.part" "$dest"
    if ! echo "$want  $dest" | sha256sum -c -; then
        echo "sha256 mismatch for $dest" >&2
        rm -f "$dest"
        exit 1
    fi
}

fetch "$PY_URL" "$PY_TAR" "$PY_SHA"
fetch "$TOOL_URL" "$TOOL" "$TOOL_SHA"
chmod +x "$TOOL"

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
# pip itself is not used when the image runs.
site=$("$APPDIR/python/bin/python3" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
rm -rf "$site/pip" "$site"/pip-*.dist-info
rm -f "$APPDIR/python/bin/pip" "$APPDIR/python/bin/pip3" "$APPDIR/python/bin/pip3.12"

cp -a "$ROOT/yucha" "$ROOT/LICENSE" "$ROOT/NOTICE" "$ROOT/README.md" \
    "$APPDIR/payload/"
cp -a "$ROOT/third_party/syncplay" "$ROOT/third_party/README.md" \
    "$APPDIR/payload/third_party/"
cp -a "$PACK/BUNDLED.txt" "$APPDIR/payload/BUNDLED.txt"
find "$APPDIR/payload" -type d -name __pycache__ -print0 | xargs -0r rm -rf
find "$APPDIR/payload" -name '*.pyc' -delete

# The picture is drawn by libmpv inside the window, not by a second mpv
# window. Copy the library and the libraries it needs, except the ones the
# desktop already provides (libc, OpenGL, Wayland).
APPDIR="$APPDIR" python3 - << 'PY'
import os, re, shutil, subprocess
from pathlib import Path

dest = Path(os.environ["APPDIR"]) / "usr" / "lib" / "yucha"
dest.mkdir(parents=True, exist_ok=True)
listed = subprocess.check_output(["ldconfig", "-p"], text=True, errors="replace")
src = None
for line in listed.splitlines():
    if "libmpv.so" in line and "=>" in line:
        src = line.split("=>", 1)[1].strip()
        break
if not src or not os.path.isfile(src):
    raise SystemExit("libmpv was not found. Install the libmpv2 package and rerun.")

skip = (
    "libc.so", "libm.so", "libdl.so", "librt.so", "libpthread.so",
    "libresolv.so", "ld-linux", "libstdc++.so", "libgcc_s.so",
    "libGL.so", "libEGL.so", "libGLdispatch", "libGLX", "libOpenGL",
    "libX11.so", "libxcb", "libwayland", "libdrm.so", "libgbm.so",
)
seen = set()

def skipped(name):
    return any(name.startswith(prefix) for prefix in skip)

def take(path):
    # Keep the name the loader asks for. ldd prints libavcodec.so.60, which
    # is a link to libavcodec.so.60.31.102. Copying only the real file leaves
    # the short name missing, and the player dies on startup.
    if not os.path.exists(path):
        return
    name = os.path.basename(path)
    if skipped(name):
        return
    real = os.path.realpath(path)
    real_name = os.path.basename(real)
    link = dest / name
    if real not in seen:
        if not os.path.isfile(real):
            return
        seen.add(real)
        shutil.copy2(real, dest / real_name)
        out = subprocess.check_output(["ldd", real], text=True, errors="replace")
        for line in out.splitlines():
            if "=>" not in line:
                continue
            dep = line.split("=>", 1)[1].strip().split()[0]
            if dep.startswith("/") and os.path.exists(dep):
                take(dep)
    if name != real_name and not link.exists():
        link.symlink_to(real_name)

take(src)
entry = dest / "libmpv.so.2"
if not entry.exists():
    shutil.copy2(os.path.realpath(src), entry)

missing = []
out = subprocess.check_output(["readelf", "-d", str(entry)], text=True, errors="replace")
for name in re.findall(r"Shared library: \[([^\]]+)\]", out):
    if skipped(name):
        continue
    if not (dest / name).exists():
        missing.append(name)
if missing:
    raise SystemExit("libmpv is missing libraries:\n" + "\n".join(missing))
print("bundled libmpv from", src)
PY

cp "$PACK/AppRun" "$APPDIR/AppRun"
# Syncplay runs `mpv --version` and then attaches to libmpv. The stub
# prints the version of the libmpv package copied above.
raw=""
if dpkg-query -W -f='${Status}' libmpv2 2>/dev/null | grep -q 'install ok installed'; then
    raw=$(dpkg-query -W -f='${Version}' libmpv2)
elif dpkg-query -W -f='${Status}' libmpv-dev 2>/dev/null | grep -q 'install ok installed'; then
    raw=$(dpkg-query -W -f='${Version}' libmpv-dev)
else
    echo "libmpv2 is not installed" >&2
    exit 1
fi
raw=${raw#*:}
raw=${raw%%[-+]*}
if ! printf '%s\n' "$raw" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "libmpv version is not numeric: $raw" >&2
    exit 1
fi
printf '%s\n' '#!/bin/sh' "echo \"mpv ${raw}\"" > "$APPDIR/mpv-launch"
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
