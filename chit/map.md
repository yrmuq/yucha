# map

Read only the row the task needs. Do not read `third_party/` or `packaging/appimage/build/` unless the user asked to update that tree.

## Own code
- `yucha/app.py` — starts Qt, builds the client, calls `launch_player`.
- `yucha/window.py` — playlist, chat, seek, volume, settings. Large. Search a class. Do not read the whole file.
- `yucha/engine.py` — `Picture` draws the video through `libmpv`. This is the player.
- `yucha/session.py` — Syncplay client. `mpv --version`, then attach to the `libmpv` socket. Does not start a second player.
- `yucha/player_ui.py` — methods Syncplay calls. Forwards them. Does not draw.
- `yucha/bridge.py` — writes those calls to `events.jsonl` for the window.
- `yucha/system.py` — open a file in an already running window, sleep inhibit, notifications.
- `yucha/configstore.py` — saved host, room, and settings.
- `yucha/i18n.py` — reads `languages/*.ini`. A line is `id = English original = text shown`.
- `languages/` — one ini file per language. `English.ini` is the only file. The id is a number.
- `tests/test_guards.py`, `tests/test_system.py`, `tests/test_release.py`, `tests/test_color.py` — the only tests.

## Packaging
- `packaging/appimage/build.sh` — builds the image, copies Ubuntu `libmpv`, writes the `mpv --version` stub.
- `packaging/appimage/AppRun` — points `YUCHA_MPV` at that stub and `YUCHA_LIBMPV` at the copied library.
- `requirements.txt` — `PySide6_Essentials`, Twisted, `python-mpv`.
- `.github/workflows/appimage.yml` — builds a version tag. `X.Y.0` is a release. Any other `X.Y.Z` is a prerelease.
- `.github/workflows/release.yml` — a merge commit from `dev` into `main` raises Y and publishes.
- `.github/workflows/dev.yml` — manual draft from `dev`. It does not take a version number.
- `.github/workflows/deps.yml` — Dependabot prerelease on `deps`. It does not change `main`.
- `.github/workflows/pins.yml` — `appimagetool` pin, on the 28th. Same prerelease path, not `main`.
- `packaging/release/` — version bump and notes. Not the player.

## Libraries
- `libmpv` — decodes and draws. Ubuntu package copied at build time.
- `python-mpv` — the binding `engine.py` uses to call `libmpv`.
- `PySide6_Essentials` — the window. Used modules: QtCore, QtGui, QtWidgets, QtDBus, QtOpenGLWidgets.
- Twisted — the room connection in `session.py`.
- Syncplay — unmodified tree in `third_party/syncplay`. Imported pieces: `client`, `messages`, `constants`, `players/mpv.py`. Its GUI is not started.

## Do not open
- `third_party/mpv` — source snapshot. Not built, not shipped.
- `third_party/syncplay/syncplay/ui/` — Syncplay's window.
- `packaging/appimage/build/` — local build output.
