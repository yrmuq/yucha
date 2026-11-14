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

    def test_release_requires_tested_dependencies_and_preserves_published_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            remote = Path(tmp) / "origin.git"
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=work, text=True,
                                               stderr=subprocess.STDOUT).strip()
            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            git("config", "user.name", "Release Test")
            git("config", "user.email", "release@example.test")
            (work / "packaging/release").mkdir(parents=True)
            (work / "yucha").mkdir()
            for name in ("cut.sh", "bump.py", "notes.py"):
                shutil.copy(NOTES.parent / name, work / "packaging/release" / name)
            init = work / "yucha/__init__.py"
            init.write_text('__version__ = "0.6.0"\n')
            git("add", ".")
            git("commit", "-m", "Add initial release")
            git("tag", "-a", "v0.6.0", "-m", "Initial release")
            original = git("rev-parse", "v0.6.0")
            git("remote", "add", "origin", str(remote))
            git("branch", "deps")
            git("branch", "dev")
            git("push", "origin", "main", "dev", "deps", "--tags")
            git("checkout", "dev")
            (work / "feature").write_text("first change\n")
            git("add", "feature")
            git("commit", "-m", "Fix the settings")
            git("push", "origin", "dev")
            git("checkout", "main")
            git("merge", "--no-ff", "dev", "-m", "Merge branch 'dev'")
            result = subprocess.check_output(["bash", "packaging/release/cut.sh"], cwd=work,
                                             text=True, stderr=subprocess.STDOUT)
            self.assertEqual(result.splitlines()[-1], "0.7.0")
            self.assertEqual(git("rev-parse", "v0.6.0"), original)
            self.assertIn('"0.7.0"', init.read_text())
            git("checkout", "deps")
            (work / "requirements.txt").write_text("example>=2\n")
            git("add", ".")
            git("commit", "-m", "Update a pending dependency")
            git("push", "origin", "deps")
            git("checkout", "dev")
            (work / "feature").write_text("second change\n")
            git("commit", "-am", "Fix the next setting")
            git("push", "origin", "dev")
            git("checkout", "main")
            git("merge", "--no-ff", "dev", "-m", "Merge branch 'dev'")
            result = subprocess.run(["bash", "packaging/release/cut.sh"], cwd=work,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Merge deps into dev", result.stdout)
            self.assertEqual(git("tag", "-l", "v0.8.0"), "")

    def test_main_sync_preserves_pending_dependencies_and_stops_on_other_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            remote = Path(tmp) / "origin.git"
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=work, text=True,
                                               stderr=subprocess.STDOUT).strip()
            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            git("config", "user.name", "Release Test")
            git("config", "user.email", "release@example.test")
            (work / "packaging/release").mkdir(parents=True)
            (work / "yucha").mkdir()
            for name in ("sync-deps.sh", "bump.py"):
                shutil.copy(NOTES.parent / name, work / "packaging/release" / name)
            init = work / "yucha/__init__.py"
            init.write_text('__version__ = "0.6.0"\n')
            (work / "requirements.txt").write_text("example>=1\n")
            git("add", ".")
            git("commit", "-m", "Add initial release")
            git("remote", "add", "origin", str(remote))
            git("checkout", "-b", "deps")
            init.write_text('__version__ = "0.6.1"\n')
            (work / "requirements.txt").write_text("example>=2\n")
            git("commit", "-am", "Update a dependency")
            pending = git("rev-parse", "HEAD")
            git("push", "origin", "deps")
            git("checkout", "main")
            init.write_text('__version__ = "0.7.0"\nNEW = True\n')
            git("commit", "-am", "Version 0.7.0")
            git("push", "origin", "main")
            sync = subprocess.run(["bash", "packaging/release/sync-deps.sh"], cwd=work,
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(sync.returncode, 0, sync.stdout)
            self.assertEqual(git("show", "origin/deps:requirements.txt"), "example>=2")
            self.assertIn('"0.7.0"', git("show", "origin/deps:yucha/__init__.py"))
            self.assertIn("NEW = True", git("show", "origin/deps:yucha/__init__.py"))
            git("merge-base", "--is-ancestor", pending, "origin/deps")
            synced = git("rev-parse", "origin/deps")
            git("checkout", "main")
            (work / "requirements.txt").write_text("incompatible-main-change\n")
            git("commit", "-am", "Change the dependency differently")
            git("push", "origin", "main")
            result = subprocess.run(["bash", "packaging/release/sync-deps.sh"], cwd=work,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(git("ls-remote", "origin", "refs/heads/deps").split()[0], synced)

    def test_prerelease_allocation_survives_deleted_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            remote = Path(tmp) / "origin.git"
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=work, text=True,
                                               stderr=subprocess.STDOUT).strip()
            git("init", "--bare", str(remote))
            git("init", "-b", "main")
            git("config", "user.name", "Release Test")
            git("config", "user.email", "release@example.test")
            (work / "packaging/release").mkdir(parents=True)
            (work / "yucha").mkdir()
            (work / ".github").mkdir()
            for name in ("prerelease.sh", "bump.py", "notes.py"):
                shutil.copy(NOTES.parent / name, work / "packaging/release" / name)
            (work / "yucha/__init__.py").write_text('__version__ = "0.7.0"\n')
            (work / ".github/allocated-versions.txt").write_text("0.6.99\n0.7.9\n")
            (work / "requirements.txt").write_text("example>=1\n")
            git("add", ".")
            git("commit", "-m", "Add an allocation record without its deleted tag")
            git("remote", "add", "origin", str(remote))
            git("push", "origin", "main")
            (work / "requirements.txt").write_text("example>=2\n")
            git("commit", "-am", "Update the pending dependency")
            result = subprocess.run(["bash", "packaging/release/prerelease.sh"], cwd=work,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout.splitlines()[-1], "0.7.10")
            self.assertIn("0.7.10", (work / ".github/allocated-versions.txt").read_text())

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
                    "### Added",
                    "- Added a language file.",
                    "",
                    "### Changed",
                    "- Moved the pin.",
                    "",
                    "### Fixed",
                    "- Fixed the seek bar.",
                    "",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
