"""Tell installed browsers where to find Veil's local bridge."""

import json
import shutil
from pathlib import Path


HOST_NAME = "com.veil.privacy"


def browser_manifest_paths():
    # Resolve home when installing, not when this module is imported. This also
    # makes the installer work when someone tests it under a different $HOME.
    home = Path.home()
    config = home / ".config"
    chromium = [
        config / "google-chrome/NativeMessagingHosts",
        config / "BraveSoftware/Brave-Browser/NativeMessagingHosts",
        config / "chromium/NativeMessagingHosts",
        config / "microsoft-edge/NativeMessagingHosts",
        config / "vivaldi/NativeMessagingHosts",
        config / "opera/NativeMessagingHosts",
    ]
    firefox = [
        home / ".mozilla/native-messaging-hosts",
        home / ".librewolf/native-messaging-hosts",
        home / ".floorp/native-messaging-hosts",
        home / ".waterfox/native-messaging-hosts",
    ]
    return chromium, firefox


def install_manifests(host_executable_path: str | Path | None = None) -> list[Path]:
    if host_executable_path is None:
        host_executable_path = shutil.which("veil-native-host") or Path.home() / ".local/bin/veil-native-host"

    base = {
        "name": HOST_NAME,
        "description": "Veil native-messaging host",
        "path": str(host_executable_path),
        "type": "stdio",
    }
    chrome = {**base, "allowed_origins": ["chrome-extension://enkfaejfbildipigielgjcoikhhhpgcb/"]}
    firefox = {**base, "allowed_extensions": ["veil@privacy.shield"]}

    installed = []
    chrome_dirs, firefox_dirs = browser_manifest_paths()
    for directories, manifest in ((chrome_dirs, chrome), (firefox_dirs, firefox)):
        for folder in directories:
            # Don't create whole browser profiles that don't exist yet.
            if not folder.parent.is_dir():
                continue
            try:
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{HOST_NAME}.json"
                with path.open("w", encoding="utf-8") as handle:
                    json.dump(manifest, handle, indent=2)
                installed.append(path)
            except OSError:
                # One browser failing to register shouldn't block the rest.
                pass
    return installed


if __name__ == "__main__":
    paths = install_manifests()
    print(f"Installed {len(paths)} native messaging manifests.")
