# lore

## Protected Areas
- Retain `.github/allocated-versions.txt` permanently so deleting a prerelease or tag cannot make its version number reusable.
- Treat `third_party/mpv` and `third_party/syncplay` as upstream snapshots; do not edit them without an explicit request to update those trees.
- Keep Qt limited to `PySide6_Essentials`; do not introduce add-ons, WebEngine, or PDF modules.

## Required Behavior
- Open the first added playlist item paused; later additions must leave current playback unchanged.
- In a connected room, Space marks an unready user ready without directly toggling playback; once ready, Space toggles playback.
- Preserve room credentials when resetting general settings; both Reset buttons save immediately and Cancel does not undo them.
- Save only explicit Dev overrides; opening Dev must not seed its defaults, and resetting Dev clears its overrides and advanced synchronization switches while preserving ordinary appearance settings.
- Preserve manual side-panel placement until its reset arrow is used, dragging is disabled, or the app restarts; movement must respect the bottom controls.
- Detach the same video widget into a separate frameless Picture-in-Picture window; keep the main window usable, preserve playback and room connection, and show its controls immediately on return.
- Keep scrollbars outside their content using the chat's shared EdgeScroll style, including newly created scroll areas.
- Do not publish Flatpak packages anywhere, including dev drafts, until the user explicitly requests it.

## Compatibility Workarounds
- Keep AppImage native dependencies compatible with glibc 2.41; the earlier newer baseline prevented startup on the test environment, and raising this floor requires an explicit compatibility decision.

## External Compatibility Constraints
- Syncplay must attach to the embedded libmpv socket; its mpv version probe must report the bundled library version without starting another player.
- Compare local room media by size and duration, and YouTube media by canonical watch URL; direct expiring stream URLs must not become shared file identities.
- Preserve the intentional ability to connect without TLS; if the certificate bundle cannot load, warn about the unencrypted connection and still connect.
