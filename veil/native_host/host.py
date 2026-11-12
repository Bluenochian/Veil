"""Pass browser native-messaging requests to the local Veil service."""

import sys
import os
import time
import struct
import json
import socket
import threading
import queue
from pathlib import Path


def log_debug(msg: str):
    try:
        config_dir = Path.home() / ".config" / "veil"
        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        log_file = config_dir / "native_host.log"
        fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def read_message() -> dict | None:
    try:
        raw_len = sys.stdin.buffer.read(4)
        if not raw_len or len(raw_len) < 4:
            return None
        msg_len = struct.unpack("@I", raw_len)[0]
        if msg_len > 1024 * 1024:
            log_debug("Rejected oversized native message")
            return None
        msg_bytes = sys.stdin.buffer.read(msg_len)
        if not msg_bytes or len(msg_bytes) < msg_len:
            return None
        return json.loads(msg_bytes.decode("utf-8"))
    except Exception as e:
        log_debug(f"read_message error: {e}")
        return None


_stdout_lock = threading.Lock()


def send_message(msg: dict):
    try:
        raw = json.dumps(msg).encode("utf-8")
        with _stdout_lock:
            sys.stdout.buffer.write(struct.pack("@I", len(raw)))
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()
    except Exception as e:
        log_debug(f"send_message error: {e}")


def get_candidate_socket_paths() -> list[Path]:
    uid = os.getuid()
    return [
        Path(f"/run/user/{uid}/veil/veil.sock"),
        Path.home() / ".config" / "veil" / "veil.sock"
    ]


def connect_socket() -> socket.socket | None:
    for p in get_candidate_socket_paths():
        if p.exists():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(str(p))
                return s
            except OSError:
                try:
                    s.close()
                except Exception:
                    pass
    return None


def run_bridge():
    running = True
    sock: socket.socket | None = None
    sock_lock = threading.Lock()
    socket_send_lock = threading.Lock()
    outbox: queue.Queue = queue.Queue(maxsize=2048)

    def maintain_socket_connection():
        nonlocal sock, running
        while running:
            with sock_lock:
                current_sock = sock

            if current_sock is None:
                new_sock = connect_socket()
                if new_sock:
                    with sock_lock:
                        sock = new_sock
                    try:
                        handshake = json.dumps({"type": "get_state"}).encode("utf-8") + b"\n"
                        with socket_send_lock:
                            new_sock.sendall(handshake)
                    except Exception:
                        pass
            time.sleep(1.0)

    def reader_from_daemon():
        nonlocal sock, running
        buf = ""
        while running:
            with sock_lock:
                current_sock = sock

            if current_sock is None:
                time.sleep(0.2)
                continue

            try:
                data = current_sock.recv(4096)
                if not data:
                    with sock_lock:
                        if sock is current_sock:
                            sock = None
                    current_sock.close()
                    buf = ""
                    continue
                buf += data.decode("utf-8")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if line.strip():
                        try:
                            parsed = json.loads(line)
                            send_message(parsed)
                        except Exception:
                            pass
            except Exception:
                with sock_lock:
                    if sock is current_sock:
                        sock = None
                try:
                    current_sock.close()
                except OSError:
                    pass
                buf = ""
                time.sleep(0.5)

    def sender_to_daemon():
        nonlocal sock, running
        while running:
            try:
                msg = outbox.get(timeout=0.2)
            except queue.Empty:
                continue

            with sock_lock:
                current_sock = sock

            if current_sock is not None:
                try:
                    with socket_send_lock:
                        current_sock.sendall(json.dumps(msg).encode("utf-8") + b"\n")
                except Exception:
                    with sock_lock:
                        if sock is current_sock:
                            sock = None
                    try:
                        current_sock.close()
                    except OSError:
                        pass
                    outbox.put(msg)
                    time.sleep(0.5)
            else:
                outbox.put(msg)
                time.sleep(0.5)

    t_maint = threading.Thread(target=maintain_socket_connection, daemon=True)
    t_reader = threading.Thread(target=reader_from_daemon, daemon=True)
    t_sender = threading.Thread(target=sender_to_daemon, daemon=True)

    t_maint.start()
    t_reader.start()
    t_sender.start()

    try:
        while True:
            msg = read_message()
            if msg is None:
                break
            outbox.put(msg)
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        with sock_lock:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


if __name__ == "__main__":
    run_bridge()
