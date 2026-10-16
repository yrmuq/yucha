# yucha

<p align="center">
  <img src="assets/banner.png" alt="yucha — in active development" width="880">
</p>

> **In active development.** There is no 1.0 release. Alpha AppImages are on the releases page. Flatpak waits until 1.0.

yucha is a media player for watching the same file at the same time as other people. Playback is [mpv](https://mpv.io/)'s engine, inside this window. Rooms, sync, and chat come from the [Syncplay](https://github.com/Syncplay/syncplay) client. Neither program's own window is used. The fields and buttons are ordinary ones. The picture is a frame drawn in the window, not a second window.

yucha is an independent project. It is not part of mpv and it is not part of Syncplay. Their names appear here only to identify the code it is built from.

## Run

You need Python 3, the mpv library (libmpv), and an mpv binary on `PATH` for the version check. Point `YUCHA_MPV` at the binary if it is not on `PATH`. The AppImage already contains both.

```sh
python3 -m pip install -r requirements.txt
python3 -m yucha
```

Drop a video on the picture. It starts at 0:00. Right click pauses and resumes. Space does the same when the picture is focused. Double click toggles fullscreen. The wheel changes the volume and shows the level for two seconds. A click on the time bar jumps to that moment. The first launch opens the room panel, because nothing is saved yet. The login is written to `~/.config/yucha/config.json` (mode 0600). The next launch leaves the panel closed and connects with the saved server, username, password, and room. The panel shows Room connected, Not configured, or Error connecting. A click on that banner opens the connection fields. The gear beside it opens the theme, colors, and sizes. Chat lines, and the notices Syncplay itself would show, stay in the panel. Chat lines also show on the picture for five seconds, in a fixed column. Each message has its own theme-colored box, and a long line wraps inside it. The name is in the accent color. Dropped files are listed between the banner and the chat, sorted by name. The one playing is marked with the accent color. A left click plays that file from the start. A right click removes the row. The next file also starts from the beginning. If the list has one file, Play starts it again from 0:00. A person who is not ready stays at the top right of the picture with a red dot. A person who is ready shows with a green dot for two seconds.

## AppImage

Alpha builds for x86_64 are on the [releases page](https://github.com/yrmuq/yucha/releases). Each version stays there. The image carries its own Python, the Syncplay client, and an mpv 0.41.0 binary, so the machine does not need those installed. What is bundled, and under which license, is in [packaging/appimage/BUNDLED.txt](packaging/appimage/BUNDLED.txt).

```sh
chmod +x yucha-x86_64.AppImage
./yucha-x86_64.AppImage
```

On Bazzite, Gear Lever (from Bazaar) can add it to the menu. If the file refuses to start because FUSE is missing, run:

```sh
./yucha-x86_64.AppImage --appimage-extract-and-run
```

A version tag `vX.Y.Z` makes GitHub build the image and attach it to that release. The release title is `yucha X.Y.Z alpha`. To rebuild the same image on your own machine, run `packaging/appimage/build.sh`. It downloads CPython, the mpv AppImage it wraps, and appimagetool. The result is `dist/yucha-x86_64.AppImage`, which is not committed.

## What is on the window

1. One window. mpv's engine draws the picture inside it and does not open a window of its own. The Syncplay client keeps pause, seek, and position in sync. The protocol is the existing Syncplay client, not a rewrite.
2. The room button at the right end of the playback bar opens the room panel. The panel sits on top of the picture and stops above the bar. The picture is not resized. A click on the banner opens the connection fields. The gear opens the appearance settings.
3. The bar sits on top of the picture. It has play, the time bar, loop, chat, and room, as icons. The chat button opens a message field above the bar. The bar itself does not move, and it stays while that field is open. A failed connection shows Reconnect under the banner. The bar uses the theme and hides after 3 seconds without the mouse, unless the room panel or the message field is open. Loop repeats the current file while the button is on. Right click and Space pause and resume. Double click toggles fullscreen. The wheel changes the volume. A click on the time bar jumps to that moment.
4. No saved login: the panel opens by itself. Saved login: it stays closed and the client connects.
5. The gear in the panel sets the theme, chat color, accent color, chat size, and interface size. Text on the picture follows the theme: dark on a light theme, light on a dark theme.

## Status

This is the first working stage. The layout is functional, not finished. Playlist controls, a file dialog, and a more careful look are not in this tree yet. Flatpak is planned for 1.0, not before.

Saved passwords are stored the same way Syncplay stores them: plaintext in the user config file, readable only by that user. Do not commit that file.

## License

yucha is free software under the **GNU General Public License v3.0 or any later version**. The license text is [LICENSE](LICENSE). That file is the Free Software Foundation's GPL v3, copied verbatim. The GPL itself says the license document must not be changed, so attributions are not pasted into it. They are in [NOTICE](NOTICE). Keep both files with any copy of the program.

Copyright (C) 2026 yrmuq.

| Piece | Upstream | Its license | What yucha does about it |
| --- | --- | --- | --- |
| Playback | [mpv](https://github.com/mpv-player/mpv) | GPL-2.0-or-later | "Or later" is what allows the combination to be shipped as GPL-3.0-or-later. An unmodified source snapshot is in `third_party/mpv`. The program runs an mpv binary you supply. The result is not called mpv. |
| Rooms, sync, chat, playlist | [Syncplay](https://github.com/Syncplay/syncplay) | Apache-2.0 | An unmodified snapshot is in `third_party/syncplay`. yucha does not patch those files. It runs the client and does not open Syncplay's window. The Apache license, copyright headers, and Syncplay's own notices stay with that tree. The result is not called Syncplay. |
| Individual Syncplay files, including `syncplayintf.lua` | Syncplay contributors and others | ISC, BSD, MIT, as each file says | Those notices stay on the files. They are compatible with GPL-3.0 and are not relicensed by being carried inside yucha. |

The combined program is distributed under GPL-3.0-or-later. Including Apache-2.0 code in that combination does not erase the Apache notices. Details are in [NOTICE](NOTICE).
