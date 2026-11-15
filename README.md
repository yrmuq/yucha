<div align="center">
  <img src="assets/icon.png" alt="yucha" width="96">
  <h1>yucha</h1>

  [![License: GPL v3+](https://img.shields.io/badge/License-GPLv3%2B-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
  [![Latest stable release](https://img.shields.io/github/v/release/yrmuq/yucha)](https://github.com/yrmuq/yucha/releases/latest)
</div>

---

> [!NOTE]
> yucha is under active development. Behavior can change, bugs may occur, and saved settings may become outdated. `Settings` → `General` → `Reset` restores appearance and general defaults while preserving the `Room` connection. Both Reset buttons save immediately; `Cancel` does not undo a reset.

---

> [!WARNING]
> yucha incorporates an unmodified `Syncplay` client and bundles `libmpv`. Redistribution must retain the applicable license and attribution notices and provide corresponding source where required by the GPL. See the [third-party notices](NOTICE).

---

yucha is a Linux media player for synchronized viewing of local files and YouTube videos. It embeds `libmpv` for playback and the `Syncplay` client for rooms, playlists, and chat, keeping playback and room controls in one Qt window.

![yucha application and General settings](assets/screenshot.webp)

---

## Features

- Local video and YouTube playback with synchronized rooms on public or self-hosted Syncplay servers.
- Shared playlist, chat, readiness states, and playback synchronization in one window.
- YouTube quality selection from `480p`, audio-language selection, and subtitles in the system language and English.
- Browser-session import for YouTube; imported cookies are stored locally and can be removed.
- Buffered YouTube ranges displayed in gray on the seek bar.
- Frameless Picture-in-Picture in a separate window with the same playback session, activated by a shortcut or minimizing the player.
- Persistent appearance settings, system/light/dark themes, and system or manual interface language selection.
- Background notifications and prevention of automatic sleep during playback.

---

<details>
<summary><h2>Controls & Shortcuts</h2></summary>

| Input | Action |
| --- | --- |
| `Drag & Drop` / `Open With` / playlist `+` | Add local media. The first item opens paused; later additions leave playback unchanged. |
| Playlist link icon | Add a YouTube URL. Each room participant needs the same video. |
| `Space` | In a connected room, mark yourself ready first; once ready, toggle playback. Outside a room, toggle playback. |
| `Right Click` on main video / playback button | Toggle playback. |
| `Right Click` on Picture-in-Picture | Open the KDE window menu, including `Keep Above`. |
| Physical `P` key / minimize with media open | Move the video into a separate frameless window. Drag the video to move it; drag any edge or corner to resize it. Controls appear on hover and remain visible for three seconds. Press `P`, double-click the video, use the up-arrow button, or close the small window to return. Playback and the room connection continue. |
| Click / drag the PiP progress thumb | Seek to that position. |
| `Double Click` | Toggle fullscreen outside Picture-in-Picture. |
| `Left` / `Right` | Seek backward / forward by 5 seconds. |
| `Up` / `Down` / wheel over video | Adjust volume. |
| Physical `M` / `R` keys | Toggle mute / cycle repeat: episode, playlist, off. |
| `Enter` | Open chat; send the message on the next press. |
| Tracks icon / quality label | Choose audio language, subtitles, or YouTube quality. |
| `Settings` → `General` → `YouTube quality` | Set the initial quality from `480p` to `4K`; default `720p`. New videos use the best available quality up to this limit. Manual quality selection applies to the current video. |
| `Settings` → `Room` → `Connect YouTube` | Import cookies from a detected browser or selected profile; remove the imported copy with `Remove session`. |
| `Left Click` / `Right Click` on a playlist item | Play from the beginning / remove the item. |
| Fullscreen screen edge | Toggle the side panel. |

Player shortcuts do not interrupt text entry. Picture-in-Picture requests an always-on-top window; on native Wayland, use the window manager's `Keep Above` command if it does not support this request. YouTube session import does not verify access to a particular video. If YouTube reports that the saved session has expired or was rejected, import cookies again through `Connect YouTube`. Imported cookies and saved configuration use `0600` permissions.

Update controls are in `About`. Click its logo five times to show or hide `Dev`, which contains `Forward if behind` and `Slow if ahead`. `Dev` stores explicit overrides only; its `Reset` clears those overrides and restores the advanced synchronization switches without changing ordinary appearance settings.

</details>

---

## Installation & Usage

### Architecture & Format Support

| Format | `x86_64` | `arm64` |
| --- | :---: | :---: |
| `AppImage` | ✅ | ❌ |
| `Flatpak` | ❌ | ❌ |

### Release Scheme

Stable releases use `X.Y.0`. Versions `X.Y.Z` with `Z > 0` are automatic dependency-update prereleases. Development builds update the private dev draft without changing the version.

Choose the [latest stable release](https://github.com/yrmuq/yucha/releases/latest) or browse [all releases](https://github.com/yrmuq/yucha/releases).

### AppImage

Requires `x86_64` Linux with `glibc 2.41` or newer and working desktop graphics drivers. The package includes the Python runtime and playback libraries; no separate `mpv` program is required.

Download the `.AppImage` from the [latest stable release](https://github.com/yrmuq/yucha/releases/latest), or select another build from [all releases](https://github.com/yrmuq/yucha/releases). Use [Gear Lever](https://flathub.org/apps/it.mijorus.gearlever) for installation, desktop integration, and updates.

The `.AppImage` embeds the GitHub update source for the latest stable release. Its accompanying `.zsync` enables efficient delta updates. Download or import only the `.AppImage`; do not open `.zsync` manually. `SHA256SUMS` contains the package checksums. Private drafts are outside the public stable update channel.

<details>
<summary>Terminal launch and systems without FUSE</summary>

```sh
chmod +x yucha-x86_64.AppImage
./yucha-x86_64.AppImage
```

If FUSE is unavailable:

```sh
./yucha-x86_64.AppImage --appimage-extract-and-run
```

The file chooser uses `xdg-desktop-portal` through Qt, with Qt's own chooser as a fallback when the portal is unavailable.

</details>

### Flatpak

Flatpak distribution is planned. Flatpak packages are not published in stable releases or development drafts.

---

## License & Attribution

yucha is distributed under `GPL-3.0-or-later`. See the [license](LICENSE), [third-party notices](NOTICE), and [bundled component information](packaging/appimage/BUNDLED.txt).

| Component | Upstream | License | Integration Details |
| --- | --- | --- | --- |
| `libmpv` | [mpv-player/mpv](https://github.com/mpv-player/mpv) | `GPL-2.0-or-later` | Copied from the build machine. `third_party/mpv` is not built or shipped. |
| `Syncplay` | [Syncplay/syncplay](https://github.com/Syncplay/syncplay) | `Apache-2.0` | Unmodified source snapshot in `third_party/syncplay` (including `ISC`, `BSD`, and `MIT` submodules). |
| `yt-dlp` / `yt-dlp-ejs` | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp), [yt-dlp/ejs](https://github.com/yt-dlp/ejs) | `Unlicense` | Resolve YouTube streams and their available tracks. |
| `CPython` | [python/cpython](https://github.com/python/cpython) | `PSF-2.0` | Bundled interpreter from python-build-standalone. |
| `PySide6_Essentials` | [pyside/pyside-setup](https://github.com/pyside/pyside-setup) | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | Qt widgets and embedded OpenGL rendering. |
| `python-mpv` | [jaseg/python-mpv](https://github.com/jaseg/python-mpv) | `GPL-2.0-or-later OR LGPL-2.1-or-later` | Python binding to libmpv. |
| `Twisted` | [twisted/twisted](https://github.com/twisted/twisted) | `MIT` | Syncplay networking and TLS. |
| `Node.js` | [nodejs/node](https://github.com/nodejs/node) | `MIT` and bundled notices | Runs the YouTube challenge solver. |

*Copyright (C) 2026 yrmuq.*
