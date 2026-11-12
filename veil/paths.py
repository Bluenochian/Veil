"""Use packaged assets when installed; otherwise fall back to the source tree."""
from pathlib import Path


def icon_directory() -> Path:
    package = Path(__file__).resolve().parent
    packed = package / "resources" / "assets" / "icons"
    source = package.parent / "assets" / "icons"
    return packed if packed.is_dir() else source


def browser_extension_directory(browser: str) -> Path:
    if browser not in {"chrome", "firefox"}:
        raise ValueError("Unsupported browser extension")
    package = Path(__file__).resolve().parent
    packed = package / "resources" / "browser-extension" / browser
    source = package.parent / "browser-extension" / browser
    return packed if packed.is_dir() else source
