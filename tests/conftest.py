"""Give each pytest test an isolated in-memory desktop secret store."""
import pytest
from veil.crypto import KeyManager


@pytest.fixture(autouse=True)
def isolated_secret_service(monkeypatch):
    records = {}

    class MemorySecretService:
        def __init__(self, config_dir):
            self.identity = str(config_dir.resolve())

        def lookup(self):
            return records.get(self.identity)

        def store(self, key):
            records[self.identity] = bytes(key)

    monkeypatch.setattr(KeyManager, "STORE_CLASS", MemorySecretService)
    return records
