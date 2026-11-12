# Publishing checklist

This checklist is for maintainers preparing a public source release.

## Rights and trust

- [x] Bundle the offline adult-domain index only with documented upstream license, attribution, pinned source revision, and build verification; see [data licensing](../DATA_LICENSE.md).
- [ ] Review third-party fonts, images, dependencies, and trademarks before tagging.
- [ ] Verify GitHub security reporting configuration; no unowned security mailbox should be advertised.
- [ ] Confirm that no local browsing records, vaults, `.env` files, tokens, or browser profiles are in the Git tree.

## Platform acceptance

- [ ] Run the automated test suite and browser API simulations.
- [ ] Complete a real Chromium-family extension-to-service conceal/reveal test.
- [ ] Complete a real Firefox-family extension-to-service conceal/reveal test.
- [ ] Verify native-messaging manifest registration on supported Linux packaging paths.
- [ ] Confirm bookmark restore with a disposable profile and independent bookmark export.
- [ ] Check tray behavior in representative Wayland and X11 sessions.
- [ ] Validate package builds and dependency installation on intended distribution families.

## Documentation and artwork

- [ ] Run `python scripts/check_docs.py` and verify all screenshots and internal links.
- [ ] Replace source-aligned tray UI renders with real PySide6 screenshots captured on a disposable Linux desktop before claiming native integration evidence.
- [ ] Confirm [README](../README.md), [Getting started](../docs/GETTING_STARTED.md), and [Privacy](../docs/PRIVACY.md) reflect the shipped build.
- [ ] Keep the supplied transparent brand banner as `assets/branding/veil-banner.png`.
- [ ] Upload `assets/branding/veil-social-preview.png` in **Repository Settings → General → Social preview**.
- [ ] Use a concise repository description and relevant GitHub topics; avoid unsupported certification claims.

## Publish

- [ ] Check that the GitHub Actions checks have passed on the release commit.
- [ ] Create an appropriate signed or verified release tag according to repository policy.
- [ ] Review `.github/RELEASE_NOTES.md` against the tagged source.
- [ ] Download the generated archive from GitHub Releases and inspect its contents and checksum.
- [ ] Confirm README image display in GitHub's light and dark themes.

> [!NOTE]
> Automated tests and browser simulations are useful regression signals, not substitutes for real browser, desktop, and packaging acceptance on intended systems.
