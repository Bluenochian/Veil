"""Look for browser profiles. Finding one doesn't mean the extension is connected."""

from pathlib import Path

from veil.browsers.base import BrowserProfile
from veil.browsers.chromium import ChromiumBrowserManager
from veil.browsers.firefox import FirefoxBrowserManager


def browser_locations():
    home = Path.home()
    config = home / ".config"
    flatpak = home / ".var" / "app"
    chromium = [
        ("Brave", config / "BraveSoftware/Brave-Browser"),
        ("Google Chrome", config / "google-chrome"),
        ("Chromium", config / "chromium"),
        ("Microsoft Edge", config / "microsoft-edge"),
        ("Vivaldi", config / "vivaldi"),
        ("Opera", config / "opera"),
        ("Brave (Flatpak)", flatpak / "com.brave.Browser/config/BraveSoftware/Brave-Browser"),
        ("Chrome (Flatpak)", flatpak / "com.google.Chrome/config/google-chrome"),
        ("Chromium (Flatpak)", flatpak / "org.chromium.Chromium/config/chromium"),
        ("Edge (Flatpak)", flatpak / "com.microsoft.Edge/config/microsoft-edge"),
        ("Chromium (Snap)", home / "snap/chromium/current/.config/chromium"),
        ("Brave (Snap)", home / "snap/brave/current/.config/BraveSoftware/Brave-Browser"),
    ]
    firefox = [
        ("Firefox", home / ".mozilla/firefox"),
        ("LibreWolf", home / ".librewolf"),
        ("Floorp", home / ".floorp"),
        ("Waterfox", home / ".waterfox"),
        ("Firefox (Flatpak)", flatpak / "org.mozilla.firefox/.mozilla/firefox"),
        ("LibreWolf (Flatpak)", flatpak / "io.gitlab.librewolf-community/.librewolf"),
    ]
    return chromium, firefox


class UniversalProfileManager:
    def __init__(self, vault):
        self.vault = vault
        self.managers: list[ChromiumBrowserManager | FirefoxBrowserManager] = []
        self.discover_profiles()

    def discover_profiles(self) -> list[BrowserProfile]:
        profiles = []
        self.managers.clear()
        chromium, firefox = browser_locations()

        for browser, root in chromium:
            if not root.is_dir():
                continue
            folders = [folder for folder in root.iterdir()
                       if folder.is_dir() and (folder.name == "Default" or folder.name.startswith("Profile "))]
            found = False
            for folder in folders:
                if not (folder / "Bookmarks").exists() and not (folder / "History").exists():
                    continue
                profile = BrowserProfile("chromium", browser, folder.name, folder)
                profiles.append(profile)
                self.managers.append(ChromiumBrowserManager(profile, self.vault))
                found = True

            # Opera is one of the browsers that stores things directly in its root.
            if not found and ((root / "Bookmarks").exists() or (root / "History").exists()):
                profile = BrowserProfile("chromium", browser, "Default", root)
                profiles.append(profile)
                self.managers.append(ChromiumBrowserManager(profile, self.vault))

        for browser, root in firefox:
            if not root.is_dir():
                continue
            for folder in root.iterdir():
                if folder.is_dir() and (folder / "places.sqlite").exists():
                    profile = BrowserProfile("firefox", browser, folder.name, folder)
                    profiles.append(profile)
                    self.managers.append(FirefoxBrowserManager(profile, self.vault))

        return profiles

    def conceal_all(self, classifier) -> dict:
        totals = {"bookmarks": 0, "history": 0, "top_sites": 0}
        for manager in self.managers:
            counts = manager.conceal_all(classifier)
            for kind in totals:
                totals[kind] += counts.get(kind, 0)
        return totals

    def restore_all(self) -> dict:
        totals = {"bookmarks": 0, "history": 0, "top_sites": 0}
        for manager in self.managers:
            counts = manager.restore_all()
            for kind in totals:
                totals[kind] += counts.get(kind, 0)
        return totals

    def shred_all_caches(self) -> dict[str, int]:
        counts = {}
        for manager in self.managers:
            name = f"{manager.profile.browser_name} ({manager.profile.profile_name})"
            try:
                counts[name] = manager.shred_caches()
            except OSError:
                counts[name] = 0
        return counts
