# lore

Reply in Russian, short and plain.
Repository: `https://github.com/yrmuq/yucha`. Commit as `yrmuq <76932153+yrmuq@users.noreply.github.com>`.
Own code is `yucha/`. Do not patch `third_party/syncplay` or `third_party/mpv`.
Picture: build-machine `libmpv`. No third-party `mpv` program. Syncplay `mpv --version` is a stub that prints that package's version.
Qt: `PySide6_Essentials` only. No add-ons, WebEngine, or PDF.
Playlist: the first drop does not start playback. A later drop may start only if the first episode is no longer selected.
TLS: do not refuse a server without TLS. If yucha's certificate bundle fails to load, warn that the connection is not encrypted and still connect.
Version: do not bump unless the user asks. To keep the current version is to keep that number. Current: `0.3.1`.
