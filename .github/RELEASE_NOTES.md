# Veil 1.0.1

Apparently surviving a reboot and clicking the tray icon once were both asking too much. Fixed that.

- The tray now starts through the user systemd service where available. If it crashes, systemd can bring it back. Other desktops still get normal autostart.
- Plasma's occasional double-click nonsense should no longer flip the switch twice.
- A failing browser profile won't stop the other profiles. When one reports an error, you'll actually hear about it now.

The OFF password is still required. The vault, extension behavior and artwork aren't changing for this update.

If you're upgrading, back up `~/.config/veil/` first and run `bash scripts/install.sh` again. Don't delete `veil.key` if you're still migrating the old wallet key. If the tray was already open during installation, restart it or log out and back in for the new startup setup.

Source and unpacked extensions only, as before. And please test with a spare browser profile first, because browsers are really good at inventing new ways to be annoying.

[Installation notes](https://github.com/Bluenochian/Veil/blob/v1.0.1/docs/INSTALLATION.md) · [Recovery](https://github.com/Bluenochian/Veil/blob/v1.0.1/docs/RECOVERY.md) · [Licenses](https://github.com/Bluenochian/Veil/blob/v1.0.1/LICENSE)
