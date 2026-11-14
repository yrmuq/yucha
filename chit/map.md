# map

Read only the row the task needs. Do not read `third_party/` or `packaging/appimage/build/` unless the user asked to update that tree.

## Own code
- `yucha/app.py` — starts Qt, builds the client, calls `launch_player`.
- `yucha/window.py` — playlist, chat, seek, volume, settings; `EdgeScroll` and `ScrollEdges` standardize external scrollbars. Large. Search a class. Do not read the whole file.
- `yucha/engine.py` — `Picture` draws the video through `libmpv`. This is the player.
- `yucha/youtube.py` — canonical YouTube URLs, track filtering, browser cookie import and private local storage, `yt-dlp` playback options.
- `yucha/ytdl.py` — yt-dlp entry point; keeps extractor cookie changes in memory so it cannot overwrite imported sessions.
- `yucha/session.py` — Syncplay client. `mpv --version`, then attach to the `libmpv` socket. Does not start a second player.
- `yucha/player_ui.py` — methods Syncplay calls. Forwards them. Does not draw.
- `yucha/bridge.py` — writes those calls to `events.jsonl` for the window.
- `yucha/system.py` — open a file in an already running window, sleep inhibit, notifications.
- `yucha/configstore.py` — saved host, room, and settings.
- `yucha/i18n.py` — reads `languages/*.ini`. A line is `id = English original = text shown`.
- `languages/` — English and Russian ini files. The id is a number.
- `tests/test_guards.py`, `tests/test_system.py`, `tests/test_release.py`, `tests/test_color.py` — config, system, release, and room checks.
- `tests/test_automation.py` — runtime-pin refresh and uploaded asset/channel verification.
- `tests/test_window.py` — Qt control, settings, and overlay regressions. Runs offscreen without mpv or a room server.

## Packaging
- `packaging/appimage/build.sh` — builds the image and `.zsync`, bundles `libmpv` and PipeWire client modules/config, stages a separate libva fallback, writes the `mpv --version` stub.
- `packaging/appimage/build-ci.sh` — all CI builds use Debian 13 with glibc 2.41; tests run with the bundled Python and libraries.
- `packaging/appimage/verify.py` — checks final update metadata, zsync contents and release checksums.
- `packaging/flatpak/build-test.sh` — optional standalone x86_64 test bundle; no stable Flatpak remote.
- `.github/actions/build/` — shared desktop build and dependency cache.
- `packaging/appimage/check-abi.py` — rejects ELF dependencies newer than glibc 2.41 before publication, including dependency prereleases.
- `packaging/appimage/AppRun` — selects host libva when the loader accepts it, otherwise the staged fallback; sets driver and bundled PipeWire paths, `YUCHA_MPV`, and `YUCHA_LIBMPV`.
- `requirements.txt` — `PySide6_Essentials`, Twisted, `python-mpv`, and `yt-dlp` with its default dependencies.
- `.github/workflows/appimage.yml` — manual package checks without publication.
- `.github/workflows/release.yml` — a merge from `dev` into `main` raises Y, publishes, then merges the published commit back into `dev`. Pending dependency changes block publication; successful publication refreshes the dev draft.
- `.github/workflows/dev.yml` — tests every dev push and updates the existing draft without a tag; a manual input optionally includes a standalone Flatpak test bundle.
- `.github/workflows/deps.yml` — Dependabot prerelease on `deps`. It does not change `main`.
- `.github/workflows/pins.yml` — Python, Node.js and appimagetool pins, weekly on Friday. Preserves accumulated changes on `deps`.
- `packaging/release/` — version allocation, notes, verified asset publication and safe synchronization of `main`, `dev` and `deps`. Not the player.

## Libraries
- `libmpv` — decodes and draws. Debian 13 package copied at build time.
- `python-mpv` — the binding `engine.py` uses to call `libmpv`.
- `yt-dlp` with `yt-dlp-ejs` and `Node.js` — resolve YouTube streams for `libmpv` and import browser cookies; `secretstorage` reads Chromium keys through Linux Secret Service. AppImage bundles the runtime and Python wheels.
- `PySide6_Essentials` — the window. Used modules: QtCore, QtGui, QtWidgets, QtDBus, QtOpenGLWidgets.
- Twisted — the room connection in `session.py`.
- Syncplay — unmodified tree in `third_party/syncplay`. Imported pieces: `client`, `messages`, `constants`, `players/mpv.py`. Its GUI is not started.

## Do not open
- `third_party/mpv` — source snapshot. Not built, not shipped.
- `third_party/syncplay/syncplay/ui/` — Syncplay's window.
- `packaging/appimage/build/` — local build output.
