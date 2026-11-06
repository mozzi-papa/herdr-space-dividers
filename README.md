# Herdr Space Dividers

Herdr의 `spaces` 목록에 제목이 있는 구분선을 추가하는 **비공식 클라이언트 패치**입니다. 구분선별 분류, 접기·펼치기, 드래그, 편집 취소와 폴더 메뉴를 제공합니다.

독립 도구와 문서는 **MIT**, Herdr 기반 패치는 **Apache-2.0**입니다. 각 라이선스를 지키면서 사용·수정·재배포할 수 있습니다. [라이선스 범위](docs/LICENSING.md)를 참고해 주세요.

## 어떤 기능인가요?

아래는 화면 구성을 설명하는 예시입니다.

```text
spaces
○ 새 프로젝트

▼ 업무 · 2 ─────────
  ○ 프로젝트 A
  ○ 프로젝트 B

▼ 개인 · 1 ─────────
  ○ 공부

new   div       menu
```

- `div`로 제목이 있는 독립 구분선을 만듭니다. 구분선은 셸이나 에이전트를 만들지 않습니다.
- 구분선 아래 스페이스를 들여쓰기하고 소속을 ID로 기억합니다.
- 제목을 클릭하면 접고 펼칩니다. 접힌 공간의 작업은 계속 실행됩니다.
- 구분선과 스페이스를 드래그하여 위치·분류를 편집합니다.
- div 우클릭은 이름 변경·삭제·편집 취소, 스페이스 우클릭은 기존 메뉴와 폴더 열기·경로 복사를 제공합니다.
- 구분선은 숫자 이동 대상에서 제외하며, 접힌 스페이스를 단축키로 선택하면 펼쳐집니다.

현재 기능은 일반 로컬 단일 머신의 펼친 사이드바를 대상으로 합니다. 공식 `herdr plugin install`로 설치하는 플러그인이나 공식 Herdr 릴리스가 아닙니다.

## 지원 환경

| 항목 | 검증 범위 |
|---|---|
| 운영체제·칩 | macOS / Apple Silicon M2 Max |
| Herdr | **0.9.5**, 기본 설정 경로를 사용하는 기본 로컬 세션 |
| 빌드 | Rust **1.96.1** + rustfmt, Zig **0.16.0**, 디버그 빌드 |
| Python | 3.11 이상, `tarfile.data_filter` 지원 필요 |
| 추가 도구 | macOS 개발 도구, `patch`, `curl`, 소스를 받을 Git 또는 ZIP 다운로드 |

다른 Herdr 버전은 적용 후보입니다. 해당 버전으로 패치·빌드·기능 검증을 통과해야 하며, 큰 구조 변경은 패치 보수가 필요합니다. Intel Mac·Linux·Windows와 메모리 사용량은 검증하지 않았습니다.

## 설치와 첫 실행

