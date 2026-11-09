# SPDX-License-Identifier: MIT
# Copyright (c) 2026 KangUnMo
"""검증을 통과한 Herdr 수정본만 선택하고 이전 실행 파일을 보존합니다."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import uuid

BASE = Path(__file__).resolve().parents[1]


class UpdateError(Exception):
    pass


def version_string(value):
    value = value.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", value):
        raise UpdateError("버전은 0.9.5 또는 v0.9.5 형식이어야 합니다.")
    return value


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, *, log, cwd=None, env=None, timeout=3600):
    try:
        with log.open("ab") as stream:
            stream.write(f"\n$ {command!r}\n".encode())
            stream.flush()
            offset = stream.tell()
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpdateError(f"명령 실행 실패: {command[0]}: {error}") from error
    with log.open("rb") as stream:
        stream.seek(offset)
        output = stream.read().decode(errors="replace")
    if result.returncode:
        raise UpdateError(f"명령 실패: {command[0]} (종료값 {result.returncode})\n"
                          + "\n".join(output.splitlines()[-25:]))
    return output


@contextmanager
def update_lock(base):
    with (base / ".update.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UpdateError("다른 수정본 업데이트가 실행 중입니다.") from error
        yield


def release_at(base, name):
    link = base / name
    if not link.is_symlink():
        return None
    release = link.resolve()
    if release.parent != (base / "releases").resolve():
        raise UpdateError(f"잘못된 실행 파일 선택 경로: {name}")
    if not (release / "herdr").is_file() or not os.access(release / "herdr", os.X_OK):
        raise UpdateError(f"실행 파일을 찾을 수 없습니다: {release}")
    return release


def replace_link(base, name, release):
    temporary = base / f".{name}-{uuid.uuid4().hex}"
    try:
        temporary.symlink_to(release.resolve().relative_to(base.resolve()), target_is_directory=True)
        os.replace(temporary, base / name)
    finally:
        temporary.unlink(missing_ok=True)


def activate(base, release):
    current = release_at(base, "current")
    previous = release_at(base, "previous")
    if current == release:
        return
    if current:
        replace_link(base, "previous", current)
    try:
        replace_link(base, "current", release)
    except OSError:
        if previous:
            replace_link(base, "previous", previous)
        else:
            (base / "previous").unlink(missing_ok=True)
        raise


def save_release(base, binary, metadata):
    releases = base / "releases"
    releases.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".candidate-", dir=releases) as temporary:
        stage = Path(temporary)
        shutil.copy2(binary, stage / "herdr")
        metadata["binary_sha256"] = digest(stage / "herdr")
        (stage / "validation.json").write_text(json.dumps(metadata, indent=2) + "\n")
        release = releases / f"{metadata['version']}-{uuid.uuid4().hex[:12]}"
        os.replace(stage, release)
    return release.resolve()


def back_up_preferences(base):
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    backup = base / "backups" / f"update-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    backup.mkdir(parents=True, mode=0o700)
    for app in ("herdr-dev", "herdr"):
        for source in (state / app / "client-shell").glob("*.json"):
            destination = backup / app / source.name
            destination.parent.mkdir(exist_ok=True, mode=0o700)
            shutil.copy2(source, destination)
    return backup


def extract_source(archive, destination, version):
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        roots = set()
        total = 0
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise UpdateError("소스 압축 파일에 잘못된 경로가 있습니다.")
            roots.add(path.parts[0])
            total += member.size
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise UpdateError("소스 압축 파일에 지원하지 않는 항목이 있습니다.")
        if len(roots) != 1 or total > 512 * 1024 * 1024:
            raise UpdateError("소스 압축 파일 구조 또는 크기가 허용 범위를 벗어났습니다.")
        bundle.extractall(destination, filter="data")
    source = destination / roots.pop()
    package = tomllib.loads((source / "Cargo.toml").read_text())["package"]
    if package.get("name") != "herdr" or package.get("version") != version:
        raise UpdateError("요청한 버전과 소스의 Cargo.toml 버전이 일치하지 않습니다.")
    return source


def apply_patch(base, source, log):
    manifest = json.loads((base / "patches/manifest.json").read_text())
    patch = base / "patches/sidebar.patch"
    if digest(patch) != manifest["patch_sha256"]:
        raise UpdateError("패치 해시가 일치하지 않습니다. 패키지를 확인해 주세요.")
    command = ["patch", "-p1", "--batch", "--forward", "--fuzz=0", "-i", str(patch)]
    run(command + ["--dry-run"], log=log, cwd=source)
    run(command, log=log, cwd=source)
    return manifest


def build_and_verify(base, source, version, manifest, log, run_dir, release_build=False):
    environment = os.environ.copy()
    environment.setdefault("RUSTUP_TOOLCHAIN", "1.96.1")
    environment["CARGO_BUILD_JOBS"] = "4"
    environment["CARGO_TARGET_DIR"] = str(base / "build-cache")
    zig = environment.get("ZIG") or str(base / "zig-aarch64-macos-0.16.0/zig")
    if not Path(zig).is_file():
        zig = shutil.which("zig")
    if not zig:
        raise UpdateError("Zig 실행 파일이 필요합니다. ZIG 환경 변수로 경로를 지정해 주세요.")
    environment["ZIG"] = zig
    profile_args = ["--release"] if release_build else []
    print("[검증] 필수 기능 테스트 목록과 전체 클라이언트 테스트", flush=True)
    listing = run(["cargo", "test", *profile_args, "--locked", "--bin", "herdr", "client::shell::", "--", "--list"],
                  log=log, cwd=source, env=environment)
    for test in manifest["required_tests"]:
        if f"::{test}: test" not in listing:
            raise UpdateError(f"필수 기능 테스트를 찾을 수 없습니다: {test}")
    test_output = run(["cargo", "test", *profile_args, "--locked", "--bin", "herdr", "client::shell::", "--",
                       "--test-threads=4"], log=log, cwd=source, env=environment)
    if not re.search(r"test result: ok\. [1-9]\d* passed; 0 failed;", test_output):
        raise UpdateError("클라이언트 테스트의 성공 결과를 확인할 수 없습니다.")
    for test in manifest["required_tests"]:
        if not re.search(r"test [^\n]*::" + re.escape(test) + r" \.\.\. ok(?:\n|$)", test_output):
            raise UpdateError(f"필수 기능 테스트가 실제로 통과하지 않았습니다: {test}")
    print("[빌드] 새 수정본 실행 파일 생성", flush=True)
    run(["cargo", "build", *profile_args, "--locked", "--bin", "herdr"], log=log, cwd=source, env=environment)
    run(["cargo", "fmt", "--all", "--check"], log=log, cwd=source, env=environment)
    binary = base / "build-cache" / ("release" if release_build else "debug") / "herdr"
    found_version = run([str(binary), "--version"], log=log, env=environment, timeout=15).strip()
    if found_version != f"herdr {version}":
        raise UpdateError(f"빌드 결과 버전이 다릅니다: {found_version}")
    print("[검증] 별도 서버에서 마우스·저장·재접속·폴더 메뉴 검사", flush=True)
    environment["HERDR_MVP_BINARY"] = str(binary)
    environment["HERDR_MVP_LOG_DIR"] = str(run_dir)
    run([sys.executable, str(base / "smoke_mvp.py")], log=log, cwd=base,
        env=environment, timeout=120)
    return binary


def installed_version():
    official = Path.home() / ".local/bin/herdr"
    if not official.is_file():
        found = shutil.which("herdr")
        if not found:
            raise UpdateError("공식 Herdr를 찾을 수 없습니다. 먼저 설치하거나 버전을 직접 지정해 주세요.")
        official = Path(found)
    result = subprocess.run([str(official), "--version"], check=True,
                            capture_output=True, text=True, timeout=15)
    match = re.fullmatch(r"herdr (\S+)", result.stdout.strip())
    if not match:
        raise UpdateError("공식 Herdr 버전을 읽을 수 없습니다. 버전을 직접 지정해 주세요.")
    return version_string(match[1])


def update(base, version, source_archive=None):
    manifest = json.loads((base / "patches/manifest.json").read_text())
    if digest(base / "patches/sidebar.patch") != manifest["patch_sha256"]:
        raise UpdateError("패치 해시가 일치하지 않습니다.")
    runs = base / "update-logs"
    runs.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"v{version}-", dir=runs))
    log = run_dir / "update.log"
    log.touch()
    print(f"[시작] Herdr {version} / 로그: {log}", flush=True)
    try:
        archive = source_archive
        if archive is None:
            cached = base / f"herdr-v{version}.tar.gz"
            archive = cached if cached.is_file() else run_dir / "source.tar.gz"
            if not archive.exists():
                run(["curl", "--fail", "--location", "--proto", "=https", "--tlsv1.2",
                     "--connect-timeout", "15", "--max-time", "180", "--output", str(archive),
                     f"https://codeload.github.com/herdrdev/herdr/tar.gz/refs/tags/v{version}"],
                    log=log, timeout=190)
        print("[적용] 공식 소스의 버전·경로 확인 후 엄격한 패치 적용", flush=True)
        source = extract_source(archive, run_dir, version)
        manifest = apply_patch(base, source, log)
        binary = build_and_verify(base, source, version, manifest, log, run_dir)
        backup = back_up_preferences(base)
        release = save_release(base, binary, {
            "version": version, "origin": "patched-official-source",
            "patch_sha256": manifest["patch_sha256"], "source_sha256": digest(archive),
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "validation": "필수 테스트 존재·전체 클라이언트 테스트·별도 PTY 검증 통과",
            "log": str(log), "preferences_backup": str(backup),
        })
        activate(base, release)
        print(f"[완료] {version} 수정본을 선택했습니다. 다음 재접속부터 적용됩니다.\n"
              f"설정 백업: {backup}\n복구: sh {base / 'update-custom.sh'} --rollback", flush=True)
        return release
    except BaseException as error:
        try:
            with log.open("a") as stream:
                stream.write(f"\n업데이트 중단: {type(error).__name__}: {error}\n")
        except OSError:
            pass
        print(f"[중단] 기존 실행 대상을 유지합니다. 로그: {log}", file=sys.stderr, flush=True)
        raise


def status(base):
    for name in ("current", "previous"):
        release = release_at(base, name)
        if release:
            data = json.loads((release / "validation.json").read_text())
            print(f"{name}: {data['version']} / {release / 'herdr'}")
        else:
            print(f"{name}: 미설정" + (" (먼저 update-custom.sh로 빌드해 주세요)" if name == "current" else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="생략하면 설치된 공식 Herdr 버전")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rollback", action="store_true", help="직전 실행 파일로 복구")
    group.add_argument("--status", action="store_true", help="선택된 버전 조회")
    parser.add_argument("--source-archive", type=Path, help="지정 버전의 로컬 공식 소스 tar.gz")
    arguments = parser.parse_args()
    if (arguments.rollback or arguments.status) and (arguments.version or arguments.source_archive):
        parser.error("조회·복구와 버전·소스 지정은 함께 사용할 수 없습니다.")
    try:
        if arguments.status:
            status(BASE)
            return 0
        with update_lock(BASE):
            if arguments.rollback:
                previous = release_at(BASE, "previous")
                if previous is None:
                    raise UpdateError("복구할 이전 수정본이 없습니다.")
                activate(BASE, previous)
                print("이전 실행 파일을 선택했습니다. 현재 분류 설정은 유지됩니다.")
                status(BASE)
            else:
                version = version_string(arguments.version) if arguments.version else installed_version()
                archive = arguments.source_archive.expanduser().resolve() if arguments.source_archive else None
                update(BASE, version, archive)
        return 0
    except KeyboardInterrupt:
        print("업데이트를 취소했습니다. 기존 실행 대상을 유지합니다.", file=sys.stderr)
        return 130
    except (UpdateError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
