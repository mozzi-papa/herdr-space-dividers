# 릴리스 준비와 배포

## 승인된 로컬 준비 범위

목표는 Apple Silicon 사용자가 Rust·Zig·Python 없이 검증된 실행 파일을 Homebrew로 설치하도록 만드는 것입니다. 기존 `herdr` 명령과 사용자 서버는 유지하고 `herdr-dividers` 명령을 제공합니다. 소스 빌드 도구는 개발자용으로 남깁니다.

클라이언트 설정은 디버그·릴리스 빌드 모두 기존 `herdr-dev/client-shell` JSON 경로를 사용합니다. 새로운 데이터베이스나 설정 마이그레이션을 도입하지 않습니다.

## 구성과 검증 순서

- [x] `patches/`: 릴리스 빌드에서도 기존 설정 경로를 유지하고 필수 검증을 추가했습니다.
- [x] `bin/herdr-dividers`: 별도 실행 명령과 도움말·버전 확인을 제공합니다.
- [x] `tools/build_release.py`: 공식 소스 패치·릴리스 테스트·빌드·개인 경로 제거·라이선스 수집·체크섬·배포 압축 파일을 생성합니다.
- [x] `tools/test_release.py`: 실행기·라이선스 고지 수집·배포 파일 목록을 검사했습니다.
- [x] `dist/herdr-space-dividers.rb`: 공개 URL과 SHA-256이 들어간 formula를 생성하고, 임시 tap에서 로컬 배포 파일의 설치를 확인했습니다.
- [x] `README.md`, `assets/`: 설치 중심의 안내와 개인 정보가 없는 구성 예시를 제공합니다.
- [x] 릴리스 실행 파일에서 마우스·설정 저장·재접속, 디버그 실행 파일과 저장 파일 호환을 확인했습니다.
- [ ] 소스 커밋·태그, GitHub Release 파일 공개, 별도 Homebrew tap 공개와 공개 URL 설치 확인을 완료합니다.

## 빌드

필요한 도구는 소스 빌드 안내와 같습니다. 릴리스 빌드는 개발자의 맥에서 수행하며 유료 빌드 서비스나 유료 인증서를 사용하지 않습니다.

```sh
python3 tools/build_release.py
```

`dist/`의 파일은 실제 검증을 통과한 뒤 생성합니다. 실행 파일은 배포용으로 최적화하고 로컬 개인 경로가 들어 있지 않은지 검사합니다. 압축 파일에는 실행기, 클라이언트, 버전 정보, 프로젝트 라이선스와 제삼자 고지를 포함합니다. Apple Developer ID 서명이나 Apple 공증을 받은 파일로 표시하지 않습니다.

## 공개 단계

로컬 검증 후 변경 파일·릴리스 파일·커밋 메시지와 정확한 명령을 제시하고 승인받아 진행합니다. 이 문서를 작성하거나 빌드하는 동작은 Git commit·push, 원격 tap 저장소 생성이나 GitHub Release 업로드를 자동으로 실행하지 않습니다.

첫 패키지 버전은 0.1.0이며 기반 Herdr 버전은 0.9.5입니다. 패키지 버전과 Herdr 버전은 서로 구분합니다. 공개 formula는 버전이 고정된 릴리스 URL과 SHA-256을 사용하며, 사용자는 Homebrew로 업데이트합니다. `update-custom.sh --rollback`은 소스 빌드 전용이므로 Homebrew 패키지의 복구 명령으로 안내하지 않습니다.

승인받은 공개 단계에서는 소스를 먼저 올리고, `v0.1.0` 릴리스에 `dist/herdr-space-dividers-v0.1.0-macos-arm64.tar.gz`와 `dist/SHA256SUMS`를 첨부합니다. 생성된 공개 formula를 별도 `mozzi-papa/homebrew-tap` 저장소의 `Formula/herdr-space-dividers.rb`에 배포합니다. 로컬 설치 확인용 `file://` formula는 공개하지 않습니다.
