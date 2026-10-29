from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class BlanchardstownCurrentNewsletterTests(unittest.TestCase):
    def test_uses_permanent_redirect_not_singular_newsletter_path(self) -> None:
        path = REPO_ROOT / "parishes" / "recipes" / "dublin" / "blanchardstown.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), "blanchardstown")
        self.assertEqual(
            payload.get("start_url"),
            "https://www.blanchardstownparish.ie/current-newsletter/",
        )
        self.assertEqual(payload.get("site_type"), "permanent_redirect_document")
        self.assertTrue(payload.get("disable_stale_rescrape_fallback"))
        self.assertNotIn("/newsletter/", payload.get("start_url", "").replace("current-newsletter", ""))
        steps = payload.get("steps") or []
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].get("action"), "download")
        self.assertTrue(steps[0].get("use_target_url"))


if __name__ == "__main__":
    unittest.main()
