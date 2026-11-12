# Contributing to Veil

Veil has a browser extension, a Linux desktop service, and an encrypted recovery vault. A change to one can affect the others, so please keep pull requests focused and include a way to test them.

## Development setup

```bash
git clone https://github.com/Bluenochian/Veil.git
cd Veil
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e . pytest
```

For a system-Python setup, distribution-managed PySide6 may be preferable. The project also provides `bash scripts/install.sh --no-deps` for local desktop integration once dependencies are present.

## Checks before a pull request

```bash
python3 -m compileall -q veil
python3 -m pytest -q tests
node tests/browser_extension_smoke.cjs
node tests/browser_scale.cjs
bash -n scripts/install.sh scripts/uninstall.sh
```

Browser changes need checks for Chromium and Firefox. Vault or bookmark changes need regression tests for interrupted writes, duplicate events, bad input, and restoration. Installer changes should be tried on a real distro as well as with the installer tests.

## Pull request scope

- Describe the behavior change and affected browser/desktop interfaces.
- Explain the reproduction steps and how failure states behave.
- Include automated regression coverage when possible.
- Keep browser data, local paths, passphrases, and machine-specific diagnostics out of commits.
- Keep public-facing claims consistent with tested behavior.

## Security disclosures

Do not file public proof-of-concept exploits exposing private data. Follow [SECURITY.md](SECURITY.md).

## Licensing contributions

Contributions submitted for inclusion in Veil must be compatible with the project's [PolyForm Noncommercial License 1.0.0](LICENSE). Contributors must have the right to submit their code and assets. Do not contribute third-party domain lists or copyrighted material without documented permission and attribution.
