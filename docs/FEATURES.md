# Features and behavior

## State switching

The desktop service needs to be running for any of this to work. `veil toggle` asks it to change state, and `veil status --json` tells you what it reported back. That doesn't automatically mean every browser extension is connected.

| Action | Scope | Notes |
| --- | --- | --- |
| Toggle | Matching extension-managed tabs and bookmarks | One-click ON; password required to turn OFF through the daemon or tray. |
| Reveal | One paused browser tab | Operates through the extension-local paused page. |
| Reveal all | Browser tab restoration broadcast | Requires connected browser extensions. |
| Panic | Immediate protection request plus supported cleanup | Does not erase general browser history. |
| Boss key | Immediate protection and window minimization | Window-manager behavior depends on the desktop. |
| Timer | Unlock reminder while protection remains active | Does not bypass password authentication to turn OFF. |

## Classification

Matching lives in `veil/classifier/engine.py`. It checks the bundled offline domain list, parts of the URL and page title, and your own allowlist or blocklist. Some research, news and educational pages need exceptions. When a site is being picked up incorrectly, start with `veil test`.

```bash
veil test https://example.net "Example document"
veil rules --add-black example.net
veil rules --list
veil rules --remove example.net
```

The browser and service need to agree about which sites match. The tests cover cases I've run into, but browser updates can still surprise us.

## Vault behavior

Sensitive records are encrypted before tab/bookmark changes are acknowledged. Bookmark restoration uses stored destination, title, and placement metadata; folder changes or concurrent edits can prevent an exact reconstruction. Backups are independent files and should be stored safely.

Batch operations reduce per-tab IPC overhead when many tabs require a state transition. They do not eliminate browser navigation, JavaScript scheduling, encryption, or disk latency on real hardware.

## Clipboard and temporary cleanup

`veil sanitize` handles supported clipboard content; `veil shred` targets supported browser temporary cache artifacts. Neither command is a general-purpose secure wipe of browser profiles, history, swap files, or disk blocks.

## Accessibility and UX

The browser placeholder includes a visible Reveal action. Desktop accessibility depends on Qt, the system tray implementation, focus handling, desktop compositing, and browser UI rendering. Accessibility reports are welcome through GitHub issues.
