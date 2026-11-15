# Things to check before putting out a build

This is mostly here because I forget little things when I'm in a hurry.

- [x] The offline domain list has its source and license recorded in [DATA_LICENSE.md](../DATA_LICENSE.md).
- [ ] Check that I haven't committed browser profiles, vault files, passwords, tokens or anything from a local `.env`.
- [ ] Check the licenses of any new dependencies or artwork.
- [ ] Run the Python tests, browser simulations and `python scripts/check_docs.py`.
- [ ] Test hiding and restoring a tab in a separate Chromium profile.
- [ ] Try the same with Firefox. Remember that a temporary debug extension disappears when Firefox restarts.
- [ ] Try restoring bookmarks from a spare profile, with an ordinary bookmark export saved elsewhere.
- [ ] Check native messaging and the tray in a real desktop session, not just GitHub Actions.
- [ ] Look over the README, install guide and privacy notes in case something changed since the last release.
- [ ] Check that the banner and screenshots still display correctly, and keep mockups labelled as mockups.
- [ ] Make sure the package version, extension manifests and GitHub tag agree.
- [ ] Download the actual release archive, check its checksum and try installing from it.

A green GitHub run is a good sign. It's not the same as testing every desktop and browser people might be using.
