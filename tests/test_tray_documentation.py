"""Keep tray documentation aligned with the menu exposed by the app."""

from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parent.parent
TRAY = (ROOT / 'veil/tray.py').read_text(encoding='utf-8')
GUIDE = (ROOT / 'docs/TRAY_MENU.md').read_text(encoding='utf-8')


class TrayDocumentationTests(unittest.TestCase):
    def test_documented_controls_are_present(self):
        entries = (
            'Reveal on Demand (Phase 2)',
            'Reveal All Concealed Tabs',
            'Camouflage Mode',
            'Discreet Audio Chime',
            'Emergency Boss Key',
            'Instant Panic (Purge & Minimize)',
            'Sanitize Clipboard',
            'Shred Temporary Caches & Thumbnails',
            'Rescan Installed Browsers',
            'Quit Veil',
        )
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertIn(entry, TRAY)
                self.assertIn(entry, GUIDE)

    def test_reveal_all_is_standby_only(self):
        self.assertIn('self.action_reveal_all.setVisible(not is_active)', TRAY)
        self.assertIn('only in standby', GUIDE)

    def test_visual_references_are_png_images(self):
        for filename in (
            'tray-shield-active.png', 'tray-standby.png',
            'tray-preferences.png', 'tray-tools.png',
        ):
            with self.subTest(filename=filename):
                content = (ROOT / 'docs/images' / filename).read_bytes()
                self.assertTrue(content.startswith(b'\x89PNG\r\n\x1a\n'))
                width, height = struct.unpack('>II', content[16:24])
                self.assertGreaterEqual(width, 1000)
                self.assertGreaterEqual(height, 600)

    def test_tray_mockups_are_labeled_as_such(self):
        self.assertIn('mockups', GUIDE)
        self.assertIn('not captures', GUIDE)
        self.assertIn('running Qt', GUIDE)


if __name__ == '__main__':
    unittest.main()
