#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 mozzi-papa
set -eu
base_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
binary="$base_dir/current/herdr"
if [ "${HERDR_ENV:-}" = 1 ]; then
    printf '%s\n' '먼저 Ctrl+B 다음 q로 Herdr 화면에서 분리한 뒤 다시 실행해 주세요. 작업은 계속 실행됩니다.' >&2
    exit 1
fi
if [ ! -x "$binary" ]; then
    printf '%s\n' '수정본이 없습니다. 먼저 sh update-custom.sh 0.9.5를 실행해 주세요.' >&2
    exit 1
fi
api_socket="$HOME/.config/herdr/herdr.sock"
official=
for candidate in "$HOME/.local/bin/herdr" "$(command -v herdr 2>/dev/null || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        official=$candidate
        break
    fi
done
# 소켓 파일은 재부팅 뒤에도 남으므로 서버가 살아 있다는 증거가 아닙니다. 실제 응답으로 확인합니다.
server_running() {
    [ -n "$official" ] || return 1
    env -u HERDR_SOCKET_PATH -u HERDR_CLIENT_SOCKET_PATH -u HERDR_CONFIG_PATH \
        "$official" status server 2>/dev/null | grep -qx 'status: running'
}
if ! server_running; then
    if [ -z "$official" ]; then
        printf '%s\n' '공식 herdr를 찾을 수 없어 서버를 시작하지 못했습니다.' \
            '터미널에서 command herdr 를 먼저 실행해 서버를 시작한 뒤 다시 실행해 주세요.' >&2
        exit 1
    fi
    printf '%s\n' '공식 Herdr 서버가 응답하지 않아 시작합니다. 저장된 세션을 복원합니다...' >&2
    # 소스 빌드(debug)는 서버가 되면 ~/.config/herdr-dev를 써서 기존 세션이 복원되지 않으므로,
    # 서버는 항상 공식 실행 파일로만 시작합니다. 새 세션(setsid)으로 분리해 이 명령이 끝나도 살아남습니다.
    (cd "$HOME" && exec env -u HERDR_SOCKET_PATH -u HERDR_CLIENT_SOCKET_PATH -u HERDR_CONFIG_PATH \
        perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV' "$official" server \
        </dev/null >/dev/null 2>&1) &
    tries=0
    until server_running; do
        tries=$((tries + 1))
        if [ "$tries" -ge 40 ]; then
            printf '%s\n' '공식 Herdr 서버가 20초 안에 시작되지 않았습니다.' \
                '~/.config/herdr/herdr-server.log를 확인하거나 command herdr 로 순정 Herdr를 직접 실행해 주세요.' >&2
            exit 1
        fi
        sleep 0.5
    done
fi
# 실행 중인 서버와의 호환성은 선택된 Herdr 클라이언트가 확인합니다.
exec env -u HERDR_CLIENT_SOCKET_PATH \
    HERDR_CONFIG_PATH="$HOME/.config/herdr/config.toml" \
    HERDR_SOCKET_PATH="$api_socket" \
    "$binary"
