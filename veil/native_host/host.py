"""Wire a browser's native-messaging pipe to the local Veil socket."""

import json
import os
import queue
import socket
import struct
import sys
import threading
import time
from pathlib import Path


MAX_FRAME = 1024 * 1024
_stdout_lock = threading.Lock()


def log_debug(message: str):
    # This log must never contain browser URLs or passwords.
    try:
        folder = Path.home() / ".config" / "veil"
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(folder / "native_host.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as file:
            file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def read_message() -> dict | None:
    try:
        prefix = sys.stdin.buffer.read(4)
        if len(prefix) != 4:
            return None
        length = struct.unpack("@I", prefix)[0]
        if length > MAX_FRAME:
            log_debug("Native message exceeded size limit")
            return None
        payload = sys.stdin.buffer.read(length)
        if len(payload) != length:
            return None
        result = json.loads(payload)
        return result if isinstance(result, dict) else None
    except (OSError, ValueError, UnicodeError) as exc:
        log_debug(f"Cannot read native message: {type(exc).__name__}")
        return None


def send_message(message: dict):
    try:
        payload = json.dumps(message).encode("utf-8")
        if len(payload) > MAX_FRAME:
            log_debug("Native reply exceeded size limit")
            return
        with _stdout_lock:
            sys.stdout.buffer.write(struct.pack("@I", len(payload)))
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
    except (OSError, ValueError, TypeError) as exc:
        log_debug(f"Cannot send native message: {type(exc).__name__}")


def get_candidate_socket_paths() -> list[Path]:
    return [
        Path(f"/run/user/{os.getuid()}/veil/veil.sock"),
        Path.home() / ".config" / "veil" / "veil.sock",
    ]


def connect_socket() -> socket.socket | None:
    for path in get_candidate_socket_paths():
        if not path.exists():
            continue
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            peer.connect(str(path))
            return peer
        except OSError:
            peer.close()
    return None


class NativeBridge:
    def __init__(self):
        self._stopping = threading.Event()
        self._peer: socket.socket | None = None
        self._peer_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._pending: queue.Queue[dict] = queue.Queue(maxsize=2048)

    def _current_peer(self):
        with self._peer_lock:
            return self._peer

    def _disconnect(self, peer):
        with self._peer_lock:
            if self._peer is peer:
                self._peer = None
        try:
            peer.close()
        except OSError:
            pass

    def _connect_loop(self):
        while not self._stopping.is_set():
            if self._current_peer() is None:
                peer = connect_socket()
                if peer:
                    with self._peer_lock:
                        self._peer = peer
                    try:
                        with self._send_lock:
                            peer.sendall(b'{"type":"get_state"}\n')
                    except OSError:
                        self._disconnect(peer)
            self._stopping.wait(1.0)

    def _read_loop(self):
        buffer = b""
        last_peer = None
        while not self._stopping.is_set():
            peer = self._current_peer()
            if peer is None:
                self._stopping.wait(0.2)
                continue
            if peer is not last_peer:
                buffer = b""
                last_peer = peer
            try:
                chunk = peer.recv(4096)
                if not chunk:
                    raise ConnectionError("socket closed")
                buffer += chunk
                if len(buffer) > MAX_FRAME:
                    raise ValueError("too much data from service")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        reply = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    if isinstance(reply, dict):
                        send_message(reply)
            except (OSError, ConnectionError, ValueError):
                self._disconnect(peer)
                buffer = b""
                self._stopping.wait(0.3)

    def _write_loop(self):
        retry = None
        while not self._stopping.is_set():
            if retry is None:
                try:
                    retry = self._pending.get(timeout=0.2)
                except queue.Empty:
                    continue

            peer = self._current_peer()
            if peer is None:
                self._stopping.wait(0.2)
                continue
            try:
                with self._send_lock:
                    peer.sendall(json.dumps(retry).encode("utf-8") + b"\n")
                retry = None
            except (OSError, ValueError, TypeError):
                self._disconnect(peer)
                self._stopping.wait(0.3)

    def run(self):
        for task in (self._connect_loop, self._read_loop, self._write_loop):
            threading.Thread(target=task, daemon=True).start()
        try:
            while True:
                message = read_message()
                if message is None:
                    return
                self._pending.put(message)
        except KeyboardInterrupt:
            pass
        finally:
            self._stopping.set()
            peer = self._current_peer()
            if peer:
                self._disconnect(peer)


def run_bridge():
    NativeBridge().run()


if __name__ == "__main__":
    run_bridge()
