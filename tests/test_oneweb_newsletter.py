"""One.com newsletter direct-download URL logic (Claudy parish)."""
from __future__ import annotations

import unittest
from datetime import date

from harvester.utils import oneweb_newsletter_download_urls, rewrite_date_url


class OnewebNewsletterUrlTests(unittest.TestCase):
    def test_rewrite_claudy_example_to_sunday(self) -> None:
        base = "http://parishofclaudy.com/onewebmedia/NEWSLETTER%2012-4-26.docx"
        target = date(2026, 6, 14)
        self.assertIn(
            "14-6-26",
            rewrite_date_url(base, target),
        )

    def test_generates_filename_variants(self) -> None:
        base = "http://parishofclaudy.com/onewebmedia/NEWSLETTER%2012-4-26.docx"
        target = date(2026, 6, 14)
        urls = oneweb_newsletter_download_urls(base, target)
        self.assertGreaterEqual(len(urls), 2)
        joined = " ".join(urls).lower()
        self.assertIn("newsletter", joined)
        self.assertIn("14-6-26", joined)


if __name__ == "__main__":
    unittest.main()
