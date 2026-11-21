"""Quality-adjust baseline without compromising the 10% harvest safety guard."""
import unittest
from copy import deepcopy

from scripts.normalise_guard_baseline import normalise


class GuardBaselineTests(unittest.TestCase):
    def test_known_false_downloads_excluded_from_previous_ok(self):
        status = {
            "target_date": "2026-11-15",
            "summary": {"ok": 3},
            "parishes": {
                "oldcastle": {"outcome": "ok"},
                "nextweek": {"outcome": "ok"},
                "real": {"outcome": "ok"},
            },
        }
        report = {
            "target_date": "2026-11-15",
            "downloaded": [
                {"parish": "oldcastle", "file_type": "html_render", "url": "https://www.dioceseofmeath.ie/map-of-parishes"},
                {"parish": "nextweek", "file_type": "pdf", "bulletin_date": "2026-11-22", "url": "https://example.ie/next.pdf"},
                {"parish": "real", "file_type": "pdf", "bulletin_date": "2026-11-15", "url": "https://example.ie/current.pdf"},
            ],
            "failed": [], "stale_rejected": [],
            "summary": {"downloaded": 3, "failed": 0, "stale_rejected": 0},
        }
        self.assertEqual(normalise(status, report), 2)
        self.assertEqual(status["summary"]["ok"], 1)
        self.assertEqual(status["parishes"]["real"]["outcome"], "ok")

    def test_mismatched_weeks_do_not_change_baseline(self):
        status = {"target_date": "2026-11-22", "summary": {"ok": 3},
                  "parishes": {"a": {"outcome": "ok"}}}
        report = {"target_date": "2026-11-15",
                  "downloaded": [{"parish": "a", "file_type": "html_render",
                                  "url": "https://www.dioceseofmeath.ie/map-of-parishes"}]}
        original = deepcopy(status)
        self.assertEqual(normalise(status, report), 0)
        self.assertEqual(status, original)


if __name__ == "__main__":
    unittest.main()
