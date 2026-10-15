# yucha

<p align="center">
  <img src="assets/banner.png" alt="yucha — in active development" width="880">
</p>

> **In active development.** There is no 1.0 release. Alpha AppImages are on the releases page. The window is still plain on purpose. Flatpak waits until 1.0.

yucha is a media player for watching the same file at the same time as other people. Playback is [mpv](https://mpv.io/). Rooms, sync, and chat come from the [Syncplay](https://github.com/Syncplay/syncplay) client. Syncplay's own window is not used. The controls live in the mpv window: a button for the server, username, password, and room; the next launch reconnects with what was saved; chat sits on the side of the picture.

yucha is an independent project. It is not part of mpv and it is not part of Syncplay. Their names appear here only to identify the code it is built from.

## Run

You need Python 3 and an mpv binary. mpv is not compiled by this repository. Put it on `PATH`, or point `YUCHA_MPV` at it.

```sh
python3 -m pip install -r requirements.txt
python3 -m yucha
```

Drop a video on the window. The first launch opens the room panel, because nothing is saved yet. The login is written to `~/.config/yucha/config.json` (mode 0600). The next launch leaves the panel closed, connects with the saved server, username, password, and room, and draws **connected** at the bottom right of the picture. Chat lines show on the right, vertically centered, for five seconds, with no box behind them.

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

1. mpv is the only window. The Syncplay client runs beside it and keeps pause, seek, and position in sync. The protocol is the existing Syncplay client, not a rewrite.
2. A button in the bottom-right corner opens the room panel.
3. The panel slides out: server, port, username, password, room, and a message field.
4. No saved login: the panel opens by itself. Saved login: it stays closed, the client connects, **connected** stays at the bottom right, and a chat line appears for five seconds. Each new chat message is drawn the same way.
5. A gear in the panel opens settings: theme, chat color, chat size, and interface size.

The interface is a small set of Lua modules (`ui/mpv/`). A module registers a widget and an action. It does not own the mouse or the keyboard. Themes are two palettes. A new control is another module, not a rewrite of the player.

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
