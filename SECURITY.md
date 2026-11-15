# Security policy

## Supported versions

The active release is **1.0**. Earlier development archives are not supported for security fixes.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature for the repository if it is enabled. Otherwise contact the repository maintainer through an established private channel before publishing technical exploitation details. Avoid attaching sensitive browser profiles, unredacted paths, protected URLs, or vault material.

Useful reports include affected version, operating system family, browser family, a minimal reproduction, expected versus observed behavior, and any relevant redacted logs.

## Scope

Security-relevant findings include vault record disclosure, unsafe restoration/deletion, native-messaging authorization errors, IPC boundary issues, privilege escalation, and unexpectedly public persistence of protected data.

Veil is a browser-visibility tool. It is not designed to protect an unlocked or compromised host from privileged inspection. See [Privacy and limitations](docs/PRIVACY.md).
