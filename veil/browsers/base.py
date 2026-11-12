"""
Abstract Browser Manager Base Class
Defines the interface for discovering, scanning, concealing, and restoring
browser artifacts (History, Bookmarks, Top Sites, Caches) across all web browsers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass


@dataclass
class BrowserProfile:
    browser_type: str  # 'chromium' or 'firefox'
    browser_name: str  # 'Brave', 'Google Chrome', 'Firefox', etc.
    profile_name: str  # 'Default', 'Profile 1', etc.
    path: Path
    is_active: bool = False


class BaseBrowserManager(ABC):
    def __init__(self, profile: BrowserProfile, vault):
        self.profile = profile
        self.vault = vault

    @abstractmethod
    def conceal_all(self, classifier) -> dict:
        """Conceal sensitive history, bookmarks, and thumbnails into vault."""
        pass

    @abstractmethod
    def restore_all(self) -> dict:
        """Restore concealed history, bookmarks, and thumbnails back into browser."""
        pass

    @abstractmethod
    def shred_caches(self) -> int:
        """Securely shred temporary thumbnail and session caches."""
        pass
