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
rm -f "$DIST/yucha-x86_64-test.flatpak" "$DIST/SHA256SUMS"

PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261124/cpython-3.12.16%2B20261124-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PY_SHA="7e1adaea26c959d13aa1120be1ae62a1ea1bb52adcb382679fffe9217e22adff"
PY_TAR="$CACHE/cpython-3.12.16-install_only_stripped.tar.gz"
NODE_DIST="node-v24.22.3-linux-x64"
NODE_TAR="$CACHE/$NODE_DIST.tar.xz"
NODE_URL="https://nodejs.org/download/release/v24.22.3/node-v24.22.3-linux-x64.tar.xz"
NODE_SHA="4f2b175a6d53a5c617a80dba2676238a0688cef28c6da4eba35c7d844e66fcfb"
TOOL="$CACHE/appimagetool-x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
TOOL_SHA="e8c1169c4af66c3184d7ee110713d4be04befe671fa358e2c1591ee840553b03"

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
fetch "$NODE_URL" "$NODE_TAR" "$NODE_SHA"
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
tar -xJf "$NODE_TAR" -C "$APPDIR/usr/bin" --strip-components=2 "$NODE_DIST/bin/node"
tar -xJOf "$NODE_TAR" "$NODE_DIST/LICENSE" > "$APPDIR/payload/LICENSE.node"

PIP_CACHE_DIR="$CACHE/pip" "$APPDIR/python/bin/python3" -m pip install \
    --disable-pip-version-check \
    --no-warn-script-location \
    -r "$ROOT/requirements.txt"
# pip itself is not used when the image runs.
site=$("$APPDIR/python/bin/python3" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
rm -rf "$site/pip" "$site"/pip-*.dist-info
rm -f "$APPDIR/python/bin/pip" "$APPDIR/python/bin/pip3" "$APPDIR/python/bin/pip3.12"

cat > "$APPDIR/usr/bin/yt-dlp" << 'SH'
#!/bin/sh
set -eu
here="$(dirname "$(readlink -f "$0")")"
exec "$here/../../python/bin/python3" -m yucha.ytdl --no-js-runtimes --js-runtimes "node:$here/node" "$@"
SH
chmod +x "$APPDIR/usr/bin/yt-dlp"
"$APPDIR/usr/bin/node" --version

cp -a "$ROOT/yucha" "$ROOT/languages" "$ROOT/LICENSE" "$ROOT/NOTICE" "$ROOT/README.md" \
    "$APPDIR/payload/"
cp -a "$ROOT/third_party/syncplay" "$ROOT/third_party/README.md" \
    "$APPDIR/payload/third_party/"
cp -a "$PACK/BUNDLED.txt" "$APPDIR/payload/BUNDLED.txt"
PYTHONNOUSERSITE=1 PYTHONPATH="$APPDIR/payload" "$APPDIR/usr/bin/yt-dlp" --version
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

def take(path, subdir=""):
    # Keep the name the loader asks for. ldd prints libavcodec.so.60, which
    # is a link to libavcodec.so.60.31.102. Copying only the real file leaves
    # the short name missing, and the player dies on startup.
    if not os.path.exists(path):
        return
    name = os.path.basename(path)
    if skipped(name):
        return
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        return
    real_name = os.path.basename(real)
    folder = dest / subdir
    folder.mkdir(parents=True, exist_ok=True)
    link = folder / name
    if not (folder / real_name).exists():
        shutil.copy2(real, folder / real_name)
    if real not in seen:
        seen.add(real)
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

# PipeWire loads its client modules and SPA factories with dlopen, outside ldd.
pipewire = next((line.split("=>", 1)[1].strip() for line in listed.splitlines()
                 if "libpipewire-0.3.so.0 " in line and "=>" in line), None)
if pipewire:
    base = Path(pipewire).resolve().parent
    config_dest = Path(os.environ["APPDIR"]) / "usr/share/pipewire"
    config_dest.mkdir(parents=True, exist_ok=True)
    modules = set()
    for name in ("client.conf", "client-rt.conf"):
        config = Path("/usr/share/pipewire") / name
        if name == "client-rt.conf" and not config.exists():
            continue
        shutil.copy2(config, config_dest / name)
        modules.update(re.findall(r"\bname\s*=\s*(libpipewire-module-[\w-]+)", config.read_text()))
    for name in modules:
        path = base / "pipewire-0.3" / (name + ".so")
        if not path.is_file():
            raise SystemExit("Missing PipeWire client module: " + str(path))
        take(str(path), "pipewire-0.3")
    for directory in ("support", "audioconvert", "videoconvert"):
        plugins = list((base / "spa-0.2" / directory).glob("*.so"))
        if not plugins:
            raise SystemExit("Missing SPA plugins: " + directory)
        for plugin in plugins:
            take(str(plugin), "spa-0.2/" + directory)

missing = []
out = subprocess.check_output(["readelf", "-d", str(entry)], text=True, errors="replace")
for name in re.findall(r"Shared library: \[([^\]]+)\]", out):
    if skipped(name):
        continue
    if not (dest / name).exists():
        missing.append(name)
if missing:
    raise SystemExit("libmpv is missing libraries:\n" + "\n".join(missing))
fallback = dest / "libva-fallback"
fallback.mkdir(exist_ok=True)
for pattern in ("libva.so*", "libva-drm.so*", "libva-x11.so*", "libva-wayland.so*"):
    for library in dest.glob(pattern):
        library.rename(fallback / library.name)
print("bundled libmpv from", src)
PY

mkdir -p "$APPDIR/usr/etc/fonts"
# Host configurations may use syntax newer than the bundled Fontconfig library.
cp -aL /etc/fonts/fonts.conf /etc/fonts/conf.d "$APPDIR/usr/etc/fonts/"
cp /usr/share/doc/fontconfig-config/copyright "$APPDIR/payload/LICENSE.fontconfig"

QT_QPA_PLATFORM=offscreen PYTHONNOUSERSITE=1 PYTHONPATH="$APPDIR/payload" \
    FONTCONFIG_PATH="$APPDIR/usr/etc/fonts" FONTCONFIG_FILE="$APPDIR/usr/etc/fonts/fonts.conf" \
    YUCHA_LIBMPV="$APPDIR/usr/lib/yucha/libmpv.so.2" \
    LD_LIBRARY_PATH="$APPDIR/usr/lib/yucha${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$APPDIR/python/bin/python3" -m unittest discover -s "$ROOT/tests" -v
python3 "$PACK/check-abi.py" "$APPDIR"

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
(
    cd "$DIST"
    ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" \
        -u 'gh-releases-zsync|yrmuq|yucha|latest|yucha-x86_64.AppImage.zsync' "$APPDIR" "$OUT"
)
test -s "$OUT.zsync"
python3 "$PACK/check-abi.py" "$OUT"
chmod +x "$OUT"
echo "wrote $OUT"
ls -lh "$OUT"

python3 "$PACK/verify.py" "$DIST" --write
