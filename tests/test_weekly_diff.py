from __future__ import annotations

import unittest

from harvester.weekly_diff import MAX_LINES_PER_SIDE, diff_bulletins


class WeeklyDiffTests(unittest.TestCase):
    def test_diff_detects_added_removed_and_kept_lines(self) -> None:
        last_week = """
        This is a long parish line about mass times and confessions this weekend.
        Another very long notice about volunteers needed for parish hall cleaning.
        """
        this_week = """
        This is a long parish line about mass times and confessions this weekend.
        Brand new long announcement for youth retreat registration this Friday evening.
        """

        result = diff_bulletins(this_week, last_week)

        self.assertEqual(1, result["kept_count"])
        self.assertIn(
            "Brand new long announcement for youth retreat registration this Friday evening.",
            result["added_lines"],
        )
        self.assertIn(
            "Another very long notice about volunteers needed for parish hall cleaning.",
            result["removed_lines"],
        )

    def test_diff_preserves_first_30_in_printed_order(self) -> None:
        this_week_lines = [
            f"Line number {i} with enough text length to pass the normalization filter and stay included."
            for i in range(MAX_LINES_PER_SIDE + 15)
        ]
        last_week = ""
        this_week = "\n".join(this_week_lines)

        result = diff_bulletins(this_week, last_week)

        self.assertEqual(this_week_lines[:MAX_LINES_PER_SIDE], result["added_lines"])
        self.assertEqual([], result["removed_lines"])
        self.assertEqual("truncated_to_30_lines_per_side", result.get("note"))

    def test_short_irish_notice_and_case_only_change(self):
        result = diff_bulletins("AIFREANN\nFéile Dé hAoine", "Aifreann")
        self.assertEqual(result["added_lines"], ["Féile Dé hAoine"])
        self.assertEqual(result["kept_count"], 1)

    def test_empty_prior_text_case(self) -> None:
        this_week = "A sufficiently long line about this week's services and community notices."

        result = diff_bulletins(this_week, "")

        self.assertEqual(0, result["kept_count"])
        self.assertEqual([], result["removed_lines"])
        self.assertEqual(
            ["A sufficiently long line about this week's services and community notices."],
            result["added_lines"],
        )


if __name__ == "__main__":
    unittest.main()
