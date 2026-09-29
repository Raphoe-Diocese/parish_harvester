"""Referee Brain slice 1b — picker challenge."""
from __future__ import annotations

import unittest
from datetime import date

from harvester.picker_challenge import challenge_pin_against_listing


class PickerChallengeTests(unittest.TestCase):
    TARGET = date(2026, 9, 27)
    PIN_OLD = (
        "https://example.parish/wp-content/uploads/2026/09/"
        "Parish-Bulletin-20th-September-2026.pdf"
    )
    LISTING_NEW = (
        "https://example.parish/wp-content/uploads/2026/09/"
        "Parish-Bulletin-27th-September-2026.pdf"
    )
    LISTING_OLDER = (
        "https://example.parish/wp-content/uploads/2026/09/"
        "Parish-Bulletin-13th-September-2026.pdf"
    )
    FAR_AHEAD = (
        "https://example.parish/wp-content/uploads/2026/10/"
        "Parish-Bulletin-25th-October-2026.pdf"
    )

    def test_newer_listing_beats_stale_pin(self) -> None:
        scored = [
            (date(2026, 9, 20), self.PIN_OLD),
            (date(2026, 9, 27), self.LISTING_NEW),
            (date(2026, 9, 13), self.LISTING_OLDER),
        ]
        verdict = challenge_pin_against_listing(self.PIN_OLD, scored, self.TARGET)
        self.assertTrue(verdict.challenged)
        self.assertEqual(verdict.chosen_url, self.LISTING_NEW)
        self.assertEqual(verdict.pin_date, date(2026, 9, 20))
        self.assertEqual(verdict.listing_date, date(2026, 9, 27))
        self.assertIn("picker_wrong", verdict.reason)
        self.assertIn("2026-09-20", verdict.reason)
        self.assertIn("2026-09-27", verdict.reason)

    def test_equal_or_older_listing_keeps_pin(self) -> None:
        scored = [
            (date(2026, 9, 27), self.LISTING_NEW),
            (date(2026, 9, 13), self.LISTING_OLDER),
        ]
        pin = self.LISTING_NEW
        verdict = challenge_pin_against_listing(pin, scored, self.TARGET)
        self.assertFalse(verdict.challenged)
        self.assertEqual(verdict.chosen_url, pin)

        scored_older_only = [(date(2026, 9, 13), self.LISTING_OLDER)]
        verdict2 = challenge_pin_against_listing(self.LISTING_NEW, scored_older_only, self.TARGET)
        self.assertFalse(verdict2.challenged)
        self.assertEqual(verdict2.chosen_url, self.LISTING_NEW)

    def test_undated_pin_beaten_by_this_week_listing(self) -> None:
        undated = "https://example.parish/wp-content/uploads/bulletin.pdf"
        scored = [(date(2026, 9, 27), self.LISTING_NEW)]
        verdict = challenge_pin_against_listing(undated, scored, self.TARGET)
        self.assertTrue(verdict.challenged)
        self.assertEqual(verdict.chosen_url, self.LISTING_NEW)
        self.assertIn("undated pin", verdict.reason)

    def test_empty_listing_keeps_pin(self) -> None:
        verdict = challenge_pin_against_listing(self.PIN_OLD, [], self.TARGET)
        self.assertFalse(verdict.challenged)
        self.assertEqual(verdict.chosen_url, self.PIN_OLD)

    def test_far_ahead_listing_does_not_beat_pin(self) -> None:
        # Outside MAX_STALE_DAYS_FROM_TARGET grace — ignore as challenger.
        scored = [(date(2026, 10, 25), self.FAR_AHEAD)]
        verdict = challenge_pin_against_listing(self.PIN_OLD, scored, self.TARGET)
        self.assertFalse(verdict.challenged)
        self.assertEqual(verdict.chosen_url, self.PIN_OLD)


if __name__ == "__main__":
    unittest.main()
