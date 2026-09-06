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
    extract_bulletin_date_from_text,
    mark_result_stale,
    suggest_retry_strategy,
    verdict_for_extracted_date,
    week_window,
)
from reportlab.pdfgen import canvas

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

    def test_pdf_heading_date_ignores_memorial_dates(self) -> None:
        text = (
            "Recent Anniversaries : Marie Lavery\n"
            "Bulletin 11th & 12th July 2026\n"
            "Caoimhin was just eight years old when he died on 9th July 2023.\n"
        )
        self.assertEqual(extract_bulletin_date_from_text(text), date(2026, 7, 12))
        self.assertIsNone(
            extract_bulletin_date_from_text(
                "Caoimhin was just eight years old when he died on 9th July 2023."
            )
        )
        self.assertIsNone(
            extract_bulletin_date_from_text(
                "PARISH NEWSLETTER\n"
                "Caoimhin was just eight years old when he died on 9th July 2023."
            )
        )

    def test_pdf_heading_date_reads_adjacent_raphoe_lines(self) -> None:
        text = (
            "WEBSITE parishofraphoe.ie EMAIL: raphoeparish@gmail.com\n"
            "Sunday 19 July 2026\n"
            "RAPHOE PARISH NEWSLETTER\n"
            "St. Eunan's Church, Raphoe\n"
            "Monday 20 July\n"
            "NATIONAL GRANDPARENTS PILGRIMAGE will take place at Knock Shrine "
            "on Sunday 26 July\n"
        )
        self.assertEqual(extract_bulletin_date_from_text(text), date(2026, 7, 19))
        self.assertEqual(
            extract_bulletin_date_from_text(
                "RAPHOE PARISH NEWSLETTER\nSunday 19 July 2026\n"
            ),
            date(2026, 7, 19),
        )

    def test_body_july_date_is_stale_against_august_sunday(self) -> None:
        verdict = verdict_for_extracted_date(date(2026, 7, 12), date(2026, 8, 16))
        self.assertEqual(verdict.status, "stale")
        self.assertEqual(verdict.extracted_date, date(2026, 7, 12))

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
        self.assertEqual(extracted, date(2026, 8, 9))
        verdict = check_bulletin_freshness(url, date(2026, 8, 9))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")
        # Last Sunday is outside week_window — behind grace is gone.
        later = check_bulletin_freshness(url, date(2026, 8, 16))
        self.assertEqual(later.status, "stale")
        self.assertEqual(later.reason, "date_behind_of_target")

    def test_21st_suday_filename_is_23_august_2026(self) -> None:
        url = (
            "https://derriaghycatholicparish.com/wp-content/uploads/2026/08/"
            "21st-Suday-in-ordinary-time.png"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 23))
        verdict = check_bulletin_freshness(url, date(2026, 8, 23))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_liturgical_only_filename_is_not_folder_day_one(self) -> None:
        # Holy Family / Loughshore: Twentieth-Sunday-in-Ordinary-Time.pdf
        # inside /uploads/2026/08/ used to date as 01/08/2026 and fail the
        # 16/08/2026 harvest as 15 days stale.
        url = (
            "https://www.holy-familyparish.com/app/uploads/2026/08/"
            "Twentieth-Sunday-in-Ordinary-Time.pdf"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 16))
        verdict = check_bulletin_freshness(url, date(2026, 8, 16))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "in_bulletin_week")

    def test_ballymena_unpadded_dot_date_and_glenavy_year_month_day(self) -> None:
        self.assertEqual(
            extract_bulletin_date(
                "https://ballymenaparish.org/wp-content/uploads/2026/08/"
                "16.8.26-20th-Sunday.pdf"
            ),
            date(2026, 8, 16),
        )
        self.assertEqual(
            extract_bulletin_date(
                "https://ballymenaparish.org/wp-content/uploads/2026/08/"
                "23.8.26-A4-21st-Sunday.pdf"
            ),
            date(2026, 8, 23),
        )
        self.assertEqual(
            extract_bulletin_date(
                "https://www.glenavyandkilleadparish.com/app/uploads/2026/08/"
                "2026-August-16-Twentieth-Sunday-in-Ordinary-Time.pdf"
            ),
            date(2026, 8, 16),
        )

    def test_hashed_upload_same_month_is_fresh(self) -> None:
        url = (
            "https://www.iskaheenparish.com/wp-content/uploads/2026/08/"
            "240be8f2-b7ae-49f3-8748-f9290e30bcb2-rotated.jpg"
        )
        verdict = check_bulletin_freshness(url, date(2026, 8, 16))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "upload_folder_matches_target_month")

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

    def test_wp_uploads_iso_dashed_filename_repeats_folder_year_month(self) -> None:
        # "2026-07-26.pdf" (clonmanyparish.ie) repeats the upload folder's own
        # year/month as the filename's own leading digits, ISO-dashed. The
        # generic slug_day fallback used to find "07" (the MONTH segment,
        # isolated by hyphens on both sides) as the leftmost 1-2 digit number
        # and return it as the day-of-month, misdating this as the 7th
        # instead of the 26th (found 2026-08-10).
        url = "https://clonmanyparish.ie/wp-content/uploads/2026/07/2026-07-26.pdf"
        self.assertEqual(extract_bulletin_date(url), date(2026, 7, 26))
        verdict = check_bulletin_freshness(url, date(2026, 7, 26))
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

    def test_yearless_month_day_slug_uses_harvest_year(self) -> None:
        # milfordrathmullanparishes.ie / rathmullan — filenames have no year.
        # 09/08/2026 is last Sunday vs 16/08/2026 — outside week_window, stale.
        # 05/07/2026 is 42 days behind and must stay stale
        # (previously these URLs were "unknown" and silently accepted).
        target = date(2026, 8, 16)
        august = (
            "https://milfordrathmullanparishes.ie/wp-content/uploads/"
            "Parish-Newsletter-Sunday-9th-August.pdf"
        )
        july = (
            "https://milfordrathmullanparishes.ie/wp-content/uploads/"
            "Parish-Newsletter-5th-July.pdf"
        )
        self.assertIsNone(extract_bulletin_date(august))
        self.assertIsNone(extract_bulletin_date(july))
        august_verdict = check_bulletin_freshness(august, target)
        self.assertEqual(august_verdict.status, "stale")
        self.assertEqual(august_verdict.extracted_date, date(2026, 8, 9))
        july_verdict = check_bulletin_freshness(july, target)
        self.assertEqual(july_verdict.status, "stale")
        self.assertEqual(july_verdict.extracted_date, date(2026, 7, 5))

    def test_d_m_yy_oneweb_filenames_are_dated(self) -> None:
        target = date(2026, 8, 16)
        limavady = "https://www.limavadyparish.org/onewebmedia/16-8-26.pdf"
        claudy = "http://parishofclaudy.com/onewebmedia/NEWSLETTER 9-8-26.docx"
        self.assertEqual(extract_bulletin_date(limavady), date(2026, 8, 16))
        self.assertEqual(
            check_bulletin_freshness(limavady, target).status, "fresh"
        )
        self.assertEqual(extract_bulletin_date(claudy), date(2026, 8, 9))
        self.assertEqual(check_bulletin_freshness(claudy, target).status, "stale")
        self.assertNotEqual(
            check_bulletin_freshness(claudy, target).reason, "within_grace_days"
        )

    def test_ballymoney_yy_mm_dd_filename_is_this_week(self) -> None:
        url = (
            "https://www.ballymoneyparish.com/media/other/31871/26-08-23pdf.pdf"
        )
        target = date(2026, 8, 23)
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 23))
        self.assertEqual(check_bulletin_freshness(url, target).status, "fresh")
        old = (
            "https://www.ballymoneyparish.com/media/other/31871/26-08-16pdf.pdf"
        )
        self.assertEqual(extract_bulletin_date(old), date(2026, 8, 16))
        self.assertEqual(check_bulletin_freshness(old, target).status, "stale")
        self.assertNotEqual(
            check_bulletin_freshness(old, target).reason, "within_grace_days"
        )

    def test_yearless_slug_does_not_override_full_year_filename(self) -> None:
        url = (
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/07/"
            "Newsletter-12th-July-2026.pdf"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 7, 12))
        verdict = check_bulletin_freshness(url, date(2026, 8, 16))
        self.assertEqual(verdict.status, "stale")

    def test_stteresas_post_url_is_9_aug_not_unknown(self) -> None:
        post = (
            "https://stteresasparish.church/2026/08/06/"
            "the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/"
        )
        image = (
            "https://stteresasparish.church/wp-content/uploads/2026/08/"
            "microsoft-word-9-august-2026.docx.jpg"
        )
        target = date(2026, 8, 16)
        self.assertEqual(extract_bulletin_date(post), date(2026, 8, 9))
        self.assertEqual(extract_bulletin_date(image), date(2026, 8, 9))
        self.assertEqual(check_bulletin_freshness(post, target).status, "stale")
        self.assertNotEqual(
            check_bulletin_freshness(post, target).reason, "within_grace_days"
        )
        self.assertEqual(
            check_bulletin_freshness(
                "https://stteresasparish.church/2026/07/30/"
                "the-st-teresas-parish-bulletin-for-sunday-2nd-august-2026/",
                target,
            ).status,
            "stale",
        )

    def test_maghera_wix_ddmmyy_b_filename_is_16_aug(self) -> None:
        current = (
            "https://static.wixstatic.com/media/"
            "596648_b0abf059f78b4dddbb521f0aeec0b508~mv2.jpg/v1/fill/"
            "w_423,h_600,al_c,q_80/160826B-0.jpg"
        )
        archived = (
            "https://static.wixstatic.com/media/"
            "596648_oldjuly~mv2.jpg/v1/fill/w_423,h_600/120726-0.jpg"
        )
        target = date(2026, 8, 16)
        self.assertEqual(extract_bulletin_date(current), date(2026, 8, 16))
        self.assertEqual(extract_bulletin_date(current.replace("-0.jpg", "-1.jpg")), date(2026, 8, 16))
        self.assertEqual(check_bulletin_freshness(current, target).status, "fresh")
        self.assertEqual(check_bulletin_freshness(current, target).reason, "in_bulletin_week")
        self.assertEqual(extract_bulletin_date(archived), date(2026, 7, 12))
        self.assertEqual(check_bulletin_freshness(archived, target).status, "stale")

    def test_ahead_grace_keeps_thursday_post_for_next_sunday(self) -> None:
        # Parishes post Thursday/Friday for next Sunday. +4 days stays fresh;
        # +9 days is past MAX_STALE_DAYS_FROM_TARGET and is stale.
        target = date(2026, 8, 16)
        ahead = "https://example.com/bulletin_200826.pdf"
        too_far = "https://example.com/bulletin_250826.pdf"
        self.assertEqual(extract_bulletin_date(ahead), date(2026, 8, 20))
        ahead_verdict = check_bulletin_freshness(ahead, target)
        self.assertEqual(ahead_verdict.status, "fresh")
        self.assertEqual(ahead_verdict.reason, "within_grace_days")
        too_far_verdict = check_bulletin_freshness(too_far, target)
        self.assertEqual(too_far_verdict.status, "stale")
        self.assertEqual(too_far_verdict.reason, "date_ahead_of_target")


