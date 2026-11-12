# Privacy and limitations

Veil is a local-first visibility-control application. It changes what participating browser extensions show and can place selected bookmark records in an encrypted local vault. It does not provide network anonymity, encrypt an entire browser profile, or make a desktop session undiscoverable.

## Data flow

1. Browser extensions inspect their permitted tab and bookmark metadata.
2. Matching destinations are submitted to the local desktop service via native messaging.
3. The service stores protected records in an encrypted SQLite vault and replies through the local IPC channel.
4. The extension displays a local paused page and can restore original destinations or bookmark records later.

The classifier and vault run locally. The project does not require a hosted classification endpoint or account. Inspect source and network behavior independently for specific trust requirements.

## Encryption

- Live protected records use AES-256-GCM, but their key is now stored in **your desktop Secret Service wallet**, normally KDE Wallet (KWallet) or GNOME Keyring. The key is no longer kept in a plaintext `veil.key` beside `vault.db`; `secret-tool` and an unlocked wallet are required to open the vault.
- Existing `veil.key` files are migrated using the *same* 256-bit key, without re-encrypting the database. Veil verifies a successful wallet read-back before removing the old key file. Stop older running Veil processes before migrating. If the wallet is missing or contains a different key, migration stops and preserves the original file.
- Copying the encrypted database alone does not reveal the key. But this does **not** defend against malware running as you: same-user applications can access an unlocked wallet, and privileged attackers may compromise the session. Full-disk encryption is still recommended for stolen laptops.
- Veil does not currently support a separate passphrase for unlocking the *live* vault. Your desktop wallet becomes part of recovery: if you lose its entry, you need an encrypted portable `.veilvault` backup or the original legacy key file.
- New portable backups use AES-256-GCM with a memory-hard scrypt key (N=65,536, r=8, p=2) derived from a separate passphrase of at least 16 characters. Older PBKDF2-based backups are still readable, but they retain their original, weaker protection.
- A corrupted or undecryptable saved record now produces an error rather than silently turning into an empty URL. Keep the vault and follow the recovery guide if this happens.
- Neither encryption nor the browser extension guarantees restoration after every crash, browser update, or simultaneous edit.

## What remains visible

- Browser history remains in place in normal safe mode. Original visit timestamps cannot reliably be restored using browser extension APIs.
- Page content might be rendered briefly before navigation is intercepted.
- Recently used files, OS-level previews, notifications, downloads, other browser profiles, windows outside the browser, screenshots, and screen-sharing tools are outside the feature boundary.
- Existing plaintext legacy `.veil.bak` files are not automatically removed.
- Malicious software, a privileged local account, and inspection of an unlocked desktop session are not defeated by Veil.

## Browser profile safety

Try a disposable profile first. Keep an independent copy of important bookmarks. Be cautious when editing bookmarks from another extension or browser device while protection is enabled.

Experimental mode `VEIL_EXPERIMENTAL_OFFLINE_DB=1` enables legacy offline browser database operations. These operations can affect profile integrity; keep the browser closed and maintain independent backups when investigating them.

## Permissions

The browser extensions request `tabs`, `bookmarks`, `storage`, and `nativeMessaging` because those browser APIs are used in tab management, bookmark handling, and communication with the local service. The paused page is opened by the extension itself and is not exposed to arbitrary websites through `web_accessible_resources`. This reduces a website's ability to detect Veil by probing that page, but it is not a promise of undetectability. Review the manifest and source for the exact permission surface.

## Categories and mistakes

Classification uses a bundled offline adult-domain index, URL/title matching, and local overrides for classes of content that may be undesirable to display in a shared-workspace context, including mature media, wagering, graphic material, and selected unsafe marketplaces. Heuristics can miss content or misclassify legitimate research, news, or educational pages. Allowlist and blocklist overrides can adjust local behavior.

## Incident handling

For any possible unintended removal or data mismatch, stop repeated activations. Preserve the vault and independent backup before experimenting with manual recovery. Report security vulnerabilities privately under [Security policy](../SECURITY.md).

> [!NOTE]
> The offline adult-domain index is included in the source distribution under its [separate data license](../DATA_LICENSE.md). It does not send visited URLs to an external classification service.
