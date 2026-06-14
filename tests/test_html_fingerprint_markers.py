"""Marker regex tests for extension/html_fingerprint.js (mirrored patterns)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THREEPATRONS_SNIPPET = (ROOT.parent / "threepatrons.txt").read_text(encoding="utf-8", errors="replace")[:120000]


class HtmlFingerprintMarkerTests(unittest.TestCase):
    def test_three_patrons_dropfiles_markers(self) -> None:
        html = THREEPATRONS_SNIPPET
        self.assertRegex(html, re.compile(r"mod_dropfiles_latest", re.I))
        self.assertRegex(html, re.compile(r"mod_downloadlink", re.I))
        self.assertRegex(html, re.compile(r"weekly-bulletins/104", re.I))
        self.assertRegex(html, re.compile(r"com_dropfiles", re.I))

    def test_sequential_bulletin_url_in_snippet(self) -> None:
        m = re.search(r"/Weekly-Bulletins/\d+/Sunday-", THREEPATRONS_SNIPPET, re.I)
        self.assertIsNotNone(m)


if __name__ == "__main__":
    unittest.main()
