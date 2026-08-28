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
    def test_recipe_prints_newest_html_newsletter_and_skips_forms(self) -> None:
        payload = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "parishofardstraweast")
        self.assertEqual(payload.get("start_url"), LISTING)
        self.assertTrue(payload.get("disable_stale_rescrape_fallback"))
        self.assertNotIn("skip", payload)

        patterns = " ".join(payload.get("href_patterns") or [])
        self.assertIn("templates/?a=", patterns)
        skip = " ".join(payload.get("href_skip_patterns") or []).lower()
        for token in ("dataentry", "parishioner", "gdpr", "privacy"):
            self.assertIn(token, skip)

        notes = " ".join(payload.get("do_not") or []).lower()
        self.assertIn("dataentryform", notes)
        self.assertIn("parishioner", notes)
        self.assertIn("gdpr", notes)
        self.assertIn("privacy", notes)

        steps = payload.get("steps") or []
        self.assertGreaterEqual(len(steps), 3)
        self.assertEqual(steps[0].get("action"), "goto")
        self.assertEqual(steps[0].get("url"), LISTING)

        click = steps[1]
        self.assertEqual(click.get("action"), "click")
        self.assertEqual(click.get("pick_strategy"), "newest_dated")
        self.assertIn("templates/?a=", click.get("selector") or "")
        self.assertNotIn("DataEntry", json.dumps(steps))

        print_step = steps[-1]
        self.assertEqual(print_step.get("action"), "print_to_pdf")
        self.assertTrue(print_step.get("skip_listing_nav"))


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
