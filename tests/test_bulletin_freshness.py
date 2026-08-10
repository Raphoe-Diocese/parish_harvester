"""Tests for bulletin freshness safety net."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from harvester.bulletin_freshness import (
    apply_freshness_safety_net,
    check_bulletin_freshness,
    extract_bulletin_date,
    mark_result_stale,
    suggest_retry_strategy,
    week_window,
)
from harvester.fetcher import FetchResult, ParishEntry


class BulletinFreshnessTests(unittest.TestCase):
    def test_extract_bulletin_date_supports_common_formats(self) -> None:
        self.assertEqual(
            extract_bulletin_date("https://x.com/bulletin_150626.pdf"),
            date(2026, 6, 15),
        )
        self.assertEqual(
            extract_bulletin_date("https://x.com/bulletin-2026-06-15.pdf"),
            date(2026, 6, 15),
        )
        self.assertEqual(
            extract_bulletin_date(
                "https://saintanthonys.uk/wp-content/uploads/2026/06/bulletin210611sunot.pdf"
            ),
            date(2026, 6, 21),
        )
        self.assertEqual(
            extract_bulletin_date(
                "https://www.bangorparish.com/wp-content/uploads/14-June-2026-NEWSLETTER.pdf"
            ),
            date(2026, 6, 14),
        )

    def test_check_freshness_in_week_is_fresh(self) -> None:
        target = date(2026, 6, 14)  # Sunday
        url = "https://example.com/bulletin_140626.pdf"
        verdict = check_bulletin_freshness(url, target)
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_check_freshness_old_date_is_stale(self) -> None:
        target = date(2026, 6, 14)
        old = (target - timedelta(days=20)).strftime("%d%m%y")
        verdict = check_bulletin_freshness(f"https://example.com/bulletin_{old}.pdf", target)
        self.assertEqual(verdict.status, "stale")

    def test_unknown_date_is_not_auto_rejected(self) -> None:
        target = date(2026, 6, 14)
        verdict = check_bulletin_freshness("https://example.com/weekly-bulletin.pdf", target)
        self.assertEqual(verdict.status, "unknown")

    def test_opaque_cdn_hash_is_not_misread_as_a_date(self) -> None:
        # Wix/Squarespace-style hashed filenames can contain a coincidental
        # 6-digit run that looks like DDMMYY (e.g. carrickparish.org 2026-08-09
        # false "2076-07-29" rejection). No genuine date exists in this URL.
        url = (
            "https://www.carrickparish.org/_files/ugd/"
            "15976c_67e290776b824ccfb8ce43943f2620aa.pdf"
        )
        self.assertIsNone(extract_bulletin_date(url))
        target = date(2026, 8, 9)
        verdict = check_bulletin_freshness(url, target)
        self.assertEqual(verdict.status, "unknown")

    def test_dd_mm_yy_dot_filename_not_misread_as_yy_mm_dd(self) -> None:
        # stbrigidsparishbelfast.org uses UK-convention DD.MM.YY filenames
        # ("Parish-Bulletin-09.08.26-FOR-PRINTING.pdf"). The same N.N.NN dot
        # shape is also used by Google Drive folder rows as YY.MM.DD, so a
        # naive single-interpretation parse misread "09.08.26" as 2009-08-26
        # and rejected a genuinely current bulletin as 17-years stale.
        current_url = (
            "https://stbrigidsparishbelfast.org/assets/documents/"
            "Parish-Bulletin-09.08.26-FOR-PRINTING.pdf"
        )
        older_url = (
            "https://stbrigidsparishbelfast.org/assets/documents/"
            "Parish-Bulletin-26.07.26-FOR-PRINTING.pdf"
        )
        self.assertEqual(extract_bulletin_date(current_url), date(2026, 8, 9))
        self.assertEqual(extract_bulletin_date(older_url), date(2026, 7, 26))
        target = date(2026, 8, 9)
        verdict = check_bulletin_freshness(current_url, target)
        self.assertEqual(verdict.status, "fresh")

    def test_wix_query_string_dated_filename_is_decoded(self) -> None:
        # parishofhannahstown.com (Wix) serves the real bulletin at an opaque
        # hashed path with the human-readable, dated filename only in a
        # URL-encoded query parameter: "?dn=Bulletin%207th%20June%202026.docx".
        # Without decoding "%20" first, the ordinal/month/year run together
        # and no date pattern can match, so a 9-week-stale bulletin was
        # reported as fresh (found 2026-08-09, parishofhannahstown, once
        # replay.py started returning the real download URL instead of the
        # listing page it was clicked from).
        stale_url = (
            "https://www.parishofhannahstown.com/_files/ugd/"
            "809bbb_86ee53ed5ed240e0a1c39055e55311b7.docx"
            "?dn=Bulletin%207th%20June%202026.docx"
        )
        self.assertEqual(extract_bulletin_date(stale_url), date(2026, 6, 7))
        verdict = check_bulletin_freshness(stale_url, date(2026, 8, 9))
        self.assertEqual(verdict.status, "stale")

    def test_ordinal_sunday_count_in_wp_filename_is_not_a_day(self) -> None:
        # derriaghycatholicparish.com names its weekly image
        # "19th-Suday-in-ordinary-time-724x1024.png" — the leading "19" is
        # the LITURGICAL Sunday-count ("19th Sunday in Ordinary Time" is the
        # correct bulletin for 09/08/2026), not a day-of-month. The generic
        # slug_day fallback previously misread it as day=19, producing
        # 2026-08-19 (10 days ahead of target) and wrongly rejecting a
        # genuinely correct, fresh bulletin as stale (found 2026-08-10).
        url = (
            "https://derriaghycatholicparish.com/wp-content/uploads/2026/08/"
            "19th-Suday-in-ordinary-time-724x1024.png"
        )
        extracted = extract_bulletin_date(url)
        self.assertNotEqual(extracted, date(2026, 8, 19))
        verdict = check_bulletin_freshness(url, date(2026, 8, 9))
        self.assertEqual(verdict.status, "fresh")

    def test_ordinal_day_of_month_still_extracted_when_not_a_sunday_count(
        self,
    ) -> None:
        # Regression guard for the fix above: "9th-August-2026.pdf"
        # (antrimparish) has a leading ordinal too, but it's a genuine
        # day-of-month (followed by a month name), not a liturgical
        # Sunday-count. The ordinal-Sunday-count fix must not blind the
        # generic slug_day fallback to real ordinal day-of-month filenames
        # — that regression silently misdated this as 2026-08-01 and only
        # "passed" by accident via the 8-day grace window instead of the
        # correct in_bulletin_week match (found 2026-08-10 while auditing
        # every grace-window "ok" result for hidden freshness bugs).
        url = (
            "https://www-static.antrimparish.com/wp-content/uploads/2026/08/"
            "9th-August-2026.pdf"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 9))
        verdict = check_bulletin_freshness(url, date(2026, 8, 9))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_wp_uploads_ddmmyyyy_four_digit_year_filename(self) -> None:
        # "Parish-Bulletin-09082026.pdf" (st-colmcilles) is a genuine
        # DDMMYYYY filename, but the wp_uploads branch's day_match only
        # checked for a 2-digit year (folder_year % 100), so it silently
        # fell through to the day=1 default and never got a chance to hit
        # the general _DDMMYYYY_RE pattern later in the function (that
        # branch hard-returns). Only "passed" by accident via the 8-day
        # grace window (found 2026-08-10).
        url = (
            "https://st-colmcilles.net/wp-content/uploads/2026/08/"
            "Parish-Bulletin-09082026.pdf"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 9))
        verdict = check_bulletin_freshness(url, date(2026, 8, 9))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_wp_uploads_bare_yyyymmdd_filename_no_separators(self) -> None:
        # "20260705.pdf" (kincasslagh.ie) repeats the upload folder's own
        # year/month verbatim as the filename's leading digits with no
        # separator anywhere — the whole basename is one contiguous 8-digit
        # run, so day_match/day_match_4y/slug_day all fail to find an
        # isolated day-like substring and it silently fell through to the
        # day=1 default (found 2026-08-10: misdated 2026-07-05 as
        # 2026-07-01, which also let a stale bulletin narrowly look fresh
        # via the 8-day grace window in some weeks).
        url = "https://kincasslagh.ie/app/uploads/2026/07/20260705.pdf"
        self.assertEqual(extract_bulletin_date(url), date(2026, 7, 5))
        verdict = check_bulletin_freshness(url, date(2026, 7, 5))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_mark_result_stale_sets_retry_metadata(self) -> None:
        target = date(2026, 6, 14)
        entry = ParishEntry(
            key="testparish",
            display_name="Test Parish",
            pattern="A",
            content_type="pdf",
            example_url="https://example.com/old.pdf",
            bulletin_page="https://example.com/bulletins/",
        )
        result = FetchResult(
            key="testparish",
            display_name="Test Parish",
            status="ok",
            url="https://example.com/bulletin_010526.pdf",
        )
        verdict = check_bulletin_freshness(result.url, target)
        self.assertEqual(verdict.status, "stale")
        marked = mark_result_stale(result, verdict, entry=entry)
        self.assertTrue(marked.is_stale)
        self.assertEqual(marked.status, "error")
        self.assertEqual(marked.retry_strategy, "rescrape_bulletin_page")

    def test_suggest_retry_strategy_for_pattern_parish(self) -> None:
        entry = ParishEntry(
            key="p",
            display_name="P",
            pattern="B",
            content_type="pdf",
            example_url="https://x.com/a.pdf",
        )
        result = FetchResult(key="p", display_name="P", status="ok", url="https://x.com/a.pdf")
        self.assertEqual(suggest_retry_strategy(result, entry), "try_date_patterns")

    def test_apply_freshness_safety_net_writes_retry_queue(self) -> None:
        target = date(2026, 6, 14)
        old = (target - timedelta(days=30)).strftime("%Y-%m-%d")
        results = [
            FetchResult(
                key="staleone",
                display_name="Stale One",
                status="ok",
                url=f"https://example.com/bulletin-{old}.pdf",
            ),
            FetchResult(
                key="freshone",
                display_name="Fresh One",
                status="ok",
                url=f"https://example.com/bulletin-{target.isoformat()}.pdf",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "retry_queue.json"
            payload = apply_freshness_safety_net(
                results,
                target,
                retry_queue_path=queue_path,
            )
            self.assertEqual(len(payload["rejected_from_mega"]), 1)
            self.assertTrue(results[0].is_stale)
            self.assertFalse(results[1].is_stale)
            on_disk = json.loads(queue_path.read_text(encoding="utf-8"))
            self.assertEqual(len(on_disk["retry"]), 1)
            self.assertEqual(on_disk["retry"][0]["strategy"], "manual_review")

    def test_week_window_matches_fetcher(self) -> None:
        target = date(2026, 6, 14)
        start, end = week_window(target)
        self.assertEqual(start, target - timedelta(days=6))
        self.assertEqual(end, target)


if __name__ == "__main__":
    unittest.main()
