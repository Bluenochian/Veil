"""Local Unix-socket messaging for Veil's service and native host."""

import os
import socket
import json
import threading
import select
from pathlib import Path
from typing import Callable, Any


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
        if cls.DEFAULT_SOCKET_DIR.parent.exists():
            cls.DEFAULT_SOCKET_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            return cls.DEFAULT_SOCKET_DIR / "veil.sock"
        cls.FALLBACK_SOCKET_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        return cls.FALLBACK_SOCKET_DIR / "veil.sock"

    def start(self):
        if self.running:
            return

        if self.socket_path.exists():
            # Check whether another process owns the socket before cleaning anything up.
            test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            is_active = False
            try:
                test_sock.settimeout(0.5)
                test_sock.connect(str(self.socket_path))
                is_active = True
            except OSError:
                is_active = False
            finally:
                try:
                    test_sock.close()
                except Exception:
                    pass

            if is_active:
                # Never pretend a second daemon owns the active socket. Doing so
                # leaves a second tray reporting protection it cannot enforce.
                raise RuntimeError(f"A Veil daemon is already listening on {self.socket_path}")

            # Stale socket? Fine, its safe to remove.
            try:
                self.socket_path.unlink()
            except OSError:
                pass

        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.server_socket.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        self.server_socket.listen(16)
        self.running = True
        self._owns_socket = True

        # Ensure fallback path symlinks or points to active socket
        try:
            fallback = self.FALLBACK_SOCKET_DIR / "veil.sock"
            if fallback != self.socket_path:
                self.FALLBACK_SOCKET_DIR.mkdir(parents=True, exist_ok=True)
                if fallback.exists() or fallback.is_symlink():
                    fallback.unlink()
                fallback.symlink_to(self.socket_path)
        except Exception:
            pass

        self._thread = threading.Thread(target=self._accept_loop, daemon=True, name="veil-ipc-accept")
        self._thread.start()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        with self._lock:
            for client in self.clients:
                try:
                    client.close()
                except Exception:
                    pass
            self.clients.clear()

        if self._owns_socket:
            try:
                fallback = self.FALLBACK_SOCKET_DIR / "veil.sock"
                if fallback != self.socket_path and (fallback.exists() or fallback.is_symlink()):
                    fallback.unlink()
            except Exception:
                pass

            if self.socket_path.exists():
                try:
                    self.socket_path.unlink()
                except OSError:
                    pass
            self._owns_socket = False

    def _accept_loop(self):
        while self.running and self.server_socket:
            try:
                client_sock, _ = self.server_socket.accept()
                # One stuck extension shoudnt block updates to all the others.
                client_sock.settimeout(0.25)
                with self._lock:
                    self.clients.append(client_sock)
                t = threading.Thread(target=self._client_handler, args=(client_sock,), daemon=True)
                t.start()
            except OSError:
                break

    def _client_handler(self, client_sock: socket.socket):
        buffer = ""
        while self.running:
            try:
                data = client_sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                if len(buffer) > 1024 * 1024:
                    break  # Malformed or abusive client; avoid unbounded buffering.
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    response = None
                    if self.on_message:
                        response = self.on_message(msg, client_sock)
                    if response is not None:
                        if isinstance(msg, dict) and "request_id" in msg:
                            response = dict(response)
                            response["request_id"] = msg["request_id"]
                        resp_data = json.dumps(response).encode("utf-8") + b"\n"
                        with self._send_lock:
                            client_sock.sendall(resp_data)
            except socket.timeout:
                continue  # Idle native host connections are expected.
            except (ConnectionResetError, BrokenPipeError, OSError):
                break
            except Exception:
                break

        with self._lock:
            if client_sock in self.clients:
                self.clients.remove(client_sock)
        try:
            client_sock.close()
        except Exception:
            pass

    def broadcast(self, message: dict):
        """Broadcast a JSON message to connected clients."""
        msg_bytes = json.dumps(message).encode("utf-8") + b"\n"
        with self._lock:
            dead_clients = []
            for client in self.clients:
                try:
                    with self._send_lock:
                        client.sendall(msg_bytes)
                except Exception:
                    dead_clients.append(client)
            for dead in dead_clients:
                if dead in self.clients:
                    self.clients.remove(dead)
                try:
                    dead.close()
                except Exception:
                    pass


class IPCClient:
    """Helper client to communicate with Veil IPC Server."""
    def __init__(self, socket_path: Path | None = None):
        self.socket_path = Path(socket_path) if socket_path else IPCServer._get_default_socket_path()
        self.sock: socket.socket | None = None
        self._receive_buffer = ""
        self._expected_request_id = None

    def connect(self, timeout: float = 2.0) -> bool:
        candidate_paths = [
            self.socket_path,
            Path(f"/run/user/{os.getuid()}") / "veil" / "veil.sock",
            Path.home() / ".config" / "veil" / "veil.sock"
        ]
        for p in candidate_paths:
            if p and p.exists():
                try:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.settimeout(timeout)
                    self.sock.connect(str(p))
                    return True
                except Exception:
                    if self.sock:
                        try:
                            self.sock.close()
                        except Exception:
                            pass
                    self.sock = None
        return False

    def send(self, message: dict):
        if not self.sock:
            return
        import uuid
        outgoing = dict(message)
        outgoing.setdefault("request_id", "cli-" + uuid.uuid4().hex)
        self._expected_request_id = outgoing["request_id"]
        self.sock.sendall(json.dumps(outgoing).encode("utf-8") + b"\n")

    def receive(self, timeout: float = 3.0) -> dict | None:
        if not self.sock:
            return None
        import time
        deadline = time.monotonic() + timeout
        while True:
            while "\n" in self._receive_buffer:
                line, self._receive_buffer = self._receive_buffer.split("\n", 1)
                try:
                    response = json.loads(line.strip())
                except (ValueError, TypeError):
                    continue
                if self._expected_request_id is not None:
                    if response.get("request_id") != self._expected_request_id:
                        continue  # Ignore unrelated server broadcasts while awaiting a reply.
                    self._expected_request_id = None
                return response
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            self.sock.settimeout(remain)
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    return None
                self._receive_buffer += chunk.decode("utf-8", errors="replace")
            except (socket.timeout, OSError):
                return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
