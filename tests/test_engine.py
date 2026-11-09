# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from yucha.engine import Picture, _hardware_decoding


class EngineTests(unittest.TestCase):
    def test_cdn_denial_is_retried_without_leaving_video_missing_or_retrying_forever(self):
        video = b"YUV4MPEG2 W2 H2 F25:1 Ip A1:1 C420jpeg\n" + (b"FRAME\n" + bytes([128]) * 6) * 50
        for retry, permanent, expected_requests in ((False, False, 1), (True, False, 2), (True, True, 3)):
            with self.subTest(retry=retry, permanent=permanent):
                requests = []

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *args):
                        pass

                    def do_GET(self):
                        requests.append(self.path)
                        denied = permanent or len(requests) == 1
                        body = b"" if denied else video
                        self.send_response(403 if denied else 200)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    with tempfile.TemporaryDirectory() as runtime, \
                            patch.dict(os.environ, {"XDG_CONFIG_HOME": runtime}):
                        engine = SimpleNamespace(ipc_path=Path(runtime) / "mpv.sock")
                        Picture._start_engine(engine)
                        player = engine.mpv
                        try:
                            player.vo, player.ao, player.hwdec = "null", "null", "no"
                            player.ytdl, player.pause = False, True
                            if not retry:
                                player.stream_lavf_o = {}
                            settled = threading.Event()
                            frames = []

                            @player.property_observer("video-out-params")
                            def on_video(_name, params):
                                if params:
                                    frames.append(params)
                                    settled.set()

                            @player.event_callback("end-file")
                            def on_end(_event):
                                settled.set()

                            player.play("http://127.0.0.1:{}/video.y4m".format(server.server_port))
                            self.assertTrue(settled.wait(5), "HTTP retries did not finish")
                            self.assertEqual(bool(frames), retry and not permanent)
                            self.assertEqual(requests, ["/video.y4m"] * expected_requests)
                        finally:
                            player.terminate()
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join()

    def test_youtube_selects_high_resolution_without_an_external_ffmpeg(self):
        from yt_dlp import YoutubeDL

        with tempfile.TemporaryDirectory() as runtime, patch.dict(os.environ, {"XDG_CONFIG_HOME": runtime}):
            engine = SimpleNamespace(ipc_path=Path(runtime) / "mpv.sock")
            Picture._start_engine(engine)
            try:
                info = {"id": "test", "title": "Test", "formats": [
                    {"format_id": "18", "url": "https://example.test/360", "ext": "mp4",
                     "vcodec": "avc1", "acodec": "mp4a", "height": 360},
                    {"format_id": "140", "url": "https://example.test/audio", "ext": "m4a",
                     "vcodec": "none", "acodec": "mp4a", "abr": 128},
                    {"format_id": "399", "url": "https://example.test/1080", "ext": "mp4",
                     "vcodec": "av01", "acodec": "none", "height": 1080},
                ]}
                with patch("yt_dlp.YoutubeDL.FFmpegMergerPP") as merger, \
                        YoutubeDL({"format": engine.mpv.ytdl_format, "quiet": True}, auto_init=False) as downloader:
                    merger.return_value.available = False
                    result = downloader.process_ie_result(info, download=False)
                self.assertEqual([track["format_id"] for track in result["requested_formats"]], ["399", "140"])
            finally:
                engine.mpv.terminate()

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
