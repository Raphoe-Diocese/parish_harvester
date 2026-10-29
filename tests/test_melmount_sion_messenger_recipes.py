from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class MelmountSionSharedHtmlTests(unittest.TestCase):
    def test_melmount_prints_html_parish_news(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "derry" / "melmountparish.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "melmountparish")
        self.assertEqual(payload.get("site_type"), "html_text_bulletin")
        self.assertEqual(
            payload.get("start_url"),
            "https://www.melmountparish.com/parishnews.html",
        )
        actions = [str(s.get("action") or "") for s in (payload.get("steps") or [])]
        self.assertIn("print_to_pdf", actions)
        self.assertNotIn("click", actions)
        print_step = next(s for s in payload["steps"] if s.get("action") == "print_to_pdf")
        self.assertTrue(print_step.get("skip_listing_nav"))

    def test_sion_mills_aliases_melmount(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "derry" / "parishofsionmills.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "parishofsionmills")
        self.assertTrue(payload.get("skip"))
        self.assertEqual(payload.get("alias_of"), "melmountparish")
        self.assertEqual(payload.get("steps") or [], [])


if __name__ == "__main__":
    unittest.main()
