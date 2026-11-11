# SPDX-License-Identifier: MIT
# Copyright (c) 2026 mozzi-papa
"""업데이트 실패 시 기존 수정본을 보존하는지 검사합니다."""

import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import update_custom as updater


def archive_at(path, version="0.9.5", extra=()):
    with tarfile.open(path, "w:gz") as archive:
        content = f'[package]\nname="herdr"\nversion="{version}"\n'.encode()
        entry = tarfile.TarInfo("herdr/Cargo.toml")
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))
        for entry, content in extra:
            archive.addfile(entry, io.BytesIO(content) if content else None)
    return path


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="herdr-updater-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.binary = self.base / "test-binary"
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o755)
        self.release = updater.save_release(self.base, self.binary, {"version": "0.9.5"})
        updater.activate(self.base, self.release)
        (self.base / "patches").mkdir()
        payload = self.base / "patches/sidebar.patch"
        payload.write_text("test patch\n")
        self.manifest = {"patch_sha256": updater.digest(payload), "required_tests": ["required"]}
        (self.base / "patches/manifest.json").write_text(json.dumps(self.manifest))
        self.archive = archive_at(self.base / "source.tar.gz")

    def test_versions_reject_shell_and_path_input(self):
        self.assertEqual(updater.version_string("v0.9.5"), "0.9.5")
        for value in ("../0.9.5", "0.9.5;touch", "latest", "0.9.5\n"):
            with self.assertRaises(updater.UpdateError):
                updater.version_string(value)

    def test_activation_and_rollback_keep_immutable_binaries(self):
        self.binary.write_text("#!/bin/sh\nexit 1\n")
        next_release = updater.save_release(self.base, self.binary, {"version": "0.9.6"})
        updater.activate(self.base, next_release)
        self.assertEqual(updater.release_at(self.base, "previous"), self.release)
        updater.activate(self.base, self.release)
        self.assertEqual(updater.release_at(self.base, "previous"), next_release)
        self.assertEqual((self.release / "herdr").read_text(), "#!/bin/sh\nexit 0\n")
        self.assertEqual(json.loads((self.release / "validation.json").read_text())["binary_sha256"],
                         updater.digest(self.release / "herdr"))

    def test_failed_link_replacement_preserves_current_and_previous(self):
        second = updater.save_release(self.base, self.binary, {"version": "0.9.6"})
        third = updater.save_release(self.base, self.binary, {"version": "0.9.7"})
        updater.activate(self.base, second)
        real = updater.replace_link

        def fail_current(base, name, release):
            if name == "current":
                raise OSError("교체 실패")
            return real(base, name, release)

        with patch.object(updater, "replace_link", side_effect=fail_current):
            with self.assertRaises(OSError):
                updater.activate(self.base, third)
        self.assertEqual(updater.release_at(self.base, "current"), second)
        self.assertEqual(updater.release_at(self.base, "previous"), self.release)

    def test_source_version_mismatch_preserves_current(self):
        with self.assertRaises(updater.UpdateError):
            updater.update(self.base, "0.9.6", self.archive)
        self.assertEqual(updater.release_at(self.base, "current"), self.release)

    def test_archive_traversal_and_external_symlinks_are_rejected(self):
        traversal = tarfile.TarInfo("herdr/../../escape")
        unsafe_link = tarfile.TarInfo("herdr/escape")
        unsafe_link.type = tarfile.SYMTYPE
        unsafe_link.linkname = "/tmp/outside-herdr-source"
        for item in (traversal, unsafe_link):
            archive_at(self.archive, extra=[(item, b"")])
            destination = self.base / "extracted"
            destination.mkdir(exist_ok=True)
            with self.assertRaises((updater.UpdateError, tarfile.FilterError)):
                updater.extract_source(self.archive, destination, "0.9.5")

    def test_patch_hash_mismatch_preserves_current(self):
        (self.base / "patches/sidebar.patch").write_text("changed")
        with self.assertRaises(updater.UpdateError):
            updater.update(self.base, "0.9.5", self.archive)
        self.assertEqual(updater.release_at(self.base, "current"), self.release)

    def test_patch_build_smoke_and_backup_failures_preserve_current(self):
        for stage in ("apply_patch", "build_and_verify", "back_up_preferences"):
            with self.subTest(stage=stage):
                with patch.object(updater, "apply_patch", return_value=self.manifest), \
                     patch.object(updater, "build_and_verify", return_value=self.binary), \
                     patch.object(updater, "back_up_preferences", return_value=self.base / "backup"), \
                     patch.object(updater, stage, side_effect=updater.UpdateError("실패")):
                    with self.assertRaises(updater.UpdateError):
                        updater.update(self.base, "0.9.5", self.archive)
                self.assertEqual(updater.release_at(self.base, "current"), self.release)

    def test_required_feature_tests_cannot_be_silently_skipped(self):
        zig = self.base / "zig-aarch64-macos-0.16.0/zig"
        zig.parent.mkdir()
        zig.touch()
        with patch.object(updater, "run", return_value="other_test: test"):
            with self.assertRaisesRegex(updater.UpdateError, "필수 기능 테스트"):
                updater.build_and_verify(self.base, self.base, "0.9.5", self.manifest,
                                         self.base / "test.log", self.base)

    def test_success_backs_up_settings_without_rewriting_them(self):
        state = self.base / "state/herdr-dev/client-shell"
        state.mkdir(parents=True)
        preferences = state / "local-test.json"
        preferences.write_text('{"dividers":[{"title":"업무"}]}')
        original = preferences.read_bytes()
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.base / "state")}), \
             patch.object(updater, "apply_patch", return_value=self.manifest), \
             patch.object(updater, "build_and_verify", return_value=self.binary):
            release = updater.update(self.base, "0.9.5", self.archive)
        self.assertEqual(updater.release_at(self.base, "current"), release)
        self.assertEqual(updater.release_at(self.base, "previous"), self.release)
        self.assertEqual(preferences.read_bytes(), original)
        metadata = json.loads((release / "validation.json").read_text())
        self.assertEqual((Path(metadata["preferences_backup"]) / "herdr-dev/local-test.json").read_bytes(), original)
        self.assertEqual(Path(metadata["preferences_backup"]).stat().st_mode & 0o077, 0)

    def test_installed_version_falls_back_to_path(self):
        result = type("Result", (), {"stdout": "herdr 0.9.5\n"})()
        with patch.object(updater.Path, "is_file", return_value=False), \
             patch.object(updater.shutil, "which", return_value="/opt/homebrew/bin/herdr"), \
             patch.object(updater.subprocess, "run", return_value=result) as execute:
            self.assertEqual(updater.installed_version(), "0.9.5")
        self.assertEqual(str(execute.call_args.args[0][0]), "/opt/homebrew/bin/herdr")

    def test_ignored_required_feature_tests_are_rejected(self):
        zig = self.base / "zig-aarch64-macos-0.16.0/zig"
        zig.parent.mkdir()
        zig.touch()
        with patch.object(updater, "run", side_effect=["module::required: test\n",
                "test module::required ... ignored\ntest result: ok. 1 passed; 0 failed; 1 ignored;\n"]):
            with self.assertRaisesRegex(updater.UpdateError, "실제로 통과하지 않았습니다"):
                updater.build_and_verify(self.base, self.base, "0.9.5", self.manifest,
                                         self.base / "test.log", self.base)

    def test_concurrent_update_is_refused(self):
        with updater.update_lock(self.base):
            with self.assertRaises(updater.UpdateError):
                with updater.update_lock(self.base):
                    self.fail("동시에 진입하면 안 됩니다.")

    def test_actual_patch_dry_run_rejects_missing_context_without_partial_edits(self):
        source = self.base / "original"
        source.mkdir()
        (source / "sample").write_text("original\n")
        payload = self.base / "patches/sidebar.patch"
        payload.write_text("--- a/sample\n+++ b/sample\n@@ -1 +1 @@\n-missing\n+changed\n")
        self.manifest["patch_sha256"] = updater.digest(payload)
        (self.base / "patches/manifest.json").write_text(json.dumps(self.manifest))
        with self.assertRaises(updater.UpdateError):
            updater.apply_patch(self.base, source, self.base / "patch.log")
        self.assertEqual((source / "sample").read_text(), "original\n")

    def test_actual_patch_applies_matching_context(self):
        source = self.base / "original"
        source.mkdir()
        (source / "sample").write_text("original\n")
        payload = self.base / "patches/sidebar.patch"
        payload.write_text("--- a/sample\n+++ b/sample\n@@ -1 +1 @@\n-original\n+changed\n")
        self.manifest["patch_sha256"] = updater.digest(payload)
        (self.base / "patches/manifest.json").write_text(json.dumps(self.manifest))
        updater.apply_patch(self.base, source, self.base / "patch.log")
        self.assertEqual((source / "sample").read_text(), "changed\n")


if __name__ == "__main__":
    unittest.main()
