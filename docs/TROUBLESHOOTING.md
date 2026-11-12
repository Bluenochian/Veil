# Troubleshooting

## Desktop wallet unavailable or vault key missing

Veil now uses `secret-tool` and the desktop Secret Service to store its live encryption key. If you see a keyring error, **do not delete `vault.db` or any remaining `veil.key`**.

1. Run `command -v secret-tool`. Install `libsecret`/`libsecret-tools` if the command is missing.
2. Unlock KDE Wallet or GNOME Keyring and run Veil from your graphical desktop session.
3. Stop any older Veil tray/service before the one-time migration.
4. If the keyring and old file disagree, preserve both rather than forcing an overwrite.
5. If the keyring entry has been lost, restore it or use your independent `.veilvault` backup. Veil will not make a new key for an existing database.

[Wallet setup](INSTALLATION.md#desktop-wallet-setup-and-safe-upgrades) · [Recovery](RECOVERY.md#desktop-wallet-and-migration-problems)

## Service does not respond

Run:

```bash
veil status
veil tray
veil status --json
```

If startup fails, check desktop session variables (`DISPLAY` or `WAYLAND_DISPLAY`), PySide6 availability, and local socket permissions. Do not assume that the presence of a saved protection flag means the daemon is running.

## Browser is detected, but tabs do not pause

1. Verify that the correct browser extension is loaded and enabled.
2. Run `veil install-extension` after the browser has created its profile.
3. Inspect the browser's extension console for native-messaging errors.
4. Confirm that the desktop service is running.
5. Try a disposable profile with a single custom matching domain and `veil test`.

Browser-specific packaging, flatpak/snap isolation, and native-messaging host directories may affect registration.

## Firefox extension vanished

Loading through `about:debugging` creates a temporary development extension. Firefox removes it after restarting. Persistent deployment requires a signed package following Mozilla's extension distribution process.

## Wrong site classification

```bash
veil test https://example.net "Page title"
veil rules --list
```

The classifier uses URL and title context, so mismatches can be caused by redirects, malformed pages, URL encoding, extension timing, or an overly broad entry. Test an exact domain override before making persistent changes.

## Bookmarks were not restored

Avoid repeated activation while diagnosing. Preserve copies of `~/.config/veil/vault.db` and any `.veilvault` backups. Inspect `veil stats` and browser bookmark folder state. Folder removal, concurrent edits, or changes from sync extensions can prevent exact reconstruction.

## Encrypted archive cannot be imported

Stop the service. Ensure the archive and passphrase are correct. Import refuses conflicting records to avoid overwriting existing vault entries. Import is not a merge-and-replace operation.

## Tray icon missing

Confirm your desktop exposes a system tray; ensure Qt platform plugins and PySide6 are present. Desktop session implementation varies across Wayland and X11 compositors.

For the icon-click behavior, state colors, Preferences, and Tools, see the [illustrated tray manual](TRAY_MENU.md). In particular, `Ctrl+Alt+V` is currently a **menu label**, not a registered global shortcut.

## `ModuleNotFoundError` after installing

The standalone installer requires system Python packages to be accessible to the `python3` command used by its wrappers. A dependency installed only inside a different virtual environment may not be visible. Install through the distribution package manager or adjust the chosen interpreter explicitly.

## Diagnose safely

Provide distribution family, Python version, desktop session type, browser family/version, exact CLI command, and redacted errors when filing an issue. Do not include actual browser history, protected URL lists, vault files, passphrases, or browser profile archives in public issues.
