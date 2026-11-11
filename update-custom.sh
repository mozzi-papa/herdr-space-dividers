#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 mozzi-papa
set -eu
base_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! python3 -c 'import sys, tarfile; sys.exit(sys.version_info < (3, 11) or not hasattr(tarfile, "data_filter"))'; then
    printf '%s\n' 'Python 3.11 이상과 tarfile 추출 필터 지원이 필요합니다. 최신 Python 3로 다시 실행해 주세요.' >&2
    exit 1
fi
exec python3 "$base_dir/tools/update_custom.py" "$@"
