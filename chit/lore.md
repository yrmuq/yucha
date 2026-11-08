# lore

Reply in Russian, short and plain.
The default delivery for requested code changes is a tested draft from dev.
After successful publication, CI merges the published release commit back into `dev` without requesting another draft build. A conflict or rejected push stops synchronization without overwriting `dev`.
If a user approval is needed, notify in Mattermost immediately so the user can reopen the chat and approve.
Repository: `https://github.com/yrmuq/yucha`. Commit as `yrmuq <76932153+yrmuq@users.noreply.github.com>`.
Own code is `yucha/`. Do not patch `third_party/syncplay` or `third_party/mpv`.
Picture: build-machine `libmpv`. No third-party `mpv` program. Syncplay `mpv --version` is a stub that prints that package's version.
Qt: `PySide6_Essentials` only. No add-ons, WebEngine, or PDF.
Playlist: the first drop opens the file paused and does not start playback. Later drops only append files and leave the current episode playing or paused as it was.
Room files: compare size and duration, not the name. A person with neither is shown as no file selected.
TLS: do not refuse a server without TLS. If yucha's certificate bundle fails to load, warn that the connection is not encrypted and still connect.
Version: X.Y.Z. Work goes on `dev`, not on `main`. Merging `dev` into `main` with a merge commit raises Y and sets Z to 0, unless that merge explicitly contains `[refresh-release]` to replace the current release once. That is a normal release, not a prerelease. A squash does not release. Dependabot publishes `X.Y.1`, `X.Y.2` from `main` plus dependency updates, and deletes the previous prerelease of that kind. Merge `deps` into `dev` by hand. Do not bump the number on a `dev` commit. Current: `0.7.0`.
Dev stores only explicit overrides; opening Dev does not seed its defaults. Both Reset buttons save immediately and survive Cancel. Other Reset clears appearance and Dev, including Dev visibility, but preserves Room; Dev Reset clears only Dev overrides and inherits ordinary appearance settings.
Side panel: bottom-edge resizing saves the Dev chat-height override; its default is 340 px. Dev can center the panel vertically or allow dragging; manual placement takes priority until the arrow resets it, dragging is disabled, or the app restarts. Panel movement reserves the existing gap above the bottom bar.
