from __future__ import annotations

import unittest
from datetime import date

from harvester.html_capture import (
    page_looks_like_listing,
    pick_best_link,
    score_link_for_target,
)


class HtmlCaptureTests(unittest.TestCase):
    def test_pick_best_link_prefers_target_week(self) -> None:
        target = date(2026, 6, 14)
        links = [
            {"href": "https://x.com/old.pdf", "text": "May 2026", "index": 0},
            {"href": "https://x.com/140626.pdf", "text": "This week", "index": 1},
        ]
        best = pick_best_link(links, target)
        self.assertEqual(best, "https://x.com/140626.pdf")

    def test_page_looks_like_listing(self) -> None:
        self.assertTrue(
            page_looks_like_listing("https://parish.com/category/newsletter/", 12)
        )
        self.assertFalse(page_looks_like_listing("https://parish.com/about/", 3))

    def test_stale_link_scores_lower(self) -> None:
        target = date(2026, 6, 14)
        fresh = score_link_for_target(target, "https://x.com/140626.pdf", "bulletin", 0)
        stale = score_link_for_target(target, "https://x.com/010126.pdf", "old", 0)
        self.assertGreater(fresh, stale)


if __name__ == "__main__":
    unittest.main()
