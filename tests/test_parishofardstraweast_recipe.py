from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from harvester.bulletin_freshness import (
    check_bulletin_freshness,
    extract_bulletin_date_from_text,
    verdict_for_extracted_date,
)
from harvester.replay import (
    _href_allowed_for_click,
    _href_is_skipped,
    _is_non_bulletin_url,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO_ROOT / "parishes" / "recipes" / "derry" / "parishofardstraweast.json"
LISTING = "http://parishofardstraweast.com/parishnews.html"
FORM_PDF = "http://parishofardstraweast.com/pdf/DataEntryFormPdf.pdf"
GDPR_PDF = "http://parishofardstraweast.com/pdf/GDPR.pdf"
JULY_HTML = "http://109.228.27.39/templates/?a=22826&z=19"
HARVEST_SUNDAY = date(2026, 8, 23)


class ArdstrawEastRecipeTests(unittest.TestCase):
    def test_recipe_prints_latest_on_parishnews_page(self) -> None:
        """29/10/2026: Latest block on parishnews.html is this week; Past list lagged."""
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "parishofardstraweast")
        self.assertEqual(payload.get("start_url"), LISTING)
        self.assertTrue(payload.get("disable_stale_rescrape_fallback"))
        self.assertNotIn("skip", payload)
        self.assertEqual(payload.get("site_type"), "html_text_bulletin")

        notes = " ".join(
            (payload.get("do_not") or []) + (payload.get("operator_notes") or [])
        ).lower()
        self.assertIn("dataentry", notes)
        self.assertIn("gdpr", notes)
        self.assertIn("past", notes)

        steps = payload.get("steps") or []
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].get("action"), "goto")
        self.assertEqual(steps[0].get("url"), LISTING)
        self.assertEqual(steps[1].get("action"), "print_to_pdf")
        self.assertTrue(steps[1].get("skip_listing_nav"))
        actions = [str(s.get("action") or "") for s in steps]
        self.assertNotIn("click", actions)


class ArdstrawEastSkipNameTests(unittest.TestCase):
    def test_form_gdpr_privacy_and_parishioner_are_non_bulletin(self) -> None:
        self.assertTrue(_is_non_bulletin_url(FORM_PDF))
        self.assertTrue(_is_non_bulletin_url(GDPR_PDF))
        self.assertTrue(
            _is_non_bulletin_url(
                "http://parishofardstraweast.com/pdf/New-Parishioner-Form.pdf"
            )
        )
        self.assertTrue(
            _is_non_bulletin_url(
                "http://parishofardstraweast.com/pdf/Privacy.pdf"
            )
        )
        self.assertFalse(_is_non_bulletin_url(JULY_HTML))

    def test_href_skip_list_blocks_form_and_keeps_july_article(self) -> None:
        skip = ["dataentry", "dataentryform", "parishioner", "gdpr", "privacy"]
        patterns = ["templates/?a="]
        self.assertTrue(_href_is_skipped(FORM_PDF, skip))
        self.assertTrue(_href_is_skipped(GDPR_PDF, skip))
        self.assertFalse(_href_is_skipped(JULY_HTML, skip))
        self.assertFalse(_href_allowed_for_click(FORM_PDF, patterns, skip))
        self.assertTrue(_href_allowed_for_click(JULY_HTML, patterns, skip))


class ArdstrawEastFreshnessTests(unittest.TestCase):
    def test_form_url_has_no_date_and_july_heading_is_stale(self) -> None:
        form_verdict = check_bulletin_freshness(FORM_PDF, HARVEST_SUNDAY)
        self.assertEqual(form_verdict.status, "unknown")
        self.assertEqual(form_verdict.reason, "no_date_in_url")

        article_verdict = check_bulletin_freshness(JULY_HTML, HARVEST_SUNDAY)
        self.assertEqual(article_verdict.status, "unknown")

        heading = (
            "Sunday, 5th July 2026 - Ardstraw East Parish Newsletter\n"
            "14th Sunday in Ordinary Time\n"
        )
        extracted = extract_bulletin_date_from_text(heading)
        self.assertEqual(extracted, date(2026, 7, 5))
        stale = verdict_for_extracted_date(extracted, HARVEST_SUNDAY)
        self.assertEqual(stale.status, "stale")
        self.assertNotEqual(extracted, HARVEST_SUNDAY)


if __name__ == "__main__":
    unittest.main()
