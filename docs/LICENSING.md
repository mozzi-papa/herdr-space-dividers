# 라이선스 범위

| 파일 | 라이선스 |
|---|---|
| `update-custom.sh`, `run.sh`, `bin/`, `smoke_mvp.py`, `tools/` | [MIT](../LICENSE) |
| 이 저장소의 문서, `assets/`, `VERSION`과 `.gitignore` | [MIT](../LICENSE) |
| `patches/sidebar.patch`, `patches/manifest.json` | [Apache-2.0](../licenses/Apache-2.0.txt) |
| 별도로 내려받는 Herdr와 빌드 의존성 | 각 원본 프로젝트의 라이선스 |
| `licenses/third-party/`의 원본 고지 사본 | 각 파일에 적힌 원본 라이선스 |

`licenses/crate-license-sources.json`은 누락된 의존성 고지의 원본 URL·커밋·SHA-256을 기록합니다. 고지 사본에 프로젝트 루트의 MIT를 다시 적용하지 않습니다.

루트 `LICENSE`는 독립 도구와 문서에 적용합니다. Herdr 원본 코드까지 MIT만 적용되는 것으로 해석하지 말아 주세요. MIT와 Apache-2.0의 고지·라이선스 조건을 유지하면서 사용·수정·재배포할 수 있습니다.

패치에는 [Herdr v0.9.5](https://github.com/herdrdev/herdr/tree/v0.9.5)의 원본 문맥과 변경 내용이 포함됩니다. `NOTICE`와 Apache 라이선스 사본을 함께 제공하며, 패치를 적용한 각 변경 파일의 앞부분에 수정 고지를 추가합니다. 원본의 저작권·출처 고지는 계속 적용됩니다.

기여한 코드는 해당 파일의 라이선스를 따릅니다. 다른 프로젝트의 코드를 가져올 때는 사용 권한과 고지를 확인하고 해당 라이선스를 함께 보존해 주세요. 실행 파일이나 의존성을 별도로 배포한다면 그 배포물의 라이선스와 고지 의무도 확인해야 합니다.

이 프로젝트는 Herdr와 제휴하거나 공식 승인을 받은 프로젝트가 아닙니다. Herdr 명칭은 기반 프로젝트를 설명하기 위해 사용합니다. 보증과 책임 제한은 각 라이선스 본문을 참고해 주세요.

릴리스 아카이브에는 패치가 적용된 Herdr 실행 파일을 포함합니다. 해당 파일에는 Herdr의 Apache-2.0과 의존성의 라이선스가 적용됩니다. `share/herdr-space-dividers/third-party/`에 Rust 의존성과 vendored 소스의 고지를 수집하며, 추가 고지에는 빌드 소스용 고지도 포함될 수 있습니다. 시스템 프레임워크는 함께 배포하지 않습니다.
