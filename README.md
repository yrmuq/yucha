# yucha

<p align="center">
  <img src="assets/banner.svg" alt="yucha — in active development" width="880">
</p>

> **In active development.** There is no release and nothing here is ready to install. The player is still being built.

yucha is a media player for watching the same file at the same time as other people. Playback is [mpv](https://mpv.io/). Rooms, sync, and chat come from the [Syncplay](https://github.com/Syncplay/syncplay) client, with Syncplay's own window left out, so the controls live in the player: a button for the server, username, password, and room; the next launch reconnects with what was saved; chat sits on the side of the picture.

This repository does not contain that program yet.

yucha is an independent project. It is not part of mpv and it is not part of Syncplay. Their names appear here only to identify the code it is built from.

## Status

The license and this document are in place. Application code is not.

## License

yucha is free software under the **GNU General Public License v3.0 or any later version**. The license text is [LICENSE](LICENSE). That file is the Free Software Foundation's GPL v3, copied verbatim. The GPL itself says the license document must not be changed, so attributions are not pasted into it. They are in [NOTICE](NOTICE). Keep both files with any copy of the program.

Copyright (C) 2026 yrmuq.

| Piece | Upstream | Its license | What yucha does about it |
| --- | --- | --- | --- |
| Playback | [mpv](https://github.com/mpv-player/mpv) | GPL-2.0-or-later | "Or later" is what allows the combination to be shipped as GPL-3.0-or-later. Corresponding mpv source stays available. The result is not called mpv. |
| Rooms, sync, chat, playlist | [Syncplay](https://github.com/Syncplay/syncplay) | Apache-2.0 | Apache-2.0 code may be included in a GPL-3.0 program. The Apache license text, copyright headers, and Syncplay's own third-party notices stay with those files, and the changes are stated. The result is not called Syncplay. |
| Individual Syncplay files, including `syncplayintf.lua` | Syncplay contributors and others | ISC, BSD, MIT, as each file says | Those notices stay on the files. They are compatible with GPL-3.0 and are not relicensed by being carried inside yucha. |

The combined program is distributed under GPL-3.0-or-later. Including Apache-2.0 code in that combination does not erase the Apache notices. Details and the required wording are in [NOTICE](NOTICE).
