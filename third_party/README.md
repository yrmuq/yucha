# Third-party snapshots

These trees are unmodified copies of upstream source. Do not edit them
in place. yucha's own code is `yucha/`.

| Directory | Upstream | Snapshot |
| --- | --- | --- |
| `mpv/` | https://github.com/mpv-player/mpv | version file `0.41.0` |
| `syncplay/` | https://github.com/Syncplay/syncplay | 1.7.7 |

`mpv/` is kept so the GPL combination has corresponding source. This
repository does not build that tree. The player starts an mpv binary
from `PATH` or from `YUCHA_MPV`.

`syncplay/` is the client library. yucha imports it and does not start
its Qt window. Its `LICENSE`, copyright headers, and per-file notices
(Apache-2.0, and ISC/BSD/MIT where a file says so) stay here.

See `../NOTICE` for the attribution text that has to travel with yucha.
