"""Password for turning Veil off. The vault's encryption key is a different thing."""

import base64
import hashlib
import hmac
import json
import os
import stat
import tempfile
import threading
import time
from pathlib import Path


class AccessDenied(PermissionError):
    pass


class UnlockGuard:
    NAME = "unlock-password.json"
    MIN_LENGTH = 12
    MAX_PASSWORD_LENGTH = 1024
    MAX_FILE_SIZE = 4096
    COOLDOWN = 30

    # Changing these would make existing passwords impossible to verify.
    N, R, P = 2 ** 15, 8, 1

    def __init__(self, config_dir: Path):
        self.folder = Path(config_dir)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.folder / self.NAME
        self._lock = threading.RLock()
        self._failures = 0
        self._locked_until = 0.0

    def _read(self):
        """Return the salt and verifier, not the password itself."""
        if self.path.is_symlink():
            raise AccessDenied("The unlock file is a symlink. I won't use it.")

        # Check the opened file too. Checking the path alone leaves a race
        # where something else could swap it for a link before open().
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise AccessDenied("Can't open the unlock settings. Veil stays on.") from exc

        try:
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError("not a file")
                data = handle.read(self.MAX_FILE_SIZE + 1)

            if len(data) > self.MAX_FILE_SIZE:
                raise ValueError("file too big")
            saved = json.loads(data)
            if not isinstance(saved, dict) or saved.get("v") != 1:
                raise ValueError("unknown unlock format")
            salt = base64.b64decode(saved["salt"], validate=True)
            verifier = base64.b64decode(saved["hash"], validate=True)
            if len(salt) != 16 or len(verifier) != 32:
                raise ValueError("wrong verifier size")
            return salt, verifier
        except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise AccessDenied("Unlock settings look damaged. I won't turn Veil off.") from exc

    @property
    def configured(self):
        return self._read() is not None

    @classmethod
    def _derive(cls, password, salt):
        return hashlib.scrypt(
            password.encode("utf-8"), salt=salt,
            n=cls.N, r=cls.R, p=cls.P, dklen=32, maxmem=64 * 1024 * 1024,
        )

    def verify(self, password):
        with self._lock:
            saved = self._read()
            if saved is None:
                raise AccessDenied("Set an unlock password first (Veil Preferences or 'veil lock set').")
            if time.monotonic() < self._locked_until:
                raise AccessDenied("Too many attempts. Try again after 30 seconds.")
            if not isinstance(password, str) or not password:
                raise AccessDenied("Unlock password required. Veil stays on.")
            if len(password) > self.MAX_PASSWORD_LENGTH:
                raise AccessDenied("Unlock password is too long.")

            salt, verifier = saved
            if not hmac.compare_digest(self._derive(password, salt), verifier):
                self._failures += 1
                if self._failures >= 5:
                    self._failures = 0
                    self._locked_until = time.monotonic() + self.COOLDOWN
                    raise AccessDenied("Too many attempts. Try again after 30 seconds.")
                raise AccessDenied("Incorrect password. Try again.")

            self._failures = 0
            self._locked_until = 0.0
            return True

    def set_password(self, password, current=None):
        with self._lock:
            if self._read() is not None:
                self.verify(current)
            if not isinstance(password, str) or len(password) < self.MIN_LENGTH:
                raise AccessDenied("Use an unlock password of at least 12 characters.")
            if len(password) > self.MAX_PASSWORD_LENGTH:
                raise AccessDenied("Unlock password is too long.")

            salt = os.urandom(16)
            record = {
                "v": 1,
                "kdf": "scrypt",
                "salt": base64.b64encode(salt).decode("ascii"),
                "hash": base64.b64encode(self._derive(password, salt)).decode("ascii"),
            }

            # No writing over the existing file. A failed password change
            # should leave the previous password working.
            temp_path = None
            try:
                fd, temp_path = tempfile.mkstemp(prefix=".unlock-", dir=self.folder)
                with os.fdopen(fd, "w", encoding="ascii") as handle:
                    os.fchmod(handle.fileno(), 0o600)
                    json.dump(record, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
                temp_path = None
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)

            self._failures = 0
            self._locked_until = 0.0
