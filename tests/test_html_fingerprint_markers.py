"""Marker regex tests for extension/html_fingerprint.js (mirrored patterns)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
THREEPATRONS_SNIPPET = (PARENT / "threepatrons.txt").read_text(encoding="utf-8", errors="replace")[:120000]
CLONLEIGH_SNIPPET = (PARENT / "clonleighparish.txt").read_text(encoding="utf-8", errors="replace")[:200000]

WP_HTML_MARKERS = [
    (r'wp-block-paragraph|class="entry-content', 14, "WP entry content blocks"),
    (r"wordpress|wp-json|wp-content/themes", 10, "WordPress signals"),
    (r"newsletter|bulletin|pastoral area", 12, "newsletter in title/slug"),
    (r"category-newsletter|tag-newsletter", 8, "newsletter taxonomy"),
]
IMAGE_BODY_MARKER = re.compile(r"wp-content/uploads/.*\.(jpg|jpeg|png|webp)", re.I)
IMAGE_HEAD_MARKER = re.compile(r"wp-content/uploads/.*\.(jpg|jpeg|png|webp)", re.I)


def _split_head_body(html: str) -> tuple[str, str]:
    lower = html.lower()
    body_idx = lower.find("<body")
    if body_idx < 0:
        return html, ""
    return html[:body_idx], html[body_idx:]


def _score_markers(html: str, markers: list[tuple[str, int, str]], *, body_only: bool = False) -> int:
    head, body = _split_head_body(html)
    haystack = body if body_only else html
    score = 0
    for pattern, weight, _label in markers:
        if re.search(pattern, haystack, re.I):
            score += weight
    return score


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

    def test_clonleigh_wordpress_html_markers_score_high(self) -> None:
        score = _score_markers(CLONLEIGH_SNIPPET, WP_HTML_MARKERS)
        self.assertGreaterEqual(score, 30, "Clonleigh should match wordpress_html_post fingerprint")

    def test_clonleigh_has_entry_content_text_not_image_only(self) -> None:
        self.assertIn('class="entry-content', CLONLEIGH_SNIPPET)
        self.assertGreater(CLONLEIGH_SNIPPET.count("wp-block-paragraph"), 5)
        self.assertRegex(
            CLONLEIGH_SNIPPET,
            re.compile(r"Strabane Pastoral Area Newsletter for Sunday 14th June 2026", re.I),
        )

    def test_clonleigh_image_marker_in_head_not_body_alone(self) -> None:
        head, body = _split_head_body(CLONLEIGH_SNIPPET)
        self.assertTrue(IMAGE_HEAD_MARKER.search(head), "og:image lives in head")
        body_image_hits = len(IMAGE_BODY_MARKER.findall(body))
        self.assertEqual(
            body_image_hits,
            0,
            "Clonleigh body should not contain wp-content JPEG paths (avoids image false positive)",
        )

    def test_clonleigh_newsletter_slug_path_pattern(self) -> None:
        path = "/2026/06/12/strabane-pastoral-area-newsletter-for-sunday-14th-june-2026/"
        self.assertRegex(path, re.compile(r"newsletter|bulletin|pastoral", re.I))
        self.assertRegex(path, re.compile(r"/\d{4}/\d{2}/\d{2}/"))


if __name__ == "__main__":
    unittest.main()
