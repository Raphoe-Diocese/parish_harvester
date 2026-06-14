"""Pattern H newsletter number advance for Three Patrons / Banagher."""
from __future__ import annotations

import unittest
from datetime import date

from harvester.utils import rewrite_newsletter_number_for_target


class NewsletterNumberTargetTests(unittest.TestCase):
    def test_three_patrons_june_from_april_example(self) -> None:
        url = "https://www.threepatrons.org/files/10/Weekly-Bulletins/95/Sunday-12th-April-2026"
        target = date(2026, 6, 14)
        out = rewrite_newsletter_number_for_target(url, target)
        self.assertIn("/Weekly-Bulletins/104/", out)


if __name__ == "__main__":
    unittest.main()
