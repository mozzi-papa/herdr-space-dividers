# SPDX-License-Identifier: MIT
# Copyright (c) 2026 KangUnMo
"""배포 고지·압축 파일·전용 실행기의 동작을 확인합니다."""

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import build_release
import update_custom


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="herdr release test ")
        self.addCleanup(temporary.cleanup)
        self.area = Path(temporary.name)

    def test_licenses_follow_runtime_dependencies_and_keep_source_notices(self):
        source = self.area / "source"
        source.mkdir()
        (source / "LICENSE").write_text("upstream license")
        dependency = self.area / "registry/normal"
        dependency.mkdir(parents=True)
        (dependency / "LICENSE-MIT").write_text("dependency copyright and license")
        vendor = source / "vendor/component"
        vendor.mkdir(parents=True)
        (vendor / "NOTICE").write_text("vendor notice")
        zig = self.area / "zig"
        zig.mkdir()
        (zig / "LICENSE").write_text("zig license")
        packages = [{"id": "root", "name": "herdr", "version": "0.9.5", "license": "Apache-2.0",
                     "manifest_path": str(source / "Cargo.toml")},
                    {"id": "normal", "name": "normal", "version": "1", "license": "MIT",
                     "manifest_path": str(dependency / "Cargo.toml")}]
        metadata = {"packages": packages, "resolve": {"root": "root", "nodes": [
            {"id": "root", "deps": [{"pkg": "normal", "dep_kinds": [{"kind": None}]},
                                      {"pkg": "unused-dev", "dep_kinds": [{"kind": "dev"}]}]},
            {"id": "normal", "deps": []}]}}
        destination = self.area / "notices"
        self.assertEqual(build_release.collect_licenses(metadata, source, zig / "zig", destination), 2)
        self.assertEqual((destination / "normal-1/LICENSE-MIT").read_text(), "dependency copyright and license")
        self.assertEqual((destination / "vendored-source/component/NOTICE").read_text(), "vendor notice")
        self.assertNotIn(str(self.area), (destination / "index.json").read_text())
        (dependency / "LICENSE-MIT").unlink()
        with self.assertRaises(update_custom.UpdateError):
            build_release.collect_licenses(metadata, source, zig / "zig", self.area / "missing")

    def test_archive_does_not_record_local_owner_names(self):
        payload = self.area / "package"
        payload.mkdir()
        (payload / "file").write_text("content")
        archive = self.area / "package.tar.gz"
        build_release.make_archive(payload, archive)
        with tarfile.open(archive) as bundle:
            for item in bundle.getmembers():
                self.assertEqual((item.uid, item.gid, item.uname, item.gname, item.mtime), (0, 0, "root", "root", 0))
            self.assertEqual(bundle.extractfile("package/file").read(), b"content")

    def test_missing_crate_license_uses_checked_upstream_commit(self):
        source = self.area / "source"
        source.mkdir()
        crate = self.area / "registry/crate"
        crate.mkdir(parents=True)
        (crate / ".cargo_vcs_info.json").write_text(json.dumps({"git": {"sha1": "a" * 40}}))
        project = self.area / "project"
        licenses = project / "licenses"
        licenses.mkdir(parents=True)
        license_file = licenses / "upstream.txt"
        license_file.write_text("upstream copyright and MIT license")
        override = {"file": "upstream.txt", "sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
                    "commit": "a" * 40, "license": "MIT", "source": "https://example.com/pinned/LICENSE"}
        (licenses / "crate-license-sources.json").write_text(json.dumps({"normal@1": override}))
        zig = self.area / "zig"
        zig.mkdir()
        (zig / "LICENSE").write_text("zig license")
        metadata = {"packages": [{"id": "crate", "name": "normal", "version": "1", "license": "MIT",
                                  "manifest_path": str(crate / "Cargo.toml")}],
                    "resolve": {"root": "crate", "nodes": [{"id": "crate", "deps": []}]}}
        with patch.object(build_release, "BASE", project):
            self.assertEqual(build_release.collect_licenses(metadata, source, zig / "zig", self.area / "good"), 1)
            license_file.write_text("changed")
            with self.assertRaises(update_custom.UpdateError):
                build_release.collect_licenses(metadata, source, zig / "zig", self.area / "bad")

    def test_launcher_resolves_homebrew_style_symlink_and_refuses_nested_attach(self):
        root = self.area / "app folder"
        for directory in ("bin", "libexec", "share/herdr-space-dividers"):
            (root / directory).mkdir(parents=True)
        shutil.copy2(build_release.BASE / "bin/herdr-dividers", root / "bin/herdr-dividers")
        (root / "share/herdr-space-dividers/VERSION").write_text("0.1.0\n")
        binary = root / "libexec/herdr-client"
        binary.write_text('#!/bin/sh\nif [ "$1" = --version ]; then echo "herdr 0.9.5"; else exit 99; fi\n')
        binary.chmod(0o755)
        links = self.area / "links"
        links.mkdir()
        alias = links / "herdr-dividers"
        alias.symlink_to("../app folder/bin/herdr-dividers")
        environment = dict(os.environ, HERDR_ENV="1")
        result = subprocess.run([str(alias), "--version"], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "herdr-dividers 0.1.0 (herdr 0.9.5)")
        result = subprocess.run([str(alias)], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("분리", result.stderr)
        result = subprocess.run([str(alias), "server", "stop"], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        binary.unlink()
        result = subprocess.run([str(alias), "--version"], env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_release_profile_is_used_for_tests_and_build(self):
        zig = self.area / "zig"
        zig.touch()
        outputs = ["module::required: test\n", "test module::required ... ok\ntest result: ok. 1 passed; 0 failed;\n",
                   "", "", "herdr 0.9.5\n", ""]
        with patch.dict(os.environ, {"ZIG": str(zig)}), patch.object(update_custom, "run", side_effect=outputs) as execute:
            binary = update_custom.build_and_verify(self.area, self.area, "0.9.5", {"required_tests": ["required"]},
                                                   self.area / "log", self.area, release_build=True)
        self.assertEqual(binary, self.area / "build-cache/release/herdr")
        self.assertIn("--release", execute.call_args_list[0].args[0])
        self.assertIn("--release", execute.call_args_list[2].args[0])


if __name__ == "__main__":
    unittest.main()
