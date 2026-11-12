"""Register Veil's native-messaging host in known browser config paths."""

import os
import sys
import json
from pathlib import Path


CHROMIUM_MANIFEST_DIRS = [
    # Google Chrome
    Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts",
    # Brave Browser
    Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
    # Chromium
    Path.home() / ".config" / "chromium" / "NativeMessagingHosts",
    # Microsoft Edge
    Path.home() / ".config" / "microsoft-edge" / "NativeMessagingHosts",
    # Vivaldi
    Path.home() / ".config" / "vivaldi" / "NativeMessagingHosts",
    # Opera
    Path.home() / ".config" / "opera" / "NativeMessagingHosts",
    # System-wide locations
    Path("/etc/opt/chrome/native-messaging-hosts"),
    Path("/etc/chromium/native-messaging-hosts")
]

FIREFOX_MANIFEST_DIRS = [
    # Native Mozilla Firefox
    Path.home() / ".mozilla" / "native-messaging-hosts",
    # LibreWolf
    Path.home() / ".librewolf" / "native-messaging-hosts",
    # Floorp
    Path.home() / ".floorp" / "native-messaging-hosts",
    # Waterfox
    Path.home() / ".waterfox" / "native-messaging-hosts",
    # System-wide
    Path("/usr/lib/mozilla/native-messaging-hosts"),
    Path("/usr/lib64/mozilla/native-messaging-hosts")
]


def install_manifests(host_executable_path: str | Path | None = None) -> list[Path]:
    if host_executable_path is None:
        # Default to installed binary or python runner
        host_executable_path = shutil_which("veil-native-host") or (Path.home() / ".local" / "bin" / "veil-native-host")

    installed_files = []

    # 1. Chromium Manifest
    chromium_manifest = {
        "name": "com.veil.privacy",
        "description": "Veil native-messaging host",
        "path": str(host_executable_path),
        "type": "stdio",
        "allowed_origins": [
            "chrome-extension://enkfaejfbildipigielgjcoikhhhpgcb/"
        ]
    }

    for d in CHROMIUM_MANIFEST_DIRS:
        if not str(d).startswith(str(Path.home()) + os.sep):
            continue
        if not d.parent.exists():
            continue
        try:
            d.mkdir(parents=True, exist_ok=True)
            manifest_file = d / "com.veil.privacy.json"
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(chromium_manifest, f, indent=2)
            installed_files.append(manifest_file)
        except OSError:
            pass

    # 2. Firefox Manifest
    firefox_manifest = {
        "name": "com.veil.privacy",
        "description": "Veil native-messaging host",
        "path": str(host_executable_path),
        "type": "stdio",
        "allowed_extensions": [
            "veil@privacy.shield"
        ]
    }

    for d in FIREFOX_MANIFEST_DIRS:
        if not str(d).startswith(str(Path.home()) + os.sep):
            continue
        if not d.parent.exists():
            continue
        try:
            d.mkdir(parents=True, exist_ok=True)
            manifest_file = d / "com.veil.privacy.json"
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(firefox_manifest, f, indent=2)
            installed_files.append(manifest_file)
        except OSError:
            pass

    return installed_files


def shutil_which(cmd: str) -> Path | None:
    import shutil
    res = shutil.which(cmd)
    return Path(res) if res else None


if __name__ == "__main__":
    installed = install_manifests()
    print(f"Installed {len(installed)} native messaging manifests.")
