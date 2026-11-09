# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run yt-dlp with a per-process, in-memory copy of the imported session."""

import yt_dlp


class PlaybackYDL(yt_dlp.YoutubeDL):
    def save_cookies(self):
        # A finishing extractor must not restore removed cookies or overwrite a new import.
        pass


def main():
    yt_dlp.YoutubeDL = PlaybackYDL
    yt_dlp.main()


if __name__ == "__main__":
    main()
