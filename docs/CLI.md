# Command reference

[← Back to Veil](../README.md) · [Everyday use](USING_VEIL.md) · [Recovery](RECOVERY.md)

Veil's CLI entry point is `veil`. Commands that change protection state require a responsive desktop service; read-only commands such as `veil test` and `veil rules --list` may work while it is stopped.

## Commands at a glance

| Command | Role | Service needed? |
| --- | --- | :---: |
| `veil tray` | Start the desktop tray and service | Launches it |
| `veil status` | Print current desktop protection state | No, but reports offline if absent |
| `veil status --json` | Emit state in JSON form | No |
| `veil toggle` | Request protection ON/OFF | Yes |
| `veil reveal-all` | Ask browser extensions to restore paused tabs | Yes |
| `veil panic` | Emergency protection request with supported cleanup | Yes for protection |
| `veil boss-key` | Protection request plus supported minimization | Yes for protection |
| `veil timer 15` | Set a fifteen-minute timer | Yes |
| `veil timer --cancel` | Cancel a timer | Yes |
| `veil browsers` | Discover profiles on disk | No |
| `veil install-extension` | Register native-messaging hosts | No |
| `veil test URL [TITLE]` | Classify a URL and optional title | No |
| `veil rules --list` | Read local overrides | No |
| `veil rules --add-white DOMAIN` | Allowlist a domain | No |
| `veil rules --add-black DOMAIN` | Blocklist a domain | No |
| `veil rules --remove DOMAIN` | Remove an override | No |
| `veil stats` | Display encrypted store counts | No |
| `veil export [FILE]` | Export a passphrase-protected vault | No |
| `veil import FILE` | Import an encrypted vault backup | Must be stopped |
| `veil sanitize` | Handle supported clipboard content | Feature-dependent |
| `veil shred` | Clean supported temporary browser artifacts | No |
| `veil sound --enable / --disable` | Toggle sound feedback | No |
| `veil autostart --enable / --disable` | Toggle desktop autostart | No |
| `veil benchmark` | Run a local 10,000-query classifier diagnostic | No |
| `veil completions bash / zsh` | Print completion definitions | No |

All actual parser options live in [`veil/command.py`](../veil/command.py). Use `veil --help` for the installed version.

## Desktop state and automation

```bash
veil status
veil status --json
```

When the service is absent, the JSON response sets `daemon_running` to false. A stored active preference does not mean live protection is running. Use the daemon status rather than scraping colored terminal text in scripts.

```bash
veil tray
veil toggle
veil reveal-all
```

These operations depend on the service and browser bridge. In particular, the service acknowledging a toggle does not prove every browser profile is connected.

### Timer options

```bash
veil timer 15
veil timer 2.5
veil timer --cancel
```

The argument is a number of minutes. Timers depend on the running desktop service and shouldn't be treated as a guaranteed scheduler across system sleep, logout, or process termination.

## Matching and overrides

```bash
veil test https://example.org
veil test https://example.org "Example title"
veil rules --list
veil rules --add-black private.example.org
veil rules --add-white research.example.org
veil rules --remove private.example.org
```

Test with an exact representative URL and title where possible. The extension's browser events can differ from a direct command-line classification call.

## Vault commands

```bash
veil stats
veil export ~/veil-backup.veilvault
# Stop Veil before importing.
veil import ~/veil-backup.veilvault
```

`export` and `import` accept an optional `--passphrase` parameter for noninteractive use, but passing sensitive text on a command line can expose it through process listings, shell history, or logs. Prefer the interactive prompt. Conflicting records may cause an import to be rejected rather than overwrite existing entries.

[Backup and restoration details →](RECOVERY.md)

## Browser and integration tools

```bash
veil browsers
veil install-extension
veil autostart --enable
veil autostart --disable
veil sound --enable
veil sound --disable
```

Browser discovery checks profile paths; successful native messaging needs a working extension and host registration for the relevant browser packaging model.

## Diagnostics and maintenance

```bash
veil benchmark
veil sanitize
veil shred
veil completions bash
veil completions zsh
```

`benchmark` measures local classification throughput, not full browser concealment or network delay. `sanitize` and `shred` are narrowly scoped; neither is a general history wipe or secure disk erasure.

## Failure handling

| Message / behavior | What it means |
| --- | --- |
| Daemon unavailable | Start `veil tray` before toggling |
| Status says STANDBY | The running service isn't enforcing protection, or it's offline |
| Browser profile absent | Launch browser once, check its profile location |
| Extension reports host error | Re-register and inspect browser native-messaging integration |
| Vault import conflict | Existing records are preserved; investigate before retrying |

[Browser diagnostics →](BROWSER_SETUP.md#when-the-extension-cannot-reach-the-desktop) · [Troubleshooting →](TROUBLESHOOTING.md)
