"""The newsletter brain proposes a file, then the referee dates it."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from harvester.bulletin_freshness import check_bulletin_freshness
from harvester.newsletter_brain import (
    DIOCESE_ORDER,
    LEARNED,
    candidate_verdict,
    choose,
    filename_shapes,
    invent_candidates,
    neighbour_month_urls,
    next_diocese,
    pick_from_wp_json,
    proved_win,
    referee,
    remember,
    section_links,
    pick_same_day_file,
    same_sunday_urls,
    weekend_files,
)


TARGET = date(2026, 10, 11)


class RefereeTests(unittest.TestCase):
    def test_newer_link_beats_older_body(self) -> None:
        verdict = referee(
            "https://parish.ie/Sunday-11th-Oct-26.pdf",
            "Newsletter 4th October 2026",
            TARGET,
        )
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.reason, "link_date_beats_older_body")
        self.assertEqual(verdict.extracted_date, TARGET)

    def test_undated_url_with_old_heading_is_stale(self) -> None:
        verdict = referee(
            "https://parish.ie/newsletter",
            "Newsletter Sunday 5th July 2026",
            TARGET,
        )
        self.assertEqual(verdict.status, "stale")
        self.assertEqual(verdict.reason, "undated_url_stale_body")

    def test_undated_url_is_not_called_fresh(self) -> None:
        verdict = referee(
            "https://parish.ie/newsletter",
            "Newsletter Sunday 11th October 2026",
            TARGET,
        )
        self.assertEqual(verdict.status, "unknown")


class InventTests(unittest.TestCase):
    def test_page_pdf_is_chosen_and_facebook_is_ignored(self) -> None:
        html = """
        <a href="https://facebook.com/parish/posts/1">Facebook</a>
        <a href="/Sunday-11th-Oct-26.pdf">This Sunday</a>
        <a href="/bulletin/">Bulletin</a>
        """
        found = invent_candidates(html, "https://parish.ie/news", TARGET)
        urls = [item.url for item in found]
        self.assertIn("https://parish.ie/Sunday-11th-Oct-26.pdf", urls)
        self.assertFalse(any("facebook.com" in url for url in urls))
        picked = choose(found, TARGET)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertEqual(picked.url, "https://parish.ie/Sunday-11th-Oct-26.pdf")

    def test_liturgical_filename_is_invented_and_dated(self) -> None:
        shapes = filename_shapes(TARGET)
        liturgical = [name for name in shapes if "Sunday" in name or "Ordinary" in name]
        self.assertTrue(liturgical)
        html = f'<a href="/pdf/{liturgical[-1]}">Newsletter</a>'
        found = invent_candidates(html, "https://parish.ie/news.html", TARGET)
        picked = choose(found, TARGET)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertIn(liturgical[-1], picked.url)
        self.assertEqual(check_bulletin_freshness(picked.url, TARGET).status, "fresh")

    def test_guessed_ddmmyy_pdf_is_fresh(self) -> None:
        found = invent_candidates("", "https://parish.ie/news.html", TARGET)
        match = next(item for item in found if item.url.endswith("/pdf/111026.pdf"))
        self.assertEqual(match.kind, "invented")
        self.assertEqual(referee(match.url, "", TARGET).status, "fresh")

    def test_jetpack_url_stays_on_i0(self) -> None:
        html = (
            '<a href="https://i0.wp.com/parish.ie/wp-content/uploads/2026/10/'
            'Sunday-11th-Oct-26.jpg">scan</a>'
        )
        found = invent_candidates(html, "https://parish.ie/", TARGET)
        picked = choose(found, TARGET)
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.startswith("https://i0.wp.com/"))
        self.assertEqual(picked.strategy_id, "jetpack_image")

    def test_neighbour_month_moves_the_folder(self) -> None:
        moved = neighbour_month_urls(
            "https://parish.ie/wp-content/uploads/2026/09/newsletter.pdf"
        )
        urls = [item.url for item in moved]
        self.assertIn(
            "https://parish.ie/wp-content/uploads/2026/10/newsletter.pdf",
            urls,
        )
        self.assertIn(
            "https://parish.ie/wp-content/uploads/2026/08/newsletter.pdf",
            urls,
        )

    def test_wp_json_keeps_only_a_fresh_source(self) -> None:
        picked = pick_from_wp_json(
            [
                {"source_url": "https://parish.ie/gdpr.pdf", "title": "GDPR"},
                {
                    "source_url": "https://parish.ie/Sunday-11th-Oct-26.pdf",
                    "title": "Newsletter",
                },
            ],
            TARGET,
        )
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("Sunday-11th-Oct-26.pdf"))

    def test_drive_row_name_is_seen(self) -> None:
        html = "<div>26.10.11.pdf</div>"
        found = invent_candidates(html, "https://drive.google.com/drive/folders/abc", TARGET)
        self.assertTrue(any(item.strategy_id == "cloud_folder_newest" for item in found))

    def test_wix_hash_is_not_saved(self) -> None:
        html = '<a href="https://parish.ie/_files/ugd/abc123.pdf">11 Oct</a>'
        found = invent_candidates(html, "https://parish.ie/", TARGET)
        self.assertFalse(any("/_files/ugd/" in item.url for item in found))

    def test_diocese_profile_leads_to_the_parish_news_article(self) -> None:
        profile = "https://achonrydiocese.org/parishes/sligo/achonry-mullinabreena/"
        probes = invent_candidates("", profile, date(2026, 10, 18))
        urls = [item.url for item in probes]
        self.assertIn("https://www.achonrymullinabreena.com/NEWS.aspx", urls)
        self.assertFalse(any(item.url == profile for item in probes))
        html = (
            '<a href="ArticleDetail.aspx?articleid=1041">'
            "Parish Newsletter 18th October 2026</a>"
            '<a href="ArticleDetail.aspx?articleid=1040">'
            "Parish Newsletter 11th October 2026</a>"
        )
        found = invent_candidates(
            html, "https://www.achonrymullinabreena.com/NEWS.aspx", date(2026, 10, 18)
        )
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertIn("articleid=1041", picked.url)
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "fresh")

    def test_mayo_list_keeps_the_newest_pdf_and_dates_it(self) -> None:
        html = (
            '<a href="/getmedia/aaa/Charlestown-04-10-2026.pdf">'
            "Charlestown Parish Newsletter October 4th 2026</a>"
            '<a href="/getmedia/bbb/Charlestown-11-10-2026.pdf">'
            "Charlestown Parish Newsletter October 11th 2026</a>"
        )
        page = "https://www.mayo.ie/en-ie/parish-newsletters/charlestown-parish-newsletters"
        found = invent_candidates(html, page, date(2026, 10, 18))
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("Charlestown-11-10-2026.pdf"))
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "stale")
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 11)).status, "fresh")

    def test_edgeworthstown_picks_this_sunday_not_the_thought_file(self) -> None:
        html = """
        <a href="https://edgeworthstownparish.ie/wp-content/uploads/2026/10/sunday-newsletter-11-10-2026-edgeworthstown_compressed.pdf">old</a>
        <a href="https://edgeworthstownparish.ie/wp-content/uploads/2026/10/sunday-newsletter-18-10-2026-thought-for-the-week_compressed.pdf">thought</a>
        <a href="https://edgeworthstownparish.ie/wp-content/uploads/2026/10/sunday-newsletter-18-10-2026-edgeworthstown_compressed.pdf">this week</a>
        <a href="https://edgeworthstownparish.ie/wp-content/uploads/2024/07/Pastoral-Letter-July-2024-Page-1.pdf">pastoral</a>
        """
        page = "https://edgeworthstownparish.ie/community-notes-rathowen/parish-newsletter/"
        found = invent_candidates(html, page, date(2026, 10, 18))
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("sunday-newsletter-18-10-2026-edgeworthstown_compressed.pdf"))
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "fresh")
        files = weekend_files(found, date(2026, 10, 18))
        self.assertTrue(files)
        self.assertTrue(files[0].url.endswith("sunday-newsletter-18-10-2026-edgeworthstown_compressed.pdf"))
        self.assertFalse(any("thought-for-the-week" in item.url for item in files))
        same_day = [
            "https://edgeworthstownparish.ie/wp-content/uploads/2026/10/sunday-newsletter-18-10-2026-thought-for-the-week_compressed.pdf",
            "https://edgeworthstownparish.ie/wp-content/uploads/2026/10/sunday-newsletter-18-10-2026-edgeworthstown_compressed.pdf",
            "https://edgeworthstownparish.ie/wp-content/uploads/2026/10/sunday-newsletter-18-10-2026-rathowenstreete_compressed.pdf",
        ]
        kept = pick_same_day_file(
            same_day,
            ["edgeworthstown_compressed.pdf", "edgeworthstown"],
        )
        self.assertIsNotNone(kept)
        assert kept is not None
        self.assertTrue(
            kept.endswith("sunday-newsletter-18-10-2026-edgeworthstown_compressed.pdf")
        )

    def test_castleisland_keeps_this_sunday_not_next_sunday(self) -> None:
        scored = [
            (date(2026, 10, 4), "https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/4th-October2026-1.pdf"),
            (date(2026, 10, 18), "https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/18th-October2026.pdf"),
            (date(2026, 10, 25), "https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/25th-October2026.pdf"),
        ]
        kept = same_sunday_urls(scored, date(2026, 10, 18))
        self.assertEqual(
            kept,
            ["https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/18th-October2026.pdf"],
        )
        from harvester.replay import _is_non_bulletin_url

        self.assertFalse(_is_non_bulletin_url(kept[0]))
        self.assertTrue(
            _is_non_bulletin_url(
                "https://achonrydiocese.org/parishes/sligo/achonry-mullinabreena/"
            )
        )
        self.assertTrue(
            _is_non_bulletin_url("https://www.killaloediocese.ie/parish/birr/")
        )
        self.assertFalse(
            _is_non_bulletin_url(
                "https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/2026-11-01.pdf"
            )
        )

    def test_ahead_file_is_kept_when_this_sunday_is_missing(self) -> None:
        scored = [
            (date(2026, 10, 18), "https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/2026-10-18.pdf"),
            (date(2026, 11, 1), "https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/2026-11-01.pdf"),
        ]
        kept = same_sunday_urls(scored, date(2026, 10, 25))
        self.assertEqual(
            kept,
            ["https://www.dioceseofkerry.ie/wp-content/uploads/2026/10/2026-11-01.pdf"],
        )
        only_next = same_sunday_urls(
            [(date(2026, 11, 1), "https://www.arklowparish.ie/newsletter_1st_November_2026.pdf")],
            date(2026, 10, 25),
        )
        self.assertEqual(len(only_next), 1)
        both = same_sunday_urls(
            [
                (date(2026, 10, 25), "https://example.ie/25.pdf"),
                (date(2026, 11, 1), "https://example.ie/01.pdf"),
            ],
            date(2026, 10, 25),
        )
        self.assertEqual(both, ["https://example.ie/25.pdf"])

    def test_termonmaguirc_picks_twenty_ninth_sunday(self) -> None:
        html = """
        <a href="https://www.termonmaguircparish.com/wp-content/uploads/2026/10/Twenty-Eighth-Sunday-in-Ordinary-Time-11-Oct-2026-1.pdf">28</a>
        <a href="https://www.termonmaguircparish.com/wp-content/uploads/2026/10/Twenty-Ninth-Sunday-in-Ordinary-Time-18-Oct-2026.pdf">29</a>
        <a href="https://www.termonmaguircparish.com/wp-content/uploads/2026/09/Twenty-Sixth-Sunday-in-Ordinary-Time-27-Sept-2026.pdf">26</a>
        """
        found = invent_candidates(html, "https://www.termonmaguircparish.com/bulletins/", date(2026, 10, 18))
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("Twenty-Ninth-Sunday-in-Ordinary-Time-18-Oct-2026.pdf"))
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "fresh")

    def test_armagh_parish_newest_pdf_is_11_october(self) -> None:
        html = """
        <a href="https://armaghparish.net/wp-content/uploads/2026/10/11th-October.pdf">11</a>
        <a href="https://armaghparish.net/wp-content/uploads/2026/10/4th-October.pdf">4</a>
        <a href="https://armaghparish.net/wp-content/uploads/2026/09/18th-October.pdf">old name</a>
        """
        found = invent_candidates(html, "https://armaghparish.net/parish-bulletin/", date(2026, 10, 18))
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("/2026/10/11th-October.pdf"))
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "stale")

    def test_cullyhanna_post_is_kept_until_the_picture_is_on_the_page(self) -> None:
        home = """
        <a href="https://lowercregganparish.com/parish-bulletin-18th-october-2026/">18</a>
        <a href="https://lowercregganparish.com/parish-bulletin-11th-october-2026/">11</a>
        <img src="https://lowercregganparish.com/wp-content/uploads/sites/6/2026/10/Sunday-4th-October-2026-page-001-scaled.jpg">
        """
        found = invent_candidates(home, "https://lowercregganparish.com/", date(2026, 10, 18))
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("/parish-bulletin-18th-october-2026/"))
        article = """
        <a href="https://lowercregganparish.com/parish-bulletin-11th-october-2026/">11</a>
        <img src="https://lowercregganparish.com/wp-content/uploads/sites/6/2026/10/Sunday-18th-October-2026-page-001-724x1024.jpg">
        """
        found = invent_candidates(
            article,
            "https://lowercregganparish.com/parish-bulletin-18th-october-2026/",
            date(2026, 10, 18),
        )
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("Sunday-18th-October-2026-page-001-724x1024.jpg"))
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "fresh")

    def test_emly_listing_has_no_pdf_so_open_the_post_and_take_the_word_file(self) -> None:
        listing = """
        <a href="https://emly.ie/emly-parish-bulletin-18th-october-2026/">18</a>
        <a href="https://emly.ie/emly-parish-bulletin-11th-october-2026/">11</a>
        <img src="https://emly.ie/wp-content/uploads/2020/03/Bulletin-1-287x250.png">
        """
        found = invent_candidates(listing, "https://emly.ie/category/parish-bulletin/", date(2026, 10, 18))
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("/emly-parish-bulletin-18th-october-2026/"))
        article = """
        <iframe src="//view.officeapps.live.com/op/embed.aspx?src=https%3A%2F%2Femly.ie%2Fwp-content%2Fuploads%2F2026%2F10%2FEmly-Parish-Bulletin-18th-Octaber-2026-send.docx"></iframe>
        <a href="https://cashel-emly.ie/wp-content/uploads/2018/07/Autumn-2020-Safeguarding-Newsletter-.pdf">old</a>
        """
        found = invent_candidates(
            article,
            "https://emly.ie/emly-parish-bulletin-18th-october-2026/",
            date(2026, 10, 18),
        )
        picked = choose(found, date(2026, 10, 18))
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.url.endswith("Emly-Parish-Bulletin-18th-Octaber-2026-send.docx"))
        self.assertEqual(candidate_verdict(picked, date(2026, 10, 18)).status, "fresh")


class MemoryTests(unittest.TestCase):
    def test_unknown_and_failed_probes_are_not_wins(self) -> None:
        found = invent_candidates("", "https://parish.ie/news", TARGET)
        guess = found[0]
        self.assertIsNone(
            proved_win(
                guess,
                http_status=404,
                file_kind="pdf",
                verdict=referee(guess.url, "", TARGET),
                parish_key="example",
            )
        )
        unknown = referee("https://parish.ie/newsletter", "", TARGET)
        self.assertIsNone(
            proved_win(
                guess,
                http_status=200,
                file_kind="pdf",
                verdict=unknown,
                parish_key="example",
            )
        )

    def test_a_fresh_file_is_remembered_once(self, ) -> None:
        found = invent_candidates(
            '<a href="/Sunday-11th-Oct-26.pdf">Sunday</a>',
            "https://parish.ie/news",
            TARGET,
        )
        picked = choose(found, TARGET)
        assert picked is not None
        verdict = referee(picked.url, "", TARGET)
        win = proved_win(
            picked,
            http_status=200,
            file_kind="pdf",
            verdict=verdict,
            parish_key="exampleparish",
        )
        self.assertIsNotNone(win)
        assert win is not None
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "newsletter_brain.json"
            first = remember(win, path)
            second = remember(win, path)
            self.assertEqual(len(first["wins"]), 1)
            self.assertEqual(len(second["wins"]), 1)
            self.assertEqual(first["wins"][0]["verdict"], "fresh")

    def test_dioceses_run_a_to_z(self) -> None:
        self.assertEqual(DIOCESE_ORDER[0], "achonry")
        self.assertEqual(DIOCESE_ORDER[-1], "waterford_and_lismore")
        self.assertEqual(next_diocese([]), "achonry")
        self.assertEqual(next_diocese(["achonry"]), "ardagh")
        self.assertEqual(len(LEARNED), 30)
        drive = next(item for item in LEARNED if item["id"] == "cloud_folder_newest")
        self.assertIn("2027", drive["how"])
        self.assertIn("2028", drive["how"])
        self.assertIn("1jPOi4GRU22vAxeKNe5Y_doBJ3riPh7ZK", drive["how"])
        self.assertIn("26.10.25.pdf", drive["how"])
        self.assertNotIn("start_url", drive["how"])
        canva = next(
            item for item in LEARNED if item["id"] == "canva_site_bulletin_image"
        )
        self.assertIn("prefer=largest", canva["how"])
        self.assertIn("_assets/media", canva["how"])
        self.assertIn("blob:", canva["how"])

    def test_this_sunday_upload_names_are_guessed(self) -> None:
        sunday = date(2026, 10, 18)
        shapes = filename_shapes(sunday)
        self.assertIn(
            "Newsletter-18th-October-2026-29th-Sunday-in-Ordinary-Time.pdf",
            shapes,
        )
        self.assertIn("2026-10-18-Newsletter.pdf", shapes)
        self.assertIn("Sunday-October-18th-1-scaled.jpg", shapes)
        found = invent_candidates("", "https://cloyneparish.com/", sunday)
        from harvester.newsletter_brain import weekend_files

        ordered = [item.url for item in weekend_files(found, sunday)]
        self.assertIn("wp-content/uploads", ordered[0])
        self.assertTrue(
            any("Newsletter-18th-October-2026" in url for url in ordered[:4])
        )
        self.assertTrue(any(url.endswith("2026-10-18-Newsletter.pdf") for url in ordered[:4]))
        self.assertEqual(
            check_bulletin_freshness(
                "Sunday-October-18th-1-scaled.jpg", sunday
            ).extracted_date,
            sunday,
        )
        from harvester.utils import naomhfionan_bulletin_urls, sunday_month_day_image_urls

        falcarragh = naomhfionan_bulletin_urls(sunday)
        self.assertIn(
            "https://naomhfionan.com/wp-content/uploads/2026/10/"
            "Parish-Newsletter-42-Sun-A-18102026.pdf",
            falcarragh,
        )
        this_sunday = naomhfionan_bulletin_urls(date(2026, 10, 25))
        self.assertIn(
            "https://naomhfionan.com/wp-content/uploads/2026/10/"
            "Parish-Newsletter-43for-Sun-A-25102026.pdf",
            this_sunday,
        )
        pages = sunday_month_day_image_urls(
            "https://wexfordparish.com/wp-content/uploads/2026/10/"
            "Sunday-October-4th-1-scaled.jpg",
            sunday,
            count=4,
        )
        self.assertEqual(len(pages), 4)
        self.assertTrue(pages[0].endswith("Sunday-October-18th-1-scaled.jpg"))
        self.assertTrue(pages[3].endswith("Sunday-October-18th-4-scaled.jpg"))

    def test_crumlin_homepage_points_at_the_newsletter_page(self) -> None:
        html = (
            '<a href="https://www.crumlinparish.ie/newsletter/">Newsletter</a>'
            '<a href="https://www.facebook.com/crumlin">Facebook</a>'
        )
        links = section_links(html, "https://www.crumlinparish.ie/")
        self.assertEqual(links, ["https://www.crumlinparish.ie/newsletter/"])


if __name__ == "__main__":
    unittest.main()