class SafetyNetUnknownUrlHeadingTests(unittest.TestCase):
    """Safety net must run H1 heading check when the URL has no date."""

    DRIVE_URL = "https://drive.google.com/file/d/1jmslbrliw/view"
    TARGET = date(2026, 8, 23)

    def _heading_pdf(self, path: Path, *lines: str) -> None:
        c = canvas.Canvas(str(path))
        y = 700
        for line in lines:
            c.drawString(72, y, line)
            y -= 18
        c.save()

    def _ok_result(self, key: str, pdf: Path) -> FetchResult:
        return FetchResult(
            key=key,
            display_name=key,
            status="ok",
            url=self.DRIVE_URL,
            file_path=pdf,
            file_type="pdf",
        )

    def test_undated_drive_july_heading_is_rejected_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "raphoe.pdf"
            self._heading_pdf(
                pdf, "Sunday 19 July 2026 RAPHOE PARISH NEWSLETTER"
            )
            result = self._ok_result("drive-1jmslbrliw", pdf)
            queue_path = Path(tmp) / "retry_queue.json"
            payload = apply_freshness_safety_net(
                [result],
                self.TARGET,
                retry_queue_path=queue_path,
            )
            self.assertTrue(result.is_stale)
            self.assertEqual(result.status, "error")
            self.assertEqual(len(payload["rejected_from_mega"]), 1)
            self.assertEqual(
                payload["rejected_from_mega"][0]["extracted_date"],
                "2026-07-19",
            )

    def test_undated_drive_july_heading_on_adjacent_line_is_rejected_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "raphoe.pdf"
            self._heading_pdf(
                pdf,
                "WEBSITE parishofraphoe.ie EMAIL: raphoeparish@gmail.com",
                "Sunday 19 July 2026",
                "RAPHOE PARISH NEWSLETTER",
                "St. Eunan's Church, Raphoe",
                "Monday 20 July",
                "NATIONAL GRANDPARENTS PILGRIMAGE will take place at Knock Shrine "
                "on Sunday 26 July",
            )
            result = self._ok_result("drive-1jmslbrliw", pdf)
            queue_path = Path(tmp) / "retry_queue.json"
            payload = apply_freshness_safety_net(
                [result],
                self.TARGET,
                retry_queue_path=queue_path,
            )
            self.assertTrue(result.is_stale)
            self.assertEqual(result.status, "error")
            self.assertEqual(len(payload["rejected_from_mega"]), 1)
            self.assertEqual(
                payload["rejected_from_mega"][0]["extracted_date"],
                "2026-07-19",
            )

    def test_undated_drive_this_week_heading_stays_not_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "this-week.pdf"
            self._heading_pdf(
                pdf, "Sunday 23 August 2026 RAPHOE PARISH NEWSLETTER"
            )
            result = self._ok_result("drive-thisweek", pdf)
            payload = apply_freshness_safety_net(
                [result],
                self.TARGET,
                retry_queue_path=Path(tmp) / "retry_queue.json",
            )
            self.assertFalse(result.is_stale)
            self.assertEqual(result.status, "ok")
            self.assertEqual(payload["rejected_from_mega"], [])

    def test_memorial_only_heading_stays_unknown_not_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "memorial.pdf"
            self._heading_pdf(
                pdf,
                "In memory of Mary 12 July 2026",
                "© 2012-2026 Parish",
            )
            result = self._ok_result("drive-memorial", pdf)
            payload = apply_freshness_safety_net(
                [result],
                self.TARGET,
                retry_queue_path=Path(tmp) / "retry_queue.json",
            )
            self.assertFalse(result.is_stale)
            self.assertEqual(result.status, "ok")
            self.assertEqual(payload["rejected_from_mega"], [])

    def test_html_article_slug_last_sunday_is_stale(self) -> None:
        # Ardara printed last week's HTML into the 06/09 mega because
        # sun-30th-august-26 was unknown (2-digit year refused by yearless).
        url = (
            "https://ardara.ie/news/"
            "church-of-the-holy-family-newsletter-sun-30th-august-26/"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 30))
        verdict = check_bulletin_freshness(url, date(2026, 9, 6))
        self.assertEqual(verdict.status, "stale")
        self.assertEqual(verdict.extracted_date, date(2026, 8, 30))

    def test_weekend_range_double_underscore_slug_is_stale(self) -> None:
        # Inver sat_29th__-_sun_30th__august_2026 — single-separator slug
        # matcher missed the date and the last-week PDF stayed in the mega.
        url = (
            "https://www.inverparish.com/uploads/2/5/2/9/25295787/"
            "inver_parish_newsletter_-_sat_29th__-_sun_30th__august_2026.pdf"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 30))
        verdict = check_bulletin_freshness(url, date(2026, 9, 6))
        self.assertEqual(verdict.status, "stale")

    def test_plus_separated_yearless_september_is_fresh(self) -> None:
        url = (
            "https://static1.squarespace.com/static/abc/t/def/"
            "6th+September.pdf"
        )
        verdict = check_bulletin_freshness(url, date(2026, 9, 6))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 9, 6))

    def test_month_first_sunday_sept_yy_is_fresh(self) -> None:
        # Tawnawilly listing 06/09: Sunday-Sept-06-26.pdf (not Sunday-6th-Sept.pdf).
        url = "https://tawnawillyparish.ie/wp-content/uploads/Sunday-Sept-06-26.pdf"
        self.assertEqual(extract_bulletin_date(url), date(2026, 9, 6))
        verdict = check_bulletin_freshness(url, date(2026, 9, 6))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 9, 6))

    def test_uk_dotted_bulletin_prefers_dd_mm_yy_not_future_year(self) -> None:
        url = (
            "https://stbrigidsparishbelfast.org/assets/documents/"
            "Parish-Bulletin-30.08.26-FOR-PRINTING-SOC.pdf"
        )
        self.assertEqual(extract_bulletin_date(url), date(2026, 8, 30))
        verdict = check_bulletin_freshness(url, date(2026, 9, 6))
        self.assertEqual(verdict.status, "stale")
        self.assertEqual(verdict.extracted_date, date(2026, 8, 30))

    def test_ddmmyy_rewrite_moves_wordpress_month_folder(self) -> None:
        from harvester.utils import rewrite_date_url

        example = (
            "https://watersideparish.net/wp-content/uploads/2026/06/"
            "newsletter_280626oo.pdf"
        )
        self.assertEqual(
            rewrite_date_url(example, date(2026, 9, 6)),
            "https://watersideparish.net/wp-content/uploads/2026/09/"
            "newsletter_060926oo.pdf",
        )

    def test_ordinary_time_filename_rewrites_to_this_sunday(self) -> None:
        from harvester.utils import (
            predicted_dated_upload_urls,
            rewrite_ordinary_time_upload_url,
        )

        example = (
            "https://www.loughshoreparishes.org/app/uploads/2026/08/"
            "21st-Sunday-in-Ordinary-Time.pdf"
        )
        self.assertEqual(
            rewrite_ordinary_time_upload_url(example, date(2026, 9, 6)),
            "https://www.loughshoreparishes.org/app/uploads/2026/09/"
            "23rd-Sunday-in-Ordinary-Time.pdf",
        )
        urls = predicted_dated_upload_urls(example, date(2026, 9, 6), weeks_back=0)
        self.assertEqual(
            urls[0],
            "https://www.loughshoreparishes.org/app/uploads/2026/09/"
            "23rd-Sunday-in-Ordinary-Time.pdf",
        )


if __name__ == "__main__":
    unittest.main()
