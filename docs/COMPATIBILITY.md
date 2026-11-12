# Compatibility and installation notes

## Linux distribution families

I've mainly used and tested Veil on Fedora. The live vault now also needs `secret-tool` and a working desktop Secret Service provider such as KDE Wallet or GNOME Keyring, which can be absent in headless or minimal sessions. The installer knows about APT, DNF, Pacman, and Zypper families, but recognizing a package manager isn't the same as testing a complete desktop setup on every distro.

| Family | Example distributions | Dependency manager | Testing scope |
| --- | --- | --- | --- |
| Debian / Ubuntu | Debian, Ubuntu, Linux Mint, Pop!_OS, Zorin, KDE neon, MX Linux | APT | Dependency routing and isolated Linux install checks; not all distros boot-tested |
| Fedora / RHEL | Fedora Workstation, Fedora Spins, CentOS Stream, Rocky, AlmaLinux, Fedora-based derivatives | DNF | Dependency routing checked; not all distros boot-tested |
| Arch | Arch, EndeavourOS, Manjaro, Garuda, CachyOS | Pacman | Dependency routing checked; not all distros boot-tested |
| openSUSE | Tumbleweed, Leap, Slowroll | Zypper | Dependency routing checked; not all distros boot-tested |

Distribution version, Python package splits, SELinux/AppArmor policy, immutable filesystem layout, and desktop session can affect installation. Consult native package managers for exact package names.

## Browser types

| Family | Examples | How to load | Limitation |
| --- | --- | --- | --- |
| Chromium | Brave, Chromium, Google Chrome, Edge, Vivaldi, Opera | Load `browser-extension/chrome` as unpacked developer extension | Not distributed or signed via browser stores |
| Firefox | Firefox, LibreWolf, Floorp, Waterfox | Load `browser-extension/firefox/manifest.json` with `about:debugging` | Temporary add-ons do not persist after restart |

All browser examples denote likely API families, not a certification that every release, sandbox, or derivative has working native messaging.

## Native messaging

`veil install-extension` registers host manifests for detected browsers. Some Flatpak, Snap, portable, or custom browser builds require additional host integration paths that the installer may not discover. If an extension loads but cannot change tabs, inspect host permissions, profile detection, and extension console output.

## Package formats

- `scripts/install.sh`: standalone per-account installation and desktop integration.
- `pyproject.toml` / `setup.py`: source and wheel builds for Python packaging.
- `debian/`: Debian source-package metadata.
- `packaging/debian/`, `packaging/rpm/`, `packaging/arch/`: packaging templates.
- No prebuilt native packages or store-signed browser extensions are included.

## Session type

The tray targets graphical Wayland/X11 sessions. Notification, clipboard, global hotkey, and window-minimization behavior may vary with GNOME, KDE Plasma, Xfce, Cinnamon, and other desktop environments.
