# Contributing to Veil

If you want to help out, open an issue or send a pull request. Bug reports are useful too, especially from browsers and Linux desktops I haven't tried.

Veil has a browser extension and a desktop service, and they both need to agree about what's hidden and how it gets restored. Please keep that in mind when changing tab, bookmark or vault code. A page disappearing is the easy part; getting it back is what matters.

## Running it from source

```bash
git clone https://github.com/Bluenochian/Veil.git
cd Veil
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e . pytest
```

On some Linux distributions, installing PySide6 through the package manager is easier. If you already have the dependencies, `bash scripts/install.sh --no-deps` handles the desktop side.

## Before sending a change

```bash
python3 -m compileall -q veil
python3 -m pytest -q tests
node tests/browser_extension_smoke.cjs
node tests/browser_scale.cjs
bash -n scripts/install.sh scripts/uninstall.sh
```

If you're changing browser code, check Firefox *and* Chromium. If you're touching the vault, try the failure cases as well as the happy path: duplicate bookmarks, interrupted saves, restoring the wrong profile, that sort of thing. Installer changes are worth trying on a real Linux desktop too.

You don't need a big PR template. Just tell me what wasn't working, what you changed and how you checked it. And please remove actual browsing URLs, passwords, profile data and private logs before posting anything.

For vulnerabilities involving private data, see [SECURITY.md](SECURITY.md) instead of posting an exploit in a public issue.

Contributions need to be compatible with the [PolyForm Noncommercial License 1.0.0](LICENSE). Please don't include third-party domain lists or artwork without permission and the right attribution.
