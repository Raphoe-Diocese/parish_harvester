from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class DublinOct25ScrapeTests(unittest.TestCase):
    def test_baldoyle_scrapes_not_pinned_18th(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "dublin" / "baldoyleparish.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("site_type"), "http_scrape_newest_pdf")
        actions = [s.get("action") for s in (payload.get("steps") or [])]
        self.assertEqual(actions, ["goto"])
        self.assertIn("25th-October", payload.get("example_url") or "")

    def test_ballinteer_scrapes_20261025(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "dublin" / "ballinteerparish.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("site_type"), "http_scrape_newest_pdf")
        self.assertIn("20261025", payload.get("example_url") or "")
        self.assertNotIn("20261018", json.dumps(payload.get("steps") or []))

    def test_ballybrack_clicks_listing_not_pinned_week(self) -> None:
        path = (
            REPO_ROOT
            / "parishes"
            / "recipes"
            / "dublin"
            / "ballybrack-killiney-parish.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("start_url"), "https://www.ballybrack-killiney-parish.org/news.html")
        actions = [s.get("action") for s in (payload.get("steps") or [])]
        self.assertEqual(actions, ["goto", "click", "print_to_pdf"])
        dump = json.dumps(payload.get("steps") or [])
        self.assertNotIn("17th-18th", dump)


if __name__ == "__main__":
    unittest.main()
