# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib.util
import unittest
from pathlib import Path

NOTES = Path(__file__).resolve().parents[1] / "packaging" / "release" / "notes.py"
SPEC = importlib.util.spec_from_file_location("release_notes", NOTES)
notes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notes)


DIFF = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,2 @@
-twisted[tls]>=22.4.0
+twisted[tls]>=24.3.0
-PySide6_Essentials>=6.6,<6.13
+PySide6_Essentials>=6.7,<6.13
diff --git a/.github/workflows/appimage.yml b/.github/workflows/appimage.yml
--- a/.github/workflows/appimage.yml
+++ b/.github/workflows/appimage.yml
@@ -1 +1 @@
-        uses: actions/checkout@v4
+        uses: actions/checkout@v5
diff --git a/packaging/appimage/build.sh b/packaging/appimage/build.sh
--- a/packaging/appimage/build.sh
+++ b/packaging/appimage/build.sh
@@ -1 +1 @@
-TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
+TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.2/appimagetool-x86_64.AppImage"
"""


class ReleaseNotes(unittest.TestCase):
    def test_dependency_notes_name_the_old_and_new_versions(self):
        self.assertEqual(
            notes.deps_notes(DIFF),
            "\n".join(
                [
                    "Dependency updates.",
                    "- `PySide6_Essentials` >=6.6,<6.13 -> >=6.7,<6.13",
                    "- `actions/checkout` v4 -> v5",
                    "- `appimagetool` 1.9.1 -> 1.9.2",
                    "- `twisted[tls]` >=22.4.0 -> >=24.3.0",
                    "",
                ]
            ),
        )

    def test_commit_notes_skip_merges_and_version_bumps(self):
        text = notes.commit_notes(
            [
                "Add a language file.",
                "Fix the seek bar",
                "Merge branch 'dev' into main",
                "Version 0.4.0.",
                "Move the pin.",
            ]
        )
        self.assertEqual(
            text,
            "\n".join(
                [
                    "Added",
                    "- Add a language file.",
                    "",
                    "Changed",
                    "- Move the pin.",
                    "",
                    "Fixed",
                    "- Fix the seek bar.",
                    "",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
