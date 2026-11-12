# Features and behavior

## State switching

Protection requires an active desktop service. `veil toggle` requests a transition; it does not claim that browser content was protected if the service cannot acknowledge the request. `veil status --json` can be used for machine-readable status checks.

| Action | Scope | Notes |
| --- | --- | --- |
| Toggle | Matching extension-managed tabs and bookmarks | Requires native messaging and an active service. |
| Reveal | One paused browser tab | Operates through the extension-local paused page. |
| Reveal all | Browser tab restoration broadcast | Requires connected browser extensions. |
| Panic | Immediate protection request plus supported cleanup | Does not erase general browser history. |
| Boss key | Immediate protection and window minimization | Window-manager behavior depends on the desktop. |
| Timer | Temporary protection interval | Process lifetime and service state affect operation. |

## Classification

The `veil/classifier/engine.py` module combines bundled offline SQLite domain-index lookups, host/URL/title matching, and local allowlist/blocklist entries. It accounts for selected educational, medical, news, and research contexts to reduce accidental matches. Domain overrides are applied locally and should be tested with `veil test`.

```bash
veil test https://example.net "Example document"
veil rules --add-black example.net
veil rules --list
veil rules --remove example.net
```

Browser extension classification and desktop-service classification need to remain aligned. Unit and browser simulations protect known paths, but behavior can change with browser API updates.

## Vault behavior

Sensitive records are encrypted before tab/bookmark changes are acknowledged. Bookmark restoration uses stored destination, title, and placement metadata; folder changes or concurrent edits can prevent an exact reconstruction. Backups are independent files and should be stored safely.

Batch operations reduce per-tab IPC overhead when many tabs require a state transition. They do not eliminate browser navigation, JavaScript scheduling, encryption, or disk latency on real hardware.

## Clipboard and temporary cleanup

`veil sanitize` handles supported clipboard content; `veil shred` targets supported browser temporary cache artifacts. Neither command is a general-purpose secure wipe of browser profiles, history, swap files, or disk blocks.

## Accessibility and UX

The browser placeholder includes a visible Reveal action. Desktop accessibility depends on Qt, the system tray implementation, focus handling, desktop compositing, and browser UI rendering. Accessibility reports are welcome through GitHub issues.
