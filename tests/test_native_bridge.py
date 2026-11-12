"""Real stdio native-host -> AF_UNIX daemon protocol smoke test."""
import json
import os
import select
import struct
import subprocess
import sys
import time
from pathlib import Path

from veil.ipc_server import IPCServer
from veil.service import VeilService


def read_frame(fd, timeout=4):
    def read_exact(size):
        out = b''
        limit = time.monotonic() + timeout
        while len(out) < size:
            remain = limit - time.monotonic()
            assert remain > 0, 'Native host timed out'
            ready, _, _ = select.select([fd], [], [], remain)
            assert ready, 'No native host stdout'
            part = os.read(fd, size - len(out))
            assert part, 'Native host pipe closed unexpectedly'
            out += part
        return out
    length, = struct.unpack('@I', read_exact(4))
    assert 0 < length < 1024 * 1024
    return json.loads(read_exact(length))


def test_native_stdio_uses_daemon_state_and_correlates_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(IPCServer, 'FALLBACK_SOCKET_DIR', tmp_path)
    socket_path = tmp_path / 'bridge.sock'
    service = VeilService(vault_dir=tmp_path / 'vault', socket_path=socket_path, start_ipc=True)
    script = '''
import os
from pathlib import Path
import veil.native_host.host as h
h.get_candidate_socket_paths = lambda: [Path(os.environ['VEIL_TEST_SOCKET'])]
h.run_bridge()
'''
    env = dict(os.environ, VEIL_TEST_SOCKET=str(socket_path))
    proc = subprocess.Popen([sys.executable, '-u', '-c', script], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        # The bridge must initiate authoritative state synchronization automatically.
        initial = read_frame(proc.stdout.fileno())
        assert initial['type'] == 'state'
        assert initial['active'] is False

        message = json.dumps({'type': 'get_state', 'request_id': 'ext-123'}).encode('utf8')
        proc.stdin.write(struct.pack('@I', len(message)) + message)
        proc.stdin.flush()
        reply = read_frame(proc.stdout.fileno())
        assert reply['request_id'] == 'ext-123'
        assert reply['type'] == 'state'
        assert reply['active'] is False

        service.activate()
        notice = read_frame(proc.stdout.fileno())
        assert notice['type'] == 'state' and notice['active'] is True
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)
        proc.stdout.close()
        proc.stderr.close()
        service.stop()
