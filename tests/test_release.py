# Copyright (C) 2026 yrmuq
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib.util
import os
import shutil
import subprocess
import tempfile
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
    def test_published_release_sync_preserves_dev_and_stops_on_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            work.mkdir()
            remote = root / "origin.git"

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=work, text=True,
                                               stderr=subprocess.STDOUT).strip()

            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            git("config", "user.name", "Release Test")
            git("config", "user.email", "release@example.test")
            (work / "packaging/release").mkdir(parents=True)
            shutil.copy(NOTES.parent / "sync-dev.sh", work / "packaging/release/sync-dev.sh")
            version = work / "version"
            version.write_text("0.6.0\n")
            git("add", ".")
            git("commit", "-m", "Add initial release.")
            git("branch", "dev")
            git("tag", "dev")
            git("remote", "add", "origin", str(remote))
            git("push", "origin", "main", "refs/heads/dev", "refs/tags/dev")
            version.write_text("0.7.0\n")
            git("commit", "-am", "Version 0.7.0.")
            published = git("rev-parse", "HEAD")
            git("push", "origin", "main")
            git("checkout", "dev")
            (work / "feature").write_text("unreleased work\n")
            git("add", "feature")
            git("commit", "-m", "Add the next feature.", "-m", "[draft]")
            pending = git("rev-parse", "HEAD")
            git("push", "origin", "HEAD:refs/heads/dev")
            git("checkout", "--detach", published)
            subprocess.check_output(["bash", "packaging/release/sync-dev.sh"], cwd=work,
                                    text=True, stderr=subprocess.STDOUT)
            synced = git("rev-parse", "origin/dev")
            self.assertEqual(git("show", "origin/dev:version"), "0.7.0")
            self.assertEqual(git("show", "origin/dev:feature"), "unreleased work")
            self.assertEqual(git("rev-parse", "HEAD^1"), pending)
            self.assertEqual(git("rev-parse", "HEAD^2"), published)
            self.assertNotIn("[draft]", git("log", "-1", "--format=%B"))
            self.assertEqual(git("ls-remote", "origin", "refs/heads/main").split()[0], published)

            git("checkout", "--detach", published)
            subprocess.check_output(["bash", "packaging/release/sync-dev.sh"], cwd=work,
                                    text=True, stderr=subprocess.STDOUT)
            self.assertEqual(git("rev-parse", "origin/dev"), synced)

            git("checkout", "--detach", synced)
            version.write_text("custom dev value\n")
            git("commit", "-am", "Change the dev setting.")
            conflicted_dev = git("rev-parse", "HEAD")
            git("push", "origin", "HEAD:refs/heads/dev")
            git("checkout", "main")
            version.write_text("0.8.0\n")
            git("commit", "-am", "Version 0.8.0.")
            result = subprocess.run(["bash", "packaging/release/sync-dev.sh"], cwd=work,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(git("ls-remote", "origin", "refs/heads/dev").split()[0], conflicted_dev)

    def test_refresh_keeps_version_and_the_next_merge_bumps_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            work.mkdir()
            remote = root / "origin.git"
            output = root / "outputs"
            env = {**os.environ, "GITHUB_OUTPUT": str(output)}

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=work, env=env,
                                               text=True, stderr=subprocess.STDOUT).strip()

            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            git("config", "user.name", "Release Test")
            git("config", "user.email", "release@example.test")
            for folder in ("packaging/release", "chit", "yucha"):
                (work / folder).mkdir(parents=True)
            for name in ("cut.sh", "bump.py", "notes.py"):
                shutil.copy(NOTES.parent / name, work / "packaging/release" / name)
            init = work / "yucha/__init__.py"
            init.write_text('__version__ = "0.6.0"\n')
            (work / "chit/lore.md").write_text('Current: `0.6.0`.\n')
            git("add", ".")
            git("commit", "-m", "Add initial release.")
            git("tag", "-a", "v0.6.0", "-m", "Initial release.")
            original_tag = git("rev-parse", "refs/tags/v0.6.0")
            git("remote", "add", "origin", str(remote))
            git("checkout", "-b", "dev")
            (work / "feature").write_text("first change\n")
            git("add", "feature")
            git("commit", "-m", "Fix the settings.")
            git("push", "origin", "dev")
            git("checkout", "main")
            git("merge", "--no-ff", "dev", "-m", "Merge branch 'dev'", "-m", "[refresh-release]")
            merge = git("rev-parse", "HEAD")
            result = subprocess.check_output(["bash", "packaging/release/cut.sh"], cwd=work,
                                             env=env, text=True, stderr=subprocess.STDOUT)
            self.assertEqual(result.splitlines()[-1], "0.6.0")
            self.assertEqual(git("rev-parse", "HEAD"), merge)
            self.assertEqual(git("rev-parse", "v0.6.0^{}"), merge)
            self.assertIn('"0.6.0"', init.read_text())
            self.assertIn("refresh=true", output.read_text())
            self.assertIn("previous_tag=" + original_tag, output.read_text())
            refreshed_tag = git("rev-parse", "refs/tags/v0.6.0")

            git("checkout", "dev")
            (work / "feature").write_text("second change\n")
            git("add", "feature")
            git("commit", "-m", "Fix the next thing.")
            git("push", "origin", "dev")
            git("checkout", "main")
            git("merge", "--no-ff", "dev", "-m", "Merge branch 'dev'")
            output.write_text("")
            result = subprocess.check_output(["bash", "packaging/release/cut.sh"], cwd=work,
                                             env=env, text=True, stderr=subprocess.STDOUT)
            self.assertEqual(result.splitlines()[-1], "0.7.0")
            self.assertIn('"0.7.0"', init.read_text())
            self.assertEqual(git("rev-parse", "v0.7.0^{}"), git("rev-parse", "HEAD"))
            self.assertEqual(git("rev-parse", "refs/tags/v0.6.0"), refreshed_tag)
            self.assertEqual(output.read_text(), "")

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
