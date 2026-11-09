# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from yucha.engine import Picture, _hardware_decoding


class EngineTests(unittest.TestCase):
    def test_hardware_decoding_follows_the_active_rendering_gpu(self):
        for vendor, renderer, expected in (
            ("AMD", "AMD Radeon RX 7800 XT", ("vaapi,vaapi-copy", "vaapi")),
            ("Mesa/X.org", "AMD Radeon Graphics", ("vaapi,vaapi-copy", "vaapi")),
            ("Intel", "Mesa Intel Iris Xe", ("vaapi,vaapi-copy", "vaapi")),
            ("NVIDIA Corporation", "NVIDIA GeForce RTX 4060", ("nvdec,nvdec-copy", "cuda")),
            ("Mesa", "llvmpipe (LLVM 19.1.7)", ("no", "no")),
            (None, None, ("auto-safe", "auto")),
        ):
            with self.subTest(vendor=vendor, renderer=renderer):
                self.assertEqual(_hardware_decoding(vendor, renderer), expected)

    def test_playback_failure_reaches_stderr_with_terminal_disabled(self):
        with tempfile.TemporaryDirectory() as runtime, redirect_stderr(io.StringIO()) as output, \
                patch.dict(os.environ, {"XDG_CONFIG_HOME": runtime}):
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
