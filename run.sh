#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 KangUnMo
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
if [ ! -S "$api_socket" ]; then
    printf '%s\n' '기존 기본 Herdr 서버를 찾을 수 없습니다. 공식 herdr를 먼저 실행해 주세요.' >&2
    exit 1
fi
# 실행 중인 서버와의 호환성은 선택된 Herdr 클라이언트가 확인합니다.
exec env -u HERDR_CLIENT_SOCKET_PATH \
    HERDR_CONFIG_PATH="$HOME/.config/herdr/config.toml" \
    HERDR_SOCKET_PATH="$api_socket" \
    "$binary"
