"""Encryption for vault records and passphrase-protected backups.

Local records use a per-installation key; exported backups use a separate
passphrase-derived key.
"""

import os
import stat
import base64
import fcntl
import hmac
import shutil
import socket
import subprocess
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import hashes


class VaultDecryptionError(ValueError):
    """A saved record could not be authenticated with the local vault key."""


class KeyringUnavailable(RuntimeError):
    """The user's desktop secret store is missing, locked, or unavailable."""


class SecretToolStore:
    """Access KDE Wallet/GNOME Keyring through freedesktop Secret Service.

    Secret bytes are piped to secret-tool on stdin, never in command arguments.
    """

    def __init__(self, config_dir: Path):
        self.attributes = (
            "application", "veil", "purpose", "live-vault-key",
            "vault", str(config_dir.resolve()),
        )

    def _run(self, args: list[str], *, secret: bytes | None = None,
             allow_missing: bool = False) -> bytes | None:
        if not shutil.which("secret-tool"):
            raise KeyringUnavailable(
                "Veil requires secret-tool (libsecret) and an unlocked KDE Wallet "
                "or GNOME Keyring. No vault key was changed."
            )
        try:
            process = subprocess.run(
                ["secret-tool", *args], input=secret,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=25, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise KeyringUnavailable(
                "Unable to contact the desktop keyring. Unlock your wallet "
                "and retry from your logged-in graphical session."
            ) from exc
        if process.returncode != 0:
            if allow_missing and process.returncode == 1 and not process.stderr.strip():
                return None
            raise KeyringUnavailable(
                "The desktop keyring is locked or inaccessible. Unlock KDE Wallet "
                "or GNOME Keyring and retry. The vault key was not modified."
            )
        return process.stdout

    def lookup(self) -> bytes | None:
        value = self._run(["lookup", *self.attributes], allow_missing=True)
        if value is None:
            return None
        try:
            key = base64.b64decode(value.strip(), altchars=b"-_", validate=True)
        except Exception as exc:
            raise KeyringUnavailable(
                "The saved Veil keyring entry is invalid; it was not replaced."
            ) from exc
        if len(key) != 32:
            raise KeyringUnavailable(
                "The saved Veil keyring entry has the wrong size; it was not replaced."
            )
        return key

    def store(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Refusing to store an invalid vault key")
        self._run(
            ["store", "--label=Veil encrypted vault key", *self.attributes],
            secret=base64.urlsafe_b64encode(key),
        )


class KeyManager:
    DEFAULT_CONFIG_DIR = Path.home() / ".config" / "veil"
    KEY_FILE_NAME = "veil.key"  # legacy plaintext file, for migration only
    STORE_CLASS = SecretToolStore

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = Path(config_dir) if config_dir is not None else self.DEFAULT_CONFIG_DIR
        self.key_path = self.config_dir / self.KEY_FILE_NAME
        self.marker_path = self.config_dir / ".keyring-initialized"
        self.lock_path = self.config_dir / ".keyring-init.lock"
        self._ensure_config_dir()
        self._store = self.STORE_CLASS(self.config_dir)
        self._key = self._get_or_create_key()

    def _ensure_config_dir(self) -> None:
        if self.config_dir.is_symlink():
            raise ValueError("Veil configuration directory must not be a symlink")
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config_dir.chmod(stat.S_IRWXU)

    def _read_legacy_key(self) -> bytes | None:
        if self.key_path.is_symlink():
            raise ValueError("Veil key file must not be a symlink")
        if not self.key_path.exists():
            return None
        fd = os.open(self.key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Veil key file must be a regular file")
            os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "rb", closefd=False) as handle:
                key = handle.read(33)
        finally:
            os.close(fd)
        if len(key) != 32:
            raise ValueError(
                "Veil encryption key is invalid: refusing to replace it and orphan the vault"
            )
        return key

    def _mark_initialized(self) -> None:
        if self.marker_path.is_symlink():
            raise ValueError("Veil keyring marker must not be a symlink")
        try:
            fd = os.open(
                self.marker_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
            )
        except FileExistsError:
            return
        with os.fdopen(fd, "wb") as handle:
            handle.write(b"freedesktop-secret-service\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _old_daemon_running(self) -> bool:
        candidates = [
            Path(f"/run/user/{os.getuid()}") / "veil" / "veil.sock",
            self.config_dir / "veil.sock",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.2)
                    sock.connect(str(path))
                    return True
            except OSError:
                pass
        return False

    def _get_or_create_key(self) -> bytes:
        # Protect first run from concurrent CLI and tray processes.
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open(self.lock_path, flags, 0o600)
        with os.fdopen(fd, "rb+") as locked:
            os.fchmod(locked.fileno(), 0o600)
            fcntl.flock(locked.fileno(), fcntl.LOCK_EX)
            legacy = self._read_legacy_key()
            current = self._store.lookup()  # fail closed if wallet unavailable

            if legacy is not None:
                if self._old_daemon_running():
                    raise KeyringUnavailable(
                        "Stop the running Veil tray/service before migrating "
                        "veil.key. The legacy key was preserved."
                    )
                if current is not None and not hmac.compare_digest(current, legacy):
                    raise KeyringUnavailable(
                        "The desktop wallet key and veil.key disagree. Neither "
                        "was changed. Back them up before attempting recovery."
                    )
                if current is None:
                    self._store.store(legacy)
                    current = self._store.lookup()
                if current is None or not hmac.compare_digest(current, legacy):
                    raise KeyringUnavailable(
                        "Migration verification failed. Original veil.key was preserved."
                    )
                self._mark_initialized()
                self.key_path.unlink()
                return legacy

            if current is not None:
                self._mark_initialized()
                return current

            if self.marker_path.exists() or (self.config_dir / "vault.db").exists():
                raise KeyringUnavailable(
                    "Veil's wallet key is missing but vault data or prior keyring "
                    "state exists. Refusing to create a new key. Unlock or restore "
                    "the original wallet first."
                )

            fresh = AESGCM.generate_key(bit_length=256)
            self._store.store(fresh)
            verified = self._store.lookup()
            if verified is None or not hmac.compare_digest(verified, fresh):
                raise KeyringUnavailable(
                    "New key could not be read back from the desktop wallet. "
                    "No vault was initialized."
                )
            self._mark_initialized()
            return fresh

    @property
    def key(self) -> bytes:
        return self._key


# Version 2 portable backups use scrypt (64 MiB, N=2^16, r=8, p=2).
# Version 1 backups used PBKDF2-HMAC-SHA256 with 100,000 iterations.
# Keep the old reader: users should never lose access to an existing backup.
MIN_BACKUP_PASSPHRASE_LENGTH = 16


def _backup_key(passphrase: str, salt: bytes, *, legacy: bool = False) -> bytes:
    if legacy:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000
        )
    else:
        kdf = Scrypt(salt=salt, length=32, n=2**16, r=8, p=2)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_with_passphrase(plaintext: str, passphrase: str) -> str:
    if not isinstance(passphrase, str) or len(passphrase.strip()) < MIN_BACKUP_PASSPHRASE_LENGTH:
        raise ValueError("Use a backup passphrase of at least 16 characters")
    salt = os.urandom(16)
    key = _backup_key(passphrase, salt)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(salt + nonce + ciphertext).decode("ascii")


def decrypt_with_passphrase(ciphertext_b64: str, passphrase: str, *, legacy: bool = False) -> str:
    # Invalid archives must fail before requesting costly key derivation.
    payload = base64.b64decode(ciphertext_b64.encode("ascii"), altchars=b"-_", validate=True)
    if len(payload) < 44:
        raise ValueError("Truncated encrypted backup")
    salt, nonce, ciphertext = payload[:16], payload[16:28], payload[28:]
    key = _backup_key(passphrase, salt, legacy=legacy)
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")


class VaultCrypto:
    def __init__(self, key_manager: KeyManager | None = None):
        self.km = key_manager or KeyManager()
        self.aesgcm = AESGCM(self.km.key)

    def encrypt_str(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        nonce = os.urandom(12)
        ct = self.aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def decrypt_str(self, ciphertext_b64: str) -> str:
        if not ciphertext_b64:
            return ""
        try:
            raw = base64.b64decode(ciphertext_b64.encode("ascii"), altchars=b"-_", validate=True)
            if len(raw) < 28:
                raise ValueError("Truncated vault record")
            nonce, ct = raw[:12], raw[12:]
            return self.aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception as exc:
            raise VaultDecryptionError(
                "Encrypted vault record could not be decrypted; the saved record was kept"
            ) from exc

    def encrypt(self, data: bytes) -> bytes:
        if not data:
            return b""
        nonce = os.urandom(12)
        ct = self.aesgcm.encrypt(nonce, data, None)
        return nonce + ct

    def decrypt(self, data: bytes) -> bytes:
        if not data:
            return b""
        try:
            if len(data) < 28:
                raise ValueError("Truncated vault record")
            nonce, ct = data[:12], data[12:]
            return self.aesgcm.decrypt(nonce, ct, None)
        except Exception as exc:
            raise VaultDecryptionError(
                "Encrypted vault record could not be decrypted; the saved record was kept"
            ) from exc

