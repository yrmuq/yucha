<div align="center">
  <img src="assets/icon.png" alt="yucha" width="96">

  <h1>yucha</h1>

  [![License: GPL v3+](https://img.shields.io/badge/License-GPLv3%2B-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
  [![Latest Release](https://img.shields.io/github/v/release/yrmuq/yucha?include_prereleases)](https://github.com/yrmuq/yucha/releases)

  <p>
    A unified desktop media player for synchronized group watch parties that embeds the <code>mpv</code> playback engine (<code>libmpv</code>) and the <code>Syncplay</code> synchronization client into a single native window with an integrated overlay UI — providing a self-contained, zero-configuration experience tailored for atomic/immutable Linux distributions without host system modifications.
  </p>
</div>

---

> [!NOTE]
> **Active Beta Development:** `yucha` is currently in active beta development. Pre-release `x86_64` `AppImage` builds are available on the [Releases](https://github.com/yrmuq/yucha/releases) page.
>
> **After Updates:** `yucha` changes frequently, and saved settings may become outdated. If you experience problems after an update, try `Settings` → `Other` → `Reset`. This restores `Theme` and `Other` defaults, clears `Dev` overrides, and hides the `Dev` tab. Your `Room` connection is kept.
>
> **Reset Behavior:** Both `Reset` buttons apply and save immediately. You do not need to click `OK`, and `Cancel` does not undo a reset. `Dev` → `Reset` clears only `Dev` overrides, preserving ordinary settings.
>
> **Dev Settings:** Opening or enabling `Dev` does not save its default values. Only changed values are saved as overrides; returning a value to its default removes that override.
>
> **Independent Project:** `yucha` is an independent project and is not affiliated with or endorsed by `mpv` or `Syncplay`.

---

## Features

* **Single-Window Architecture:** Hardware-accelerated video rendering via `libmpv` combined with `Syncplay` room state, playlist synchronization, and chat in one unified interface.
* **Overlay UI & OSD:** Auto-hiding playback controls, an overlay side panel for room and playlist management, and themed on-screen display (`OSD`) notifications for chat messages and user readiness states.
* **Customizable Appearance:** Built-in support for light and dark themes, custom accent colors, and scalable UI/OSD font sizes.
* **Language:** The interface language comes from `languages/*.ini`.
* **Persistent Configuration:** Automatically saves connection credentials and user preferences to `~/.config/yucha/config.json` (`0600` permissions) for automatic reconnection on startup.
* **Playback Power:** The screen stays awake while a video is playing. Pause lets the system blank and sleep again.
* **Session Notifications:** When the window is in the background, the system reports a joined room, a person who enters, and a chat message.
* **Desktop Identity:** The window and the audio stream are named `yucha`, so the task bar and the volume mixer do not show `mpv`.

---

## Controls & Shortcuts

| Input | Action |
| :--- | :--- |
| `Drag & Drop` | Append media files to the playlist (sorted alphabetically), keeping the current video. The first file opens paused. |
| `Open With` | Add the opened video to the playlist. A window that is already open receives it. |
| `+` (Playlist) | Choose local files to add to the playlist. |
| Link icon (Playlist) | Enter a YouTube video URL and press `Enter` to queue it. For synchronized viewing, open the same video in each client. |
| Tracks icon / `HD` | Choose available audio and subtitle tracks, or set YouTube video quality locally. |
| `Right Click` / `Space` | Toggle Play / Pause. |
| `Double Click` | Toggle Fullscreen. |
| `Left Click` (left or right screen edge, fullscreen) | Toggle the side panel. |
| `Drag` (bottom edge of side panel) | Resize the chat height and save its maximum height. |
| `Drag` (side panel background, headings, or banner) | Move the panel when `Dev` → `Drag side panel` is enabled. |
| `Arrow` button (after moving the side panel) | Restore the panel to the side selected in `Other` → `Main panel`, respecting vertical centering if enabled. |
| `Left` / `Right` | Seek backward / forward (`5s`). |
| `Up` / `Down` / `Mouse Wheel` | Adjust volume (`10%` steps via keys, up to `130%` max). |
| `Enter` | Open the message field. Enter again sends the text and closes the field. |
| Physical `M` key (any keyboard layout) | Toggle Mute. |
| Physical `R` key (any keyboard layout) | Cycle repeat: current episode, whole playlist, off. Resets to off after restart. |
| `Mouse Wheel` (Playlist) | Scroll through episodes. |
| `Left Click` (Playlist) | Play selected file from `0:00`. |
| `Right Click` (Playlist) | Remove file from playlist. |

---

## Installation & Usage

### Architecture & Format Support

| Format | `x86_64` | `arm64` |
| :--- | :---: | :---: |
| `AppImage` | ✅ | ❌ |
| `Flatpak` | ❌ | ❌ |

### AppImage

Pre-built `AppImage` packages bundle `Python`, the `Syncplay` client, and `libmpv` copied from the build machine. No separate `mpv` program is included. Download the latest `.AppImage` from the [Releases](https://github.com/yrmuq/yucha/releases) page.

For seamless desktop integration and updates, use `Gear Lever` ([Flathub](https://flathub.org/apps/it.mijorus.gearlever)) to manage and launch the `AppImage` directly from your application menu. If the menu entry is from an older image, add it again so the file manager can open videos in `yucha`.

Alternatively, grant execution permissions and launch it from the terminal:

```sh
chmod +x yucha-x86_64.AppImage
./yucha-x86_64.AppImage

```

If the host system lacks `FUSE` support, extract and run the bundle directly:

```sh
./yucha-x86_64.AppImage --appimage-extract-and-run

```

### Flatpak

`Flatpak` packaging is planned for a future stable release.

---

## License & Attribution

### Repository License

`yucha` is free software distributed under `GPL-3.0-or-later`. See `LICENSE` and `NOTICE` for full terms and third-party attributions. Bundled `AppImage` component licenses are listed in `packaging/appimage/BUNDLED.txt`.

### Third-Party Components

| Component | Upstream | License | Integration Details |
| --- | --- | --- | --- |
| `libmpv` | [mpv-player/mpv](https://github.com/mpv-player/mpv) | `GPL-2.0-or-later` | Copied from the build machine. `third_party/mpv` is not built or shipped. |
| `Syncplay` | [Syncplay/syncplay](https://github.com/Syncplay/syncplay) | `Apache-2.0` | Unmodified source snapshot in `third_party/syncplay` (including `ISC`, `BSD`, and `MIT` submodules). |
| `yt-dlp` / `yt-dlp-ejs` | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp), [yt-dlp/ejs](https://github.com/yt-dlp/ejs) | `Unlicense` | Resolve YouTube streams and their available tracks. |
| `Node.js` | [nodejs/node](https://github.com/nodejs/node) | `MIT` and bundled notices | Runs the YouTube challenge solver. |

*Copyright (C) 2026 yrmuq.*
