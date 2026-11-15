"""Tiny line-delimited JSON socket between the desktop service and browser bridge."""

import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable


MAX_MESSAGE_BYTES = 1024 * 1024


class IPCServer:
    DEFAULT_SOCKET_DIR = Path(f"/run/user/{os.getuid()}") / "veil"
    FALLBACK_SOCKET_DIR = Path.home() / ".config" / "veil"

    def __init__(self, socket_path: Path | None = None,
                 on_message_callback: Callable[[dict, Any], dict | None] | None = None):
        self.socket_path = Path(socket_path) if socket_path else self._get_default_socket_path()
        self.on_message = on_message_callback
        self.server_socket: socket.socket | None = None
        self.running = False
        self._owns_socket = False
        self.clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @classmethod
    def _get_default_socket_path(cls) -> Path:
        folder = cls.DEFAULT_SOCKET_DIR
        if not folder.parent.exists():
            folder = cls.FALLBACK_SOCKET_DIR
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        return folder / "veil.sock"

    def start(self):
        if self.running:
            return

        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.socket_path.exists():
            # An old socket file is fine. A second running daemon isn't.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                try:
                    probe.connect(str(self.socket_path))
                except OSError:
                    self.socket_path.unlink(missing_ok=True)
                else:
                    raise RuntimeError(f"A Veil daemon is already listening on {self.socket_path}")

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            server.listen(16)
        except Exception:
            server.close()
            raise
        self.server_socket = server
        self._owns_socket = True
        self.running = True

        # The old config-directory socket is still used by some installations.
        try:
            fallback = self.FALLBACK_SOCKET_DIR / "veil.sock"
            if fallback != self.socket_path:
                self.FALLBACK_SOCKET_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
                if fallback.exists() or fallback.is_symlink():
                    fallback.unlink()
                fallback.symlink_to(self.socket_path)
        except OSError:
            pass

        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="veil-ipc-accept")
        self._thread.start()

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None

        with self._lock:
            open_clients = self.clients[:]
            self.clients.clear()
        for client in open_clients:
            client.close()

        if self._owns_socket:
            fallback = self.FALLBACK_SOCKET_DIR / "veil.sock"
            if fallback != self.socket_path and fallback.is_symlink():
                # Don't delete some unrelated file that happened to be there.
                try:
                    if fallback.resolve() == self.socket_path.resolve():
                        fallback.unlink()
                except OSError:
                    pass
            self.socket_path.unlink(missing_ok=True)
            self._owns_socket = False

    def _accept_loop(self):
        while self.running and self.server_socket:
            try:
                client, _ = self.server_socket.accept()
            except OSError:
                break
            client.settimeout(0.25)
            with self._lock:
                self.clients.append(client)
            threading.Thread(target=self._client_handler, args=(client,), daemon=True).start()

    def _client_handler(self, client: socket.socket):
        buffer = b""
        try:
            while self.running:
                try:
                    chunk = client.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_MESSAGE_BYTES:
                    break

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        request = json.loads(line)
                    except (UnicodeDecodeError, ValueError):
                        continue
                    if self.on_message is None:
                        continue
                    reply = self.on_message(request, client)
                    if reply is None:
                        continue
                    if isinstance(request, dict) and "request_id" in request:
                        reply = {**reply, "request_id": request["request_id"]}
                    packet = json.dumps(reply).encode("utf-8") + b"\n"
                    with self._send_lock:
                        client.sendall(packet)
        except (ConnectionError, OSError, TypeError, ValueError):
            pass
        finally:
            with self._lock:
                if client in self.clients:
                    self.clients.remove(client)
            client.close()

    def broadcast(self, message: dict):
        packet = json.dumps(message).encode("utf-8") + b"\n"
        with self._lock:
            for client in self.clients[:]:
                try:
                    with self._send_lock:
                        client.sendall(packet)
                except OSError:
                    self.clients.remove(client)
                    client.close()


class IPCClient:
    def __init__(self, socket_path: Path | None = None):
        self.socket_path = Path(socket_path) if socket_path else IPCServer._get_default_socket_path()
        self.sock: socket.socket | None = None
        self._receive_buffer = b""
        self._expected_request_id = None

    def connect(self, timeout: float = 2.0) -> bool:
        candidates = (
            self.socket_path,
            Path(f"/run/user/{os.getuid()}") / "veil" / "veil.sock",
            Path.home() / ".config" / "veil" / "veil.sock",
        )
        for path in dict.fromkeys(candidates):
            if not path.exists():
                continue
            peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                peer.settimeout(timeout)
                peer.connect(str(path))
            except OSError:
                peer.close()
                continue
            self.sock = peer
            return True
        return False

    def send(self, message: dict):
        if not self.sock:
            return
        outgoing = dict(message)
        outgoing.setdefault("request_id", "cli-" + uuid.uuid4().hex)
        self._expected_request_id = outgoing["request_id"]
        self.sock.sendall(json.dumps(outgoing).encode("utf-8") + b"\n")

    def receive(self, timeout: float = 3.0) -> dict | None:
        if not self.sock:
            return None
        deadline = time.monotonic() + timeout
        while True:
            while b"\n" in self._receive_buffer:
                line, self._receive_buffer = self._receive_buffer.split(b"\n", 1)
                try:
                    response = json.loads(line)
                except (UnicodeDecodeError, ValueError):
                    continue
                if not isinstance(response, dict):
                    continue
                if self._expected_request_id is not None:
                    if response.get("request_id") != self._expected_request_id:
                        continue  # State broadcast, not the reply we asked for.
                    self._expected_request_id = None
                return response

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(4096)
            except (socket.timeout, OSError):
                return None
            if not chunk:
                return None
            self._receive_buffer += chunk
            if len(self._receive_buffer) > MAX_MESSAGE_BYTES:
                return None

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None
