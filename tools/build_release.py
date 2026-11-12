# SPDX-License-Identifier: MIT
# Copyright (c) 2026 mozzi-papa
"""검증된 Apple Silicon 릴리스와 Homebrew formula를 로컬에 준비합니다."""

import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tarfile
import tempfile

import update_custom as updater

BASE = Path(__file__).resolve().parents[1]


def collect_licenses(metadata, source, zig, destination):
    """실제 대상의 Rust 의존성과 vendored Zig 소스의 고지를 보존합니다."""
    destination.mkdir(parents=True)
    packages = {item["id"]: item for item in metadata["packages"]}
    nodes = {item["id"]: item for item in metadata["resolve"]["nodes"]}
    pending = [metadata["resolve"]["root"]]
    used = set()
    while pending:
        package_id = pending.pop()
        if package_id in used:
            continue
        used.add(package_id)
        for dependency in nodes[package_id]["deps"]:
            if any(kind["kind"] != "dev" for kind in dependency["dep_kinds"]):
                pending.append(dependency["pkg"])
    index = []
    for package_id in sorted(used):
        package = packages[package_id]
        root = Path(package["manifest_path"]).parent
        files = [path for path in root.iterdir() if path.is_file() and
                 re.match(r"^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)(?:[._-]|$)", path.name, re.I)]
        if package.get("license_file"):
            files.append(root / package["license_file"])
        if not files and root.is_relative_to(source):
            files = [source / "LICENSE"]
        extra_source = None
        if not files:
            overrides_path = BASE / "licenses/crate-license-sources.json"
            overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
            override = overrides.get(f"{package['name']}@{package['version']}")
            if override:
                candidate = BASE / "licenses" / override["file"]
                vcs = json.loads((root / ".cargo_vcs_info.json").read_text())
                if updater.digest(candidate) != override["sha256"] or \
                        vcs["git"]["sha1"] != override["commit"] or package["license"] != override["license"]:
                    raise updater.UpdateError(f"보완 라이선스 원본 정보가 일치하지 않습니다: {package['name']}")
                files = [candidate]
                extra_source = override["source"]
        if not files:
            raise updater.UpdateError(f"라이선스 고지 파일을 찾을 수 없습니다: {package['name']} {package['version']}")
        folder = destination / f"{package['name']}-{package['version']}"
        folder.mkdir()
        for path in sorted(set(files)):
            shutil.copy2(path, folder / path.name)
        index.append({"name": package["name"], "version": package["version"],
                      "license": package.get("license"), "directory": folder.name, "extra_source": extra_source})
    vendor_root = source / "vendor"
    for path in sorted(vendor_root.rglob("*")):
        if path.is_file() and not any(part in {".zig-cache", "zig-out", ".git"} for part in path.parts) and \
                re.match(r"^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)(?:[._-]|$)", path.name, re.I):
            target = destination / "vendored-source" / path.relative_to(vendor_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    zig_license = zig.parent / "LICENSE"
    if not zig_license.is_file():
        raise updater.UpdateError("Zig 배포본의 LICENSE 파일을 찾을 수 없습니다.")
    shutil.copy2(zig_license, destination / "Zig-LICENSE")
    (destination / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return len(index)


def make_archive(payload, archive):
    def portable_info(info):
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = 0
        return info
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(payload, arcname=payload.name, filter=portable_info)


def formula_text(version, sha256):
    return f'''# SPDX-License-Identifier: MIT
# Copyright (c) 2026 mozzi-papa
class HerdrSpaceDividers < Formula
  desc "Workspace dividers and grouping for Herdr (unofficial client)"
  homepage "https://github.com/mozzi-papa/herdr-space-dividers"
  url "https://github.com/mozzi-papa/herdr-space-dividers/releases/download/v{version}/herdr-space-dividers-v{version}-macos-arm64.tar.gz"
  version "{version}"
  sha256 "{sha256}"
  license all_of: ["MIT", "Apache-2.0"]

  depends_on :macos
  depends_on arch: :arm64
  on_macos do
    depends_on macos: :sequoia
  end

  def install
    bin.install "bin/herdr-div"
    bin.install_symlink "herdr-div" => "herdr-dividers"
    libexec.install "libexec/herdr-client"
    (share/"herdr-space-dividers").install Dir["share/herdr-space-dividers/*"]
  end

  def caveats
    <<~EOS
      An existing default local Herdr server is required.
      Run: herdr-div  (herdr-dividers also works)
      The official herdr command and your running server are unchanged.
    EOS
  end

  test do
    assert_match "herdr-div #{{version}}", shell_output("#{{bin}}/herdr-div --version")
    assert_match "herdr-div #{{version}}", shell_output("#{{bin}}/herdr-dividers --version")
  end
end
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-archive", type=Path)
    arguments = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise updater.UpdateError("현재 릴리스 빌드는 Apple Silicon macOS에서만 지원합니다.")
    version = updater.version_string((BASE / "VERSION").read_text().strip())
    manifest = json.loads((BASE / "patches/manifest.json").read_text())
    upstream = manifest["base_version"]
    work_root = BASE / ".release-work"
    work_root.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"v{version}-", dir=work_root))
    log = work / "release.log"
    log.touch()
    archive = arguments.source_archive
    if archive is None:
        cached = sorted(BASE.glob(f"update-logs/v{upstream}-*/source.tar.gz"))
        archive = cached[-1] if cached else work / "source.tar.gz"
        if not archive.exists():
            updater.run(["curl", "--fail", "--location", "--proto", "=https", "--tlsv1.2",
                         "--connect-timeout", "15", "--max-time", "180", "-o", str(archive),
                         f"https://codeload.github.com/herdrdev/herdr/tar.gz/refs/tags/v{upstream}"], log=log)
    print(f"[릴리스] {version}, Herdr {upstream} / {log}", flush=True)
    source = updater.extract_source(archive, work, upstream)
    updater.apply_patch(BASE, source, log)
    os.environ["MACOSX_DEPLOYMENT_TARGET"] = "15.0"
    remap = f"--remap-path-prefix={Path.home()}=/herdr-dividers-build"
    flags = os.environ.get("CARGO_ENCODED_RUSTFLAGS", "")
    os.environ["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(filter(None, [flags, remap]))
    binary = updater.build_and_verify(BASE, source, upstream, manifest, log, work, release_build=True)
    package_release(source, binary, version, upstream, manifest, archive, work, log)


def package_release(source, binary, version, upstream, manifest, archive, work, log):
    print("[패키지] 실행 파일·제삼자 고지·검증 기록 준비", flush=True)
    dist = BASE / "dist"
    dist.mkdir(exist_ok=True)
    payload = work / f"herdr-space-dividers-{version}"
    if payload.exists():
        shutil.rmtree(payload)
    (payload / "bin").mkdir(parents=True)
    (payload / "libexec").mkdir()
    share = payload / "share/herdr-space-dividers"
    share.mkdir(parents=True)
    shutil.copy2(BASE / "bin/herdr-div", payload / "bin/herdr-div")
    shipped_binary = payload / "libexec/herdr-client"
    shutil.copy2(binary, shipped_binary)
    updater.run(["strip", "-x", str(shipped_binary)], log=log)
    updater.run(["codesign", "--force", "--sign", "-", str(shipped_binary)], log=log)
    updater.run(["codesign", "--verify", "--strict", str(shipped_binary)], log=log)
    environment = os.environ.copy()
    environment["RUSTUP_TOOLCHAIN"] = os.environ.get("RUSTUP_TOOLCHAIN", "1.96.1")
    metadata = json.loads(updater.run(["cargo", "metadata", "--locked", "--offline", "--format-version", "1",
                                      "--filter-platform", "aarch64-apple-darwin"], cwd=source, env=environment, log=log))
    zig_value = os.environ.get("ZIG") or shutil.which("zig")
    if not zig_value:
        raise updater.UpdateError("Zig 라이선스 수집을 위해 ZIG 경로를 지정해 주세요.")
    license_count = collect_licenses(metadata, source, Path(zig_value).resolve(), share / "third-party")
    sysroot = Path(updater.run(["rustup", "run", environment["RUSTUP_TOOLCHAIN"], "rustc", "--print", "sysroot"], log=log).strip())
    rust_docs = sysroot / "share/doc/rust"
    rust_notices = share / "third-party/Rust"
    shutil.copytree(rust_docs / "licenses", rust_notices / "licenses")
    for name in ("COPYRIGHT.html", "COPYRIGHT-library.html"):
        shutil.copy2(rust_docs / name, rust_notices / name)
    for name in ("VERSION", "LICENSE", "NOTICE"):
        shutil.copy2(BASE / name, share / name)
    shutil.copytree(BASE / "licenses", share / "licenses")
    shutil.copytree(BASE / "docs", share / "docs")
    environment["HERDR_MVP_BINARY"] = str(shipped_binary)
    environment["HERDR_MVP_LOG_DIR"] = str(work / "packaged-check")
    updater.run([sys.executable, str(BASE / "smoke_mvp.py")], env=environment, log=log, timeout=120)
    linker = updater.run(["otool", "-L", str(shipped_binary)], log=log)
    private_values = [str(Path.home()).encode(), getpass.getuser().encode()]
    for path in payload.rglob("*"):
        if path.is_file() and any(value in path.read_bytes() for value in private_values if value):
            raise updater.UpdateError(f"배포 파일에서 로컬 개인 경로·계정 값이 발견되었습니다: {path.relative_to(payload)}")
    if any(line.strip().startswith("/") and not line.strip().startswith(("/usr/lib/", "/System/Library/"))
           for line in linker.splitlines()[1:]):
        raise updater.UpdateError("시스템 밖의 동적 라이브러리 연결을 확인해 주세요.")
    record = {"version": version, "herdr_version": upstream, "platform": "macos-arm64",
              "minimum_macos": "15.0", "tested_macos": platform.mac_ver()[0],
              "patch_sha256": manifest["patch_sha256"], "source_sha256": updater.digest(archive),
              "binary_sha256": updater.digest(shipped_binary), "rust_license_packages": license_count,
              "signature": "ad-hoc; not Developer ID signed or notarized",
              "validated_at": datetime.now(timezone.utc).isoformat()}
    (share / "build-info.json").write_text(json.dumps(record, indent=2) + "\n")
    package = dist / f"herdr-space-dividers-v{version}-macos-arm64.tar.gz"
    make_archive(payload, package)
    checksum = updater.digest(package)
    (dist / "SHA256SUMS").write_text(f"{checksum}  {package.name}\n")
    (dist / "herdr-space-dividers.rb").write_text(formula_text(version, checksum))
    (BASE / ".release-work/latest").write_text(str(work))
    print(f"[완료] {package}\nSHA-256: {checksum}\n공개 업로드는 수행하지 않았습니다.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (updater.UpdateError, OSError, ValueError, tarfile.TarError) as error:
        print(f"릴리스 준비 실패: {error}", file=sys.stderr)
        sys.exit(1)
