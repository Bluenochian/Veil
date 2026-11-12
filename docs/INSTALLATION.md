# Installation and desktop setup

[← Back to Veil](../README.md) · [Quick start](GETTING_STARTED.md) · [Browser setup](BROWSER_SETUP.md) · [Compatibility](COMPATIBILITY.md)

Veil's primary installation path is a per-account Linux desktop install. It uses Python, Qt, a local Unix socket, and browser-native messaging; it doesn't require installing a kernel module or a privileged browser agent.

## Prerequisites

| Dependency | Purpose | Required? |
| --- | --- | --- |
| Python 3.10+ | Desktop service and CLI | Yes |
| PySide6 | Tray/desktop interface | For the graphical tray |
| `cryptography` | Encrypted vault and backup support | Yes |
| `secret-tool` (libsecret) | Access the live vault key in the desktop wallet | Yes |
| KDE Wallet or GNOME Keyring (unlocked) | Secret Service provider in your graphical login session | Yes |
| Browser extension | Read and alter participating browser tabs/bookmarks | For browser control |
| `libnotify`, `wl-clipboard`, `xclip` | Notifications and clipboard integrations | Optional, feature-dependent |
| Wayland or X11 desktop session | Graphical tray and desktop integration | For graphical use |

### Supported package-manager families

The installer checks `/etc/os-release` and recognizes common `ID` / `ID_LIKE` families. It **does not** prove identical runtime behavior on every distribution or desktop configuration.

<details>
<summary>Debian and Ubuntu family (APT)</summary>

Examples: Debian, Ubuntu, Linux Mint, Pop!_OS, MX Linux, KDE neon, and Zorin OS.

```bash
sudo apt-get update
sudo apt-get install -y \
  python3-pyside6.qtcore python3-pyside6.qtgui \
  python3-pyside6.qtwidgets python3-pyside6.qtdbus \
  python3-cryptography libsecret-tools libnotify-bin wl-clipboard xclip
```

Some releases split Qt packages differently. Check the package manager rather than assuming the exact same names everywhere.

</details>

<details>
<summary>Fedora and RHEL family (DNF)</summary>

Examples: Fedora Workstation, Fedora Spins, CentOS Stream, Rocky Linux, AlmaLinux, and related distributions.

```bash
sudo dnf install -y python3-pyside6 python3-cryptography libsecret libnotify wl-clipboard xclip
```

Image-based distributions may have different approaches for providing dependencies, including layering or containers.

</details>

<details>
<summary>Arch family (Pacman)</summary>

Examples: Arch Linux, EndeavourOS, Manjaro, Garuda Linux, and CachyOS.

```bash
sudo pacman -S --needed python-pyside6 python-cryptography libsecret libnotify wl-clipboard xclip
```

</details>

<details>
<summary>openSUSE family (Zypper)</summary>

Examples: Tumbleweed, Leap, and Slowroll.

```bash
sudo zypper install -y python3-pyside6 python3-cryptography libsecret-tools libnotify-tools wl-clipboard xclip
```

</details>

## Desktop wallet setup and safe upgrades

Veil uses the freedesktop Secret Service through `secret-tool`, supported by KDE Wallet and GNOME Keyring. Make sure your desktop wallet is **unlocked in your graphical login session**. Installing libsecret alone doesn't create or unlock a working wallet. Veil intentionally refuses to start its vault if the wallet cannot be accessed; there is no plaintext-key fallback.

**Already using Veil?** Stop the older tray and service first, keep a safe copy of `~/.config/veil/` and preferably export a passphrase-encrypted `.veilvault` backup *before upgrading*. At the next start, Veil stores the existing `veil.key` in the wallet, reads it back to verify the same AES key, then removes the plaintext file. It does not change the encrypted database. If an old daemon is still running, the wallet is unavailable, or the keys disagree, Veil stops the migration without deleting the old file.

If you move to a different machine, do **not** rely solely on copying `vault.db`: you will also need the original wallet key, or (recommended) a portable passphrase-encrypted `.veilvault` archive.

## Recommended source installation

```bash
git clone https://github.com/Bluenochian/Veil.git
cd Veil
bash scripts/install.sh
```

The installer can offer to install dependencies. If the dependencies are already present:

```bash
bash scripts/install.sh --no-deps
```

> [!IMPORTANT]
> `--no-deps` skips dependency installation; it does not bundle PySide6 or fix missing Python modules automatically. The `python3` interpreter invoked by the wrapper needs to see the dependencies.

### Resulting application layout

```text
~/.local/
├── bin/
│   ├── veil
│   └── veil-native-host
└── share/
    ├── veil/app/
    │   ├── veil/                  # Desktop core
    │   ├── browser-extension/     # Browser-side code
    │   ├── assets/                # Icons and artwork
    │   └── bin/                   # Entrypoints
    └── applications/
        └── veil.desktop           # Desktop shortcut, if installed

~/.config/
├── veil/
│   ├── vault.db                   # Local encrypted records
│   ├── .keyring-initialized       # Non-secret wallet marker
│   └── rules.json                 # Matching overrides
├── autostart/veil.desktop
└── systemd/user/veil.service
```

The exact set of files can differ based on initialization and optional desktop integration. The configuration and vault live outside the copied application directory.

## Verify the command and desktop service

```bash
export PATH="$HOME/.local/bin:$PATH"
veil --help
veil browsers
veil tray
```

In a second terminal:

```bash
veil status
veil status --json
```

If the service isn't running, check the graphical session, PySide6, `secret-tool`, and your unlocked KDE Wallet/GNOME Keyring. Don't assume that a saved ON flag means browser protection has actually begun.

## Connect the native host

Load the appropriate browser extension as described in [Browser setup](BROWSER_SETUP.md), then run:

```bash
veil install-extension
```

Repeat the registration after creating a new browser profile or adding another browser. An unpacked extension and host manifest must both exist. Flatpak or Snap browsers may not read the standard native-messaging paths without extra configuration.

## Alternate build formats

The repository includes Python packaging metadata and native packaging templates. To build a Python distribution:

```bash
python3 -m pip install build
python3 -m build
```

A Python wheel isn't a substitute for the per-account installer: it doesn't automatically perform browser-profile registration, load extensions into browsers, or enable desktop autostart. Likewise, packaging templates under `packaging/` are not prebuilt and individually certified `.deb`, `.rpm`, or Arch packages.

## Uninstalling

```bash
bash scripts/uninstall.sh
```

Review [scripts/uninstall.sh](../scripts/uninstall.sh) before running. Export vault data or make a backup first if preserving records matters. Uninstalling Veil does not mean all browser-side state and browser history are erased.

## Next

[Connect Brave/Chromium or Firefox →](BROWSER_SETUP.md) · [First conceal/reveal test →](GETTING_STARTED.md#5-run-a-reversible-demonstration)

> [!NOTE]
> Veil includes its offline adult-domain index automatically; no separate list download or manual database setup is needed. See [data licensing](../DATA_LICENSE.md).
