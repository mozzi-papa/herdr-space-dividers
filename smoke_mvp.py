# SPDX-License-Identifier: MIT
# Copyright (c) 2026 mozzi-papa
"""별도 서버와 가상 터미널에서 구분 행 MVP를 검증합니다."""
import base64
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import socket
import struct
import subprocess
import tempfile
import termios
import time
import unicodedata

root = Path(__file__).resolve().parent
binary = Path(os.environ.get('HERDR_MVP_BINARY', root / 'current/herdr')).resolve()
reconnect_binary = Path(os.environ.get('HERDR_MVP_RECONNECT_BINARY', binary)).resolve()
log_dir = Path(os.environ.get('HERDR_MVP_LOG_DIR', root))
log_dir.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='herdr-div-mvp-') as temp:
    area = Path(temp)
    config = area / 'config.toml'
    config.write_text('onboarding = false\n[keys]\nswitch_workspace = "cmd+1..9"\n')
    env = os.environ.copy()
    for key in ['HERDR_ENV', 'HERDR_SOCKET_PATH', 'HERDR_CLIENT_SOCKET_PATH', 'HERDR_PANE_ID', 'HERDR_TAB_ID', 'HERDR_WORKSPACE_ID']:
        env.pop(key, None)
    env.update(VSCODE_IPC_HOOK_CLI='herdr-isolated-clipboard-test', HERDR_CONFIG_PATH=str(config), HERDR_SOCKET_PATH=str(area/'herdr.sock'),
               XDG_CONFIG_HOME=str(area/'config'), XDG_STATE_HOME=str(area/'state'), TERM='xterm-256color', SHELL='/bin/sh', ZDOTDIR=str(area), ENV='/dev/null')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
    def controlling_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    process = subprocess.Popen([str(binary)], stdin=slave, stdout=slave, stderr=slave,
                               env=env, cwd=area, preexec_fn=controlling_terminal)
    os.close(slave)
    output = bytearray()
    def drain(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([master], [], [], min(.1, max(0,end-time.monotonic())))[0]:
                try: output.extend(os.read(master, 65536))
                except OSError: break
    def sidebar_title_row(character):
        row, column, found = 1, 1, None
        text = output.decode('utf-8', errors='replace')
        for match in re.finditer(r'\x1b\][\s\S]*?(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|.', text, re.S):
            token = match.group()
            if token.startswith('\x1b['):
                if token[-1] in 'Hf':
                    parts = token[2:-1].split(';')
                    row = int(parts[0] or '1')
                    column = int(parts[1] or '1') if len(parts) > 1 else 1
            elif token.startswith('\x1b'):
                continue
            elif token == '\r': column = 1
            elif token == '\n': row += 1
            else:
                if token == character and column < 25: found = row
                column += 0 if unicodedata.combining(token) else (2 if unicodedata.east_asian_width(token) in 'WF' else 1)
        assert found is not None, character
        return found
    def drag_space_into(title):
        # 구분선이 있으면 맨 위 `미분류` 헤더 바로 아래 행이 첫 미분류 스페이스입니다.
        space, target = sidebar_title_row('미') + 1, sidebar_title_row(title)
        os.write(master, f'\x1b[<0;6;{space}M\x1b[<32;6;{target}M\x1b[<0;6;{target}m'.encode())
        drain(.3)
    def click(button, row):
        os.write(master, f'\x1b[<{button};6;{row}M\x1b[<{button};6;{row}m'.encode())
    def saved_preferences():
        files = list((area/'state/herdr-dev/client-shell').glob('*.json'))
        assert len(files) == 1, files
        return json.loads(files[0].read_text())
    def rpc(method, params):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(5)
            client.connect(str(area/'herdr.sock'))
            client.sendall((json.dumps({'id':'mvp-smoke','method':method,'params':params})+'\n').encode())
            response=json.loads(client.makefile().readline())
            assert 'error' not in response, response
            return response['result']
    try:
        drain(3)
        assert process.poll() is None, output[-2000:]
        assert b'div' in output, output[-2000:]
        before = rpc('session.snapshot', {})['snapshot']
        os.write(master, b'\x1b[<0;8;20M\x1b[<0;8;20m')
        drain(.5)
        visible = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output.decode('utf-8', errors='replace')).replace(' ', '')
        assert '구분선' in visible, visible[-1500:]
        os.write(master, '업무'.encode()+b'\r')
        drain(.8)
        assert '업'.encode() in output and '무'.encode() in output
        assert saved_preferences()['dividers'] == [{'position': 1, 'title': '업무', 'members': [], 'collapsed': False}]
        # 실제 출력된 행을 읽어 좌표를 정하고, 미분류 스페이스를 구분선 제목에 끌어 넣습니다.
        drag_space_into('업')
        assert saved_preferences()['dividers'][0]['position'] == 0
        assert saved_preferences()['dividers'][0]['members'] == [before['focused_workspace_id']]
        click(0, sidebar_title_row('업'))
        drain(.3)
        assert saved_preferences()['dividers'][0]['collapsed'] is True
        os.write(master, b'\x1b[49;9u')
        drain(.3)
        assert saved_preferences()['dividers'][0]['collapsed'] is False
        click(2, sidebar_title_row('업'))
        drain(.3)
        os.write(master, b'\r')
        drain(.2)
        os.write(master, b'\x15' + '변경 이름'.encode() + b'\r')
        drain(.3)
        assert saved_preferences()['dividers'] == [{'position': 0, 'title': '변경 이름', 'members': [before['focused_workspace_id']], 'collapsed': False}]
        click(2, sidebar_title_row('변'))
        drain(.2)
        os.write(master, b'\x1b[B\r')
        drain(.3)
        assert not saved_preferences().get('dividers')
        click(2, 3)
        drain(.3)
        visible = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output.decode('utf-8', errors='replace')).replace(' ', '')
        assert 'Finder에서폴더열기' in visible
        assert '폴더경로복사' in visible
        os.write(master, b'\x1b[B' * 3 + b'\r')
        drain(.3)
        assert b'\x1b]52;c;' + base64.b64encode(str(area.resolve()).encode()) in output
        # 구분선을 남기고 새 클라이언트 프로세스로 재접속합니다.
        os.write(master, b'\x1b[<0;8;20M\x1b[<0;8;20m')
        drain(.2)
        os.write(master, '복원'.encode() + b'\r')
        drain(.5)
        preference_files = list((area/'state/herdr-dev/client-shell').glob('*.json'))
        assert len(preference_files) == 1, preference_files
        saved = json.loads(preference_files[0].read_text())
        assert saved['dividers'] == [{'position': 1, 'title': '복원', 'members': [], 'collapsed': False}], saved
        drag_space_into('복')
        assert saved_preferences()['dividers'][0]['members'] == [before['focused_workspace_id']]
        click(0, sidebar_title_row('복'))
        drain(.3)
        assert saved_preferences()['dividers'][0]['collapsed'] is True
        os.write(master, b'\x02q')
        drain(.7)
        process.wait(timeout=3)
        os.close(master)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
        process = subprocess.Popen([str(reconnect_binary)], stdin=slave, stdout=slave, stderr=slave,
                                   env=env, cwd=area, preexec_fn=controlling_terminal)
        os.close(slave)
        output.clear()
        drain(2)
        visible = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output.decode('utf-8', errors='replace')).replace(' ', '')
        assert '복원' in visible, visible[-1500:]
        assert saved_preferences()['dividers'][0]['collapsed'] is True
        assert saved_preferences()['dividers'][0]['members'] == [before['focused_workspace_id']]
        print('PASS: 분류 ID·접기 저장, 숫자 이동 자동 펼치기, 새 클라이언트 재접속 복원')
        after = rpc('session.snapshot', {})['snapshot']
        for key in ['workspaces','tabs','panes','agents']:
            assert len(before[key]) == len(after[key]), key
        print('Focus:', before['focused_workspace_id'], after['focused_workspace_id'])
        assert before['focused_workspace_id'] == after['focused_workspace_id']
        assert [p['pane_id'] for p in before['panes']] == [p['pane_id'] for p in after['panes']]
        print('Counts:', {key: (len(before[key]), len(after[key])) for key in ['workspaces','tabs','panes','agents']})
        (log_dir/'mvp-smoke.ansi').write_bytes(output)
        print('PASS: 생성·드래그·우클릭 편집·폴더 메뉴·경로 복사, 기존 스페이스/페인 ID 및 개수 유지')
    finally:
        try:
            (log_dir/'mvp-smoke.ansi').write_bytes(output)
            for log in area.rglob('herdr-server.log'):
                (log_dir/'smoke-server.log').write_bytes(log.read_bytes())
        finally:
            # 로그 저장이 실패해도 이 스크립트의 임시 소켓 서버는 종료합니다.
            try: rpc('server.stop', {})
            except (OSError, AssertionError): pass
            drain(1)
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                drain(.5)
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            os.close(master)
