# Veil 1.0 — hide it, bring it back, carry on

I wanted one button that could get certain tabs and bookmarks out of sight without turning the browser into a crime scene afterward. Turns out the **bringing them back** part is where things get interesting.

So here's Veil: a small Linux tray companion, a browser extension, and a local encrypted vault. Hit the switch, matching tabs get a pause page and matching bookmarks can be vaulted. Switch back, and Veil tries to put everything where it belongs.

Pretty simple on paper. Famous last words.

## What's actually in here

- **One-click conceal / reveal**, including the tray, CLI and browser extensions.
- **Chrome-family and Firefox support**, with their own background-script loading paths. Browser-store signing and real-world compatibility still vary.
- **Encrypted recovery records**, native messaging and a local daemon. No cloud account needed.
- **Local matching rules** for sensitive destinations, plus allowlists and blocklists.
- **Batched tab operations** for people with an unreasonable number of tabs open. I'm not judging.
- **Portable encrypted backups**, plus installer paths for common Linux distro families.

## The security changes in the refreshed 1.0 build

The live AES-256 key now goes into **KDE Wallet or GNOME Keyring** via `secret-tool`, instead of sitting in a plaintext `veil.key` right next to `vault.db`. Existing keys are migrated only after Veil reads the same key back from the wallet. If that fails, it leaves the original alone. Losing your vault because the wallet had a bad day would be a pretty terrible feature.

New `.veilvault` exports use **scrypt** and require a passphrase of at least 16 characters. Old PBKDF2 backups can still be imported. Damaged encrypted records now raise a visible error instead of quietly becoming empty URLs.

The extension also has tighter paused-page exposure, and Firefox no longer tries to load a Chromium worker in its background page.

## If you're upgrading, read this bit

1. **Stop** the old Veil tray and service first.
2. Preserve a copy of `~/.config/veil/`. Better yet, make a separate encrypted `.veilvault` backup too.
3. Install `secret-tool` and unlock your KDE Wallet or GNOME Keyring.
4. Start the new Veil. It moves the existing encryption key into your wallet **only after verifying it**.

**Dont delete `veil.key` yourself** to speed things along. And don't lose your backup. The wallet now holds the live vault key, so copying `vault.db` alone won't be enough on another computer.

[Installation and wallet guide](https://github.com/Bluenochian/Veil/blob/v1.0/docs/INSTALLATION.md#desktop-wallet-setup-and-safe-upgrades) · [Recovery notes](https://github.com/Bluenochian/Veil/blob/v1.0/docs/RECOVERY.md)

## A few things Veil is *not*

It's not an anonymity tool, a browser-history cleaner, or protection from someone who controls your already-unlocked computer. A page may also flash briefly before the extension catches it. And no, a successful CI run isn't the same thing as having tested every browser and Linux desktop on earth.

**Start with a spare browser profile**, especially if you care about your bookmarks. The automated tests cover storage and simulated extension behavior, but live KDE/GNOME wallet migration, Firefox signing, and non-Fedora desktops still need real testing.

## Download and licensing

This release contains **source code and unpacked extensions**, not signed browser-store packages. It uses [PolyForm Noncommercial 1.0.0](https://github.com/Bluenochian/Veil/blob/v1.0/LICENSE); the bundled offline domain list has its [own license and attribution](https://github.com/Bluenochian/Veil/blob/v1.0/DATA_LICENSE.md).

The dramatic banner is AI-generated. Some of the README got AI help too. The bugs and responsibility? Those are still mine.

Anyway, enjoy. And if something breaks, open an issue with a redacted log instead of posting your actual browsing history. Seriously.
