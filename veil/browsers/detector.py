"""Find browser profiles in the usual Linux config directories.

A profile being found doesn't mean its extension is connected.
"""

import os
from pathlib import Path
from veil.browsers.base import BrowserProfile
from veil.browsers.chromium import ChromiumBrowserManager
from veil.browsers.firefox import FirefoxBrowserManager


CHROMIUM_SEARCH_LOCATIONS = [
    # Regular installs and package-manager paths
    ("Brave", "chromium", Path.home() / ".config" / "BraveSoftware" / "Brave-Browser"),
    ("Google Chrome", "chromium", Path.home() / ".config" / "google-chrome"),
    ("Chromium", "chromium", Path.home() / ".config" / "chromium"),
    ("Microsoft Edge", "chromium", Path.home() / ".config" / "microsoft-edge"),
    ("Vivaldi", "chromium", Path.home() / ".config" / "vivaldi"),
    ("Opera", "chromium", Path.home() / ".config" / "opera"),
    # Flatpak locations
    ("Brave (Flatpak)", "chromium", Path.home() / ".var" / "app" / "com.brave.Browser" / "config" / "BraveSoftware" / "Brave-Browser"),
    ("Chrome (Flatpak)", "chromium", Path.home() / ".var" / "app" / "com.google.Chrome" / "config" / "google-chrome"),
    ("Chromium (Flatpak)", "chromium", Path.home() / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium"),
    ("Edge (Flatpak)", "chromium", Path.home() / ".var" / "app" / "com.microsoft.Edge" / "config" / "microsoft-edge"),
    # Snap locations
    ("Chromium (Snap)", "chromium", Path.home() / "snap" / "chromium" / "current" / ".config" / "chromium"),
    ("Brave (Snap)", "chromium", Path.home() / "snap" / "brave" / "current" / ".config" / "BraveSoftware" / "Brave-Browser")
]

FIREFOX_SEARCH_LOCATIONS = [
    # Native paths
    ("Firefox", "firefox", Path.home() / ".mozilla" / "firefox"),
    ("LibreWolf", "firefox", Path.home() / ".librewolf"),
    ("Floorp", "firefox", Path.home() / ".floorp"),
    ("Waterfox", "firefox", Path.home() / ".waterfox"),
    # Flatpak locations
    ("Firefox (Flatpak)", "firefox", Path.home() / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox"),
    ("LibreWolf (Flatpak)", "firefox", Path.home() / ".var" / "app" / "io.gitlab.librewolf-community" / ".librewolf")
]


class UniversalProfileManager:
    """Find the browser profiles we can actually work with."""

    def __init__(self, vault):
        self.vault = vault
        self.managers: list[ChromiumBrowserManager | FirefoxBrowserManager] = []
        self.discover_profiles()

    def discover_profiles(self) -> list[BrowserProfile]:
        profiles = []
        self.managers.clear()

        for browser_name, b_type, root_dir in CHROMIUM_SEARCH_LOCATIONS:
            if not root_dir.exists():
                continue

            # Usual profiel names: 'Default', 'Profile 1', 'Profile 2', etc.
            found_subprofiles = False
            for child in root_dir.iterdir():
                if child.is_dir() and (child.name == "Default" or child.name.startswith("Profile ")):
                    if (child / "Bookmarks").exists() or (child / "History").exists():
                        bp = BrowserProfile(
                            browser_type="chromium",
                            browser_name=browser_name,
                            profile_name=child.name,
                            path=child
                        )
                        profiles.append(bp)
                        self.managers.append(ChromiumBrowserManager(bp, self.vault))
                        found_subprofiles = True

            # Opera tends to put files in root_dir. Not every browser follows the same layuot.
            if not found_subprofiles and ((root_dir / "Bookmarks").exists() or (root_dir / "History").exists()):
                bp = BrowserProfile(
                    browser_type="chromium",
                    browser_name=browser_name,
                    profile_name="Default",
                    path=root_dir
                )
                profiles.append(bp)
                self.managers.append(ChromiumBrowserManager(bp, self.vault))

        for browser_name, b_type, root_dir in FIREFOX_SEARCH_LOCATIONS:
            if not root_dir.exists():
                continue

            for child in root_dir.iterdir():
                if child.is_dir() and (child / "places.sqlite").exists():
                    bp = BrowserProfile(
                        browser_type="firefox",
                        browser_name=browser_name,
                        profile_name=child.name,
                        path=child
                    )
                    profiles.append(bp)
                    self.managers.append(FirefoxBrowserManager(bp, self.vault))

        return profiles

    def conceal_all(self, classifier) -> dict:
        totals = {"bookmarks": 0, "history": 0, "top_sites": 0}
        for mgr in self.managers:
            res = mgr.conceal_all(classifier)
            totals["bookmarks"] += res.get("bookmarks", 0)
            totals["history"] += res.get("history", 0)
            totals["top_sites"] += res.get("top_sites", 0)
        return totals

    def restore_all(self) -> dict:
        totals = {"bookmarks": 0, "history": 0, "top_sites": 0}
        for mgr in self.managers:
            res = mgr.restore_all()
            totals["bookmarks"] += res.get("bookmarks", 0)
            totals["history"] += res.get("history", 0)
            totals["top_sites"] += res.get("top_sites", 0)
        return totals

    def shred_all_caches(self) -> dict[str, int]:
        results = {}
        for mgr in self.managers:
            label = f"{mgr.profile.browser_name} ({mgr.profile.profile_name})"
            try:
                cnt = mgr.shred_caches()
                results[label] = cnt
            except Exception:
                results[label] = 0
        return results

