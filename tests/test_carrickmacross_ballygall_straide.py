from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class CarrickmacrossBallygallStraideTests(unittest.TestCase):
    def test_carrickmacross_allows_five_page_newsletter(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "clogher" / "carrickmacross.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(int(payload.get("max_bulletin_pages") or 0), 5)

    def test_ballygall_scrapes_blog_not_pinned_sept(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "dublin" / "ballygallparish.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("site_type"), "predicted_dated_pdf")
        self.assertIn("Newsletter-for-November-8th.pdf", payload.get("start_url", ""))
        self.assertNotIn("November-1st", payload.get("start_url", ""))
        self.assertNotIn("October25th", payload.get("start_url", ""))
        self.assertIn("Newsletter-for-", " ".join(payload.get("href_patterns") or []))

    def test_straide_scrapes_and_bohola_aliases(self) -> None:
        straide = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "achonry" / "straide.json").read_text(
                encoding="utf-8"
            )
        )
        bohola = json.loads(
            (REPO_ROOT / "parishes" / "recipes" / "achonry" / "bohola.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(straide.get("site_type"), "predicted_dated_pdf")
        self.assertIn("Bohola-Straide-Newsletter-8th-November-2026.pdf", straide["start_url"])
        self.assertNotIn("1st-November", straide["start_url"])
        self.assertTrue(bohola.get("skip"))
        self.assertEqual(bohola.get("alias_of"), "straide")


if __name__ == "__main__":
    unittest.main()
