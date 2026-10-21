# yucha

<p align="center">
  <img src="assets/icon.png" alt="yucha" width="96">
</p>

<p align="center">
  <img src="assets/banner.png" alt="yucha — in active development" width="880">
</p>

> **Note:** `yucha` is in active beta development. Pre-release `x86_64` AppImages are available on the [Releases](https://github.com/yrmuq/yucha/releases) page.

**yucha** is a unified desktop media player for synchronized group watch parties. It embeds the [mpv](https://mpv.io/) playback engine (`libmpv`) and the [Syncplay](https://github.com/Syncplay/syncplay) synchronization client into a single native window with an integrated overlay UI. 

The primary goal of this integration is to provide a self-contained, zero-configuration solution tailored for atomic/immutable Linux distributions — eliminating the need to layer packages, configure external player paths, or manage separate client and player windows.

*`yucha` is an independent project and is not affiliated with or endorsed by `mpv` or `Syncplay`.*

## Features

- **Single-Window Architecture:** Hardware-accelerated video rendering via `libmpv` combined with `Syncplay` room state, playlist synchronization, and chat in one interface.
- **Atomic-Friendly Portability:** Distributed as a self-contained bundle that runs cleanly on immutable Linux systems without host modifications.
- **Overlay UI & OSD:** Auto-hiding playback controls, an overlay side panel for room/playlist management, and themed on-screen display (OSD) notifications for chat messages and user readiness states.
- **Customizable Appearance:** Built-in support for light/dark themes, custom accent colors, and scalable UI/OSD font sizes.
- **Persistent Configuration:** Automatically saves connection credentials and preferences to `~/.config/yucha/config.json` (`0600` permissions) for automatic reconnection on startup.

## Installation & Usage

### AppImage

Pre-built AppImages bundle Python, the `Syncplay` client, and `mpv`, requiring no external host dependencies. Download the latest `.AppImage` from the [Releases](https://github.com/yrmuq/yucha/releases) page.

For the easiest desktop integration and updates, use [Gear Lever](https://flathub.org/apps/it.mijorus.gearlever) to manage and launch the AppImage directly from your application menu.

Alternatively, make the file executable and run it from the terminal:

```sh
chmod +x yucha-x86_64.AppImage
./yucha-x86_64.AppImage

```

If your system lacks FUSE support, extract and run the image directly:

```sh
./yucha-x86_64.AppImage --appimage-extract-and-run

```

### Flatpak

Flatpak packaging is planned for the `v1.0` stable release.

## Controls & Shortcuts

| Input | Action |
| --- | --- |
| **Drag & Drop** | Add media files to the playlist (sorted alphabetically) |
| **Right Click** / `Space` | Toggle Play / Pause |
| **Double Click** | Toggle Fullscreen |
| `Left` / `Right` | Seek backward / forward (`5s`) |
| `Up` / `Down` / **Mouse Wheel** | Adjust volume (`10%` steps via keys, up to `130%` max) |
| `M` | Toggle Mute |
| **Left Click (Playlist)** | Play selected file from `0:00` |
| **Right Click (Playlist)** | Remove file from playlist |

## License & Attribution

`yucha` is free software distributed under the **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`). See [LICENSE](https://www.google.com/search?q=LICENSE) and [NOTICE](https://www.google.com/search?q=NOTICE) for full terms and third-party attributions. Bundled AppImage component licenses are listed in [packaging/appimage/BUNDLED.txt](https://www.google.com/search?q=packaging/appimage/BUNDLED.txt).

| Component | Upstream | License | Integration Details |
| --- | --- | --- | --- |
| Playback Engine | [mpv](https://github.com/mpv-player/mpv) | `GPL-2.0-or-later` | Unmodified source snapshot in `third_party/mpv`; links against `libmpv`. |
| Sync & Chat Client | [Syncplay](https://github.com/Syncplay/syncplay) | `Apache-2.0` | Unmodified snapshot in `third_party/syncplay` (including `ISC`/`BSD`/`MIT` submodules). |

Copyright (C) 2026 yrmuq.