먼저 [공식 Herdr](https://herdr.dev/tui/)와 위 빌드 도구를 준비해 주세요. 이 프로젝트는 시스템 도구를 자동 설치하지 않습니다. Rust는 `rustup toolchain install 1.96.1 --profile minimal --component rustfmt`로 준비할 수 있습니다. Zig 0.16.0은 [공식 다운로드](https://ziglang.org/download/0.16.0/)에서 받으시고 파일 경로를 `ZIG`로 지정하거나 `zig`를 PATH에 등록해 주세요.

```sh
git clone https://github.com/KangUnMo/herdr-space-dividers.git
cd herdr-space-dividers
python3 --version
rustup run 1.96.1 rustc --version
zig version
sh update-custom.sh 0.9.5
```

`zig`가 PATH에 없다면 마지막 명령 앞에 `ZIG="실제 Zig 실행 파일의 절대 경로"`를 지정해 주세요. 빌드와 검증에는 시간이 걸리고 수 GB의 디스크 공간이 필요합니다.

기본 로컬 Herdr 서버가 실행 중이어야 합니다. 서버가 없다면 별도 터미널에서 `command herdr`를 실행한 뒤 기본 설정의 `Ctrl+B`, `q`로 화면만 분리해 주세요. **사용 중인 서버를 종료할 필요는 없습니다.**

Herdr 밖의 터미널에서 다음 명령으로 수정본 화면에 연결합니다.

```sh
sh run.sh
```

현재 사용 중인 Herdr 안에서는 중첩 실행을 거부합니다. 먼저 화면만 분리한 뒤 실행해 주세요. 셸 설정이나 Ghostty 설정을 자동으로 편집하지 않습니다.

## 사용·업데이트·복구

- [사용법](docs/USAGE.md): 구분선 편집, 소속 이동, 단축키, 폴더 메뉴
- [업데이트와 복구](docs/UPDATING.md): 버전 선택, 실패 대응, 원래 화면으로 복귀
- [안전장치와 한계](docs/SAFETY.md): 변경되는 파일과 실행되는 작업
- [검증 결과](docs/VERIFICATION.md): 실제 확인한 환경과 검사 범위

공식 Herdr를 업데이트한 뒤 저장소 폴더에서 실행합니다. 생략한 버전은 설치된 공식 실행 파일에서 읽습니다.

```sh
sh update-custom.sh
sh update-custom.sh --status
```

모든 검증을 통과한 수정본만 다음 실행 대상으로 선택합니다. 실패하면 기존 수정본을 유지합니다. 첫 설치가 실패하면 선택된 수정본이 생기지 않습니다.

```sh
sh update-custom.sh --rollback
```

복구는 직전 수정본이 있을 때만 가능합니다. 실행 파일 선택을 되돌리며 현재 분류 설정은 덮어쓰지 않습니다. 재접속은 기본 설정에서 `Ctrl+B`, `q` 다음 `sh run.sh`입니다.

## 안전성을 어떻게 확인하나요?

설정 백업, 엄격한 패치 적용, 필수 테스트 통과 검사, 별도 서버 검증, 실패 시 기존 실행 파일 유지와 복구를 구현했습니다. 사용자의 기존 서버나 공식 실행 파일을 자동 종료·교체하지 않습니다.

**무결점이나 모든 버전의 호환성을 보장하지는 않습니다.** 다운로드한 공식 Herdr 소스와 의존성을 사용자 권한으로 빌드·실행합니다. 먼저 코드와 [안전 안내](docs/SAFETY.md)를 확인해 주세요. 외부 보안 감사를 받은 제품으로 표시하지 않습니다.

## 개발과 기여

```sh
python3 -m unittest discover -s tools -p 'test_update_custom.py' -v
sh -n update-custom.sh
sh -n run.sh
```

코드·문서 개선과 재현 가능한 문제 보고를 환영합니다. 보고에는 Herdr·OS·도구 버전, 재현 순서와 필요한 오류만 포함해 주세요. 설정 백업과 전체 로그에는 로컬 경로나 프로젝트 정보가 있을 수 있으므로 그대로 공개하지 말아 주세요.

이 저장소의 변경 요청은 이 저장소를 대상으로 합니다. Herdr 본체의 기여 정책은 [원본 프로젝트](https://github.com/herdrdev/herdr)의 정책을 따릅니다.

## English summary

Unofficial Herdr 0.9.5 client patch for independent workspace dividers, grouping, collapse/expand, drag editing, undo, and local folder actions. Tested on Apple Silicon macOS. Source build only; Rust 1.96.1, Zig 0.16.0 and Python 3.11 with tar extraction filters are required. Start with `sh update-custom.sh 0.9.5`, then attach to your existing default local server with `sh run.sh` outside Herdr. Updates activate only after tests pass. Independent tools/docs are MIT; the Herdr-derived patch remains Apache-2.0. This is not an official plugin, a security-audited release, or a guarantee of future compatibility.
