# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from yucha.engine import Picture


class EngineTests(unittest.TestCase):
    def test_playback_failure_reaches_stderr_with_terminal_disabled(self):
        with tempfile.TemporaryDirectory() as runtime, redirect_stderr(io.StringIO()) as output:
            engine = SimpleNamespace(ipc_path=Path(runtime) / "mpv.sock")
            Picture._start_engine(engine)
            try:
                ended = threading.Event()

                @engine.mpv.event_callback("end-file")
                def on_end(_event):
                    ended.set()

                engine.mpv.play(str(Path(runtime) / "missing.mp4"))
                self.assertTrue(ended.wait(5), "libmpv did not finish the failed load")
            finally:
                engine.mpv.terminate()
            self.assertIn("libmpv [", output.getvalue())
            self.assertIn("Failed to open", output.getvalue())
            self.assertIn("missing.mp4", output.getvalue())
