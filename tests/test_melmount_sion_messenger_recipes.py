from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class MelmountSionMessengerRecipeTests(unittest.TestCase):
    def _assert_click_then_download(self, relative: str, key: str) -> None:
        path = REPO_ROOT / relative
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("parish_key"), key)
        self.assertEqual(payload.get("site_type"), "parish_messenger")
        actions = [str(s.get("action") or "") for s in (payload.get("steps") or [])]
        self.assertIn("click", actions)
        self.assertIn("download", actions)
        self.assertNotIn("print_to_pdf", actions)
        blob = json.dumps(payload.get("steps") or [])
        self.assertIn("CLICK HERE to load Current Newsletter", blob)
        self.assertNotIn('a[href$=\'.pdf\']', blob)
        self.assertNotIn('a[href$=".pdf"]', blob)
        notes = " ".join(payload.get("do_not") or []).lower()
        self.assertIn("print_to_pdf", notes)
        skip = " ".join(payload.get("href_skip_patterns") or []).lower()
        self.assertIn("giftaid", skip)

    def test_melmount_clicks_current_newsletter(self) -> None:
        self._assert_click_then_download(
            "parishes/recipes/derry/melmountparish.json", "melmountparish"
        )

    def test_sion_mills_clicks_current_newsletter(self) -> None:
        self._assert_click_then_download(
            "parishes/recipes/derry/parishofsionmills.json", "parishofsionmills"
        )


if __name__ == "__main__":
    unittest.main()
