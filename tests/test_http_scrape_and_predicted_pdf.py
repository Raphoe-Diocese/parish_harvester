"""Helpers for HTTP-scrape newest PDF and predicted dated uploads."""
from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from harvester.replay import (
    _decode_pdfemb_data_url,
    _extract_matching_hrefs,
    _extract_pdfembed_target_url,
    _extract_post_page_images,
    _extract_wp_upload_images,
    _is_non_bulletin_url,
    _pick_newest_dated_post_url,
    _resolve_download_candidates,
    _score_http_scrape_pdf_hrefs,
    _score_wordpress_post_hrefs,
    _wordpress_feed_post_links,
    _wordpress_post_links_from_payload,
    _wordpress_posts_api_urls,
)
from harvester.utils import (
    churchmedia_channel_about_url,
    churchmedia_newsletter_url_from_about,
    churchmedia_slug_from_url,
    dropfiles_task_download_url,
    extract_mcn_church_id,
    looks_like_permanent_bulletin_url,
    mcn_newsletter_url_from_profile,
    mcn_profile_data_url,
    predicted_dated_upload_urls,
    predicted_wordpress_dated_post_urls,
    rewrite_date_url,
    wix_dated_slug_candidates,
    yearless_slug_date,
)


class YearlessSlugTests(unittest.TestCase):
    def test_sunday_nth_month_uses_assume_year(self) -> None:
        url = (
            "https://milfordrathmullanparishes.ie/wp-content/uploads/"
            "Parish-Newsletter-Sunday-9th-August.pdf"
        )
        self.assertEqual(
            yearless_slug_date(url, 2026, near=date(2026, 8, 16)),
            date(2026, 8, 9),
        )

    def test_december_before_new_year_rolls_back(self) -> None:
        url = "Parish-Newsletter-28th-December.pdf"
        self.assertEqual(
            yearless_slug_date(url, 2026, near=date(2026, 1, 4)),
            date(2025, 12, 28),
        )

    def test_full_year_slug_is_not_yearless(self) -> None:
        url = "Newsletter-12th-July-2026.pdf"
        self.assertIsNone(yearless_slug_date(url, 2026, near=date(2026, 8, 16)))

    def test_tawnawilly_aug_abbreviation_is_yearless(self) -> None:
        url = "https://tawnawillyparish.ie/wp-content/uploads/Sunday-23rd-Aug.pdf"
        self.assertEqual(
            yearless_slug_date(url, 2026, near=date(2026, 8, 16)),
            date(2026, 8, 23),
        )


class PredictedDatedUploadTests(unittest.TestCase):
    def test_newtown_pattern_rewrites_sunday_and_month_folder(self) -> None:
        example = (
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/07/"
            "Newsletter-12th-July-2026.pdf"
        )
        urls = predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=5)
        self.assertEqual(
            urls[0],
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/08/"
            "Newsletter-16th-August-2026.pdf",
        )
        self.assertIn(
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/08/"
            "Newsletter-16th-August-2026.docx",
            urls,
        )
        self.assertIn(
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/08/"
            "Newsletter-9th-August-2026.pdf",
            urls,
        )
        self.assertIn(example, urls)

    def test_holyfamily_parish_derry_ddmmyy_path(self) -> None:
        example = "https://www.holyfamily-parish.com/pdf/090826.pdf"
        urls = predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=2)
        self.assertEqual(urls[0], "https://www.holyfamily-parish.com/pdf/160826.pdf")
        self.assertIn("https://www.holyfamily-parish.com/pdf/090826.pdf", urls)
        self.assertTrue(
            all("holy-familyparish.com" not in u for u in urls),
            urls[:6],
        )

    def test_errigal_derry_ddmmyy_path(self) -> None:
        example = "https://www.errigalparish.com/pdf/160826.pdf"
        urls = predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=2)
        self.assertEqual(urls[0], "https://www.errigalparish.com/pdf/160826.pdf")
        self.assertIn("https://www.errigalparish.com/pdf/090826.pdf", urls)
        self.assertEqual(
            rewrite_date_url(example, date(2026, 8, 23)),
            "https://www.errigalparish.com/pdf/230826.pdf",
        )

    def test_yearless_sunday_june_rewrites_to_august(self) -> None:
        example = "https://tawnawillyparish.ie/wp-content/uploads/Sunday-28th-June.pdf"
        self.assertEqual(
            rewrite_date_url(example, date(2026, 8, 16)),
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-16th-August.pdf",
        )
        self.assertEqual(
            rewrite_date_url(
                "https://tawnawillyparish.ie/wp-content/uploads/Sunday-16th-Aug.pdf",
                date(2026, 8, 23),
            ),
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-23rd-Aug.pdf",
        )
        urls = predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=1)
        self.assertEqual(
            urls[0],
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-16th-August.pdf",
        )
        self.assertIn(
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-9th-August.pdf",
            urls,
        )

    def test_claudy_oneweb_space_variants_are_quoted(self) -> None:
        example = "http://parishofclaudy.com/onewebmedia/NEWSLETTER 21-6-26.docx"
        urls = predicted_dated_upload_urls(example, date(2026, 8, 9), weeks_back=0)
        self.assertTrue(
            any("NEWSLETTER%209-8-26.docx" in u for u in urls),
            urls[:8],
        )


class HttpScrapeScoreTests(unittest.TestCase):
    def test_picks_newest_parish_newsletter_and_skips_order_of_mass(self) -> None:
        hrefs = [
            "https://www.catholicbishops.ie/wp-content/uploads/2011/02/Order-of-Mass.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/Parish-Newsletter-5th-July.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/Parish-Newsletter-Sunday-2nd-August.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/Parish-Newsletter-Sunday-9th-August.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 9))
        self.assertIn("Sunday-9th-August", best_url)
        self.assertTrue(_is_non_bulletin_url(hrefs[0]))
        self.assertTrue(all("Order-of-Mass" not in url for _, url in scored))

    def test_friday_next_sunday_newsletter_is_accepted(self) -> None:
        # Friday 21/08/2026 harvest Sunday is 16/08. The listing only had
        # next Sunday's Parish-Newsletter. +3 days used to reject it.
        hrefs = [
            "https://www.catholicbishops.ie/wp-content/uploads/2011/02/Order-of-Mass.pdf",
            "https://milfordrathmullanparishes.ie/wp-content/uploads/"
            "Parish-Newsletter-Sunday-23rd-August.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        self.assertEqual(len(scored), 1)
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 23))
        self.assertIn("Sunday-23rd-August", best_url)
        self.assertTrue(all("Order-of-Mass" not in url for _, url in scored))

    def test_tawnawilly_yearless_aug_beats_july_2026_and_skips_gdpr(self) -> None:
        hrefs = [
            "https://tawnawillyparish.ie/wp-content/uploads/GDPR-Parish-Bulletin.pdf",
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-26-July-2026.pdf",
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-16th-Aug.pdf",
            "https://tawnawillyparish.ie/wp-content/uploads/Sunday-23rd-Aug.pdf",
            "https://tawnawillyparish.ie/wp-content/uploads/ChristMass-Newsletter-2025.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 23))
        self.assertIn("Sunday-23rd-Aug", best_url)
        self.assertTrue(_is_non_bulletin_url(hrefs[0]))
        self.assertTrue(all("GDPR" not in url for _, url in scored))

    def test_filename_date_beats_wordpress_upload_folder(self) -> None:
        # Malin uploaded March files into /2026/04/. Folder-first dating
        # would treat 29th-March as 29/04 and beat 5th-April.
        hrefs = [
            "http://malinparish.ie/wp-content/uploads/2026/04/Bulletin-29th-March-2026.pdf",
            "http://malinparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026.pdf",
            "http://malinparish.ie/wp-content/uploads/2022/02/Synod-2023.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 4, 5))
        self.assertIn("5th-April", best_url)

    def test_malin_dated_download_rewrites_to_missing_august_file(self) -> None:
        # This is why Malin must scrape the listing, not rewrite the download URL.
        example = (
            "http://malinparish.ie/wp-content/uploads/2026/04/"
            "Bulletin-5th-April-2026.pdf"
        )
        self.assertEqual(
            rewrite_date_url(example, date(2026, 8, 16)),
            "http://malinparish.ie/wp-content/uploads/2026/08/"
            "Bulletin-16th-August-2026.pdf",
        )

    def test_liturgical_and_glenavy_filenames_score_current_week(self) -> None:
        hrefs = [
            "https://www.holy-familyparish.com/app/uploads/2026/08/Nineteenth-Sunday-in-Ordinary-Time.pdf",
            "https://www.holy-familyparish.com/app/uploads/2026/08/Twentieth-Sunday-in-Ordinary-Time.pdf",
            "https://ballymenaparish.org/wp-content/uploads/2025/01/Wedding-Parish.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 16))
        self.assertIn("Twentieth-Sunday", best_url)
        self.assertTrue(all("Wedding-Parish" not in url for _, url in scored))

    def test_old_year_liturgical_file_does_not_beat_current(self) -> None:
        hrefs = [
            "https://glenariffeparish.org/wp-content/uploads/2024/08/Twentieth-Sunday-of-Ordinary-time.pdf",
            "https://glenariffeparish.org/wp-content/uploads/2026/07/Sixteenth-Sunday-of-Ordinary-Time.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 7, 19))
        self.assertIn("2026/07/Sixteenth", best_url)

    def test_glenavy_year_monthname_day_filename(self) -> None:
        hrefs = [
            "https://www.glenavyandkilleadparish.com/app/uploads/2026/04/2026-April-26-Fourth-Sunday-of-Easter.pdf",
            "https://www.glenavyandkilleadparish.com/app/uploads/2026/08/2026-August-16-Twentieth-Sunday-in-Ordinary-Time.pdf",
            "https://www.glenavyandkilleadparish.com/app/uploads/2026/08/2026-August-9-nineteenth-Sunday-in-Ordinary-Time.pdf",
        ]
        scored = _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16))
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 16))
        self.assertIn("August-16", best_url)


class WixDatedSlugCandidateTests(unittest.TestCase):
    def test_ballinascreen_includes_copy_of_variant(self) -> None:
        example = (
            "https://www.parishofballinascreen.com/"
            "ballinascreen-desertmartin-parishes-21_june_2026"
        )
        urls = wix_dated_slug_candidates(example, date(2026, 8, 16), weeks_back=1)
        self.assertEqual(
            urls[0],
            "https://www.parishofballinascreen.com/"
            "ballinascreen-desertmartin-parishes-16_august_2026",
        )
        self.assertEqual(
            urls[1],
            "https://www.parishofballinascreen.com/"
            "copy-of-ballinascreen-desertmartin-parishes-16_august_2026",
        )
        self.assertIn(
            "https://www.parishofballinascreen.com/"
            "ballinascreen-desertmartin-parishes-9_august_2026",
            urls,
        )

    def test_copy_of_example_does_not_double_prefix(self) -> None:
        example = (
            "https://www.parishofballinascreen.com/"
            "copy-of-ballinascreen-desertmartin-parishes-9_august_2026"
        )
        urls = wix_dated_slug_candidates(example, date(2026, 8, 16), weeks_back=0)
        copy_ofs = [u for u in urls if "/copy-of-copy-of-" in u]
        self.assertEqual(copy_ofs, [])
        self.assertIn(
            "https://www.parishofballinascreen.com/"
            "copy-of-ballinascreen-desertmartin-parishes-16_august_2026",
            urls,
        )


class DropfilesTaskUrlTests(unittest.TestCase):
    def test_banagher_sef_to_task_download(self) -> None:
        sef = (
            "https://www.banagherparish.com/files/9/Newsletters/395/"
            "Bulletin---13th-Sunday-in-Ordinary-Time---28th-June-2026"
        )
        self.assertEqual(
            dropfiles_task_download_url(sef),
            "https://www.banagherparish.com/index.php?option=com_dropfiles"
            "&task=frontfile.download&catid=9&id=395",
        )

    def test_non_dropfiles_url_returns_none(self) -> None:
        self.assertIsNone(
            dropfiles_task_download_url(
                "https://www.banagherparish.com/information"
            )
        )


class PermanentBulletinUrlTests(unittest.TestCase):
    def test_newtown_deep_path_is_permanent(self) -> None:
        url = "https://newtownkilleaparish.ie/bulletin/raphoe/newtown-killea/"
        self.assertTrue(looks_like_permanent_bulletin_url(url))
        self.assertEqual(rewrite_date_url(url, date(2026, 8, 16)), url)
        self.assertEqual(
            _resolve_download_candidates(url, target_date=date(2026, 8, 16)),
            [url],
        )

    def test_listing_bulletin_slash_is_not_permanent(self) -> None:
        self.assertFalse(
            looks_like_permanent_bulletin_url("https://newtownkilleaparish.ie/bulletin/")
        )

    def test_predicted_august_filename_is_not_used_for_permanent_path(self) -> None:
        guessed = predicted_dated_upload_urls(
            "https://newtownkilleaparish.ie/wp-content/uploads/2026/07/Newsletter-12th-July-2026.pdf",
            date(2026, 8, 16),
            weeks_back=0,
        )
        self.assertTrue(any("Newsletter-16th-August-2026.pdf" in u for u in guessed))
        self.assertFalse(
            looks_like_permanent_bulletin_url(guessed[0]),
        )


class McnNewsletterHelperTests(unittest.TestCase):
    def test_extracts_church_id_and_profile_url(self) -> None:
        html = '<input type="hidden" value="164" id="hfChurchId" />'
        self.assertEqual(extract_mcn_church_id(html), "164")
        self.assertEqual(
            mcn_profile_data_url(
                "https://mcn.live/Camera/our-lady-of-perpetual-succour-glenfinn",
                "164",
            ),
            "https://mcn.live/Website/ProfileDataByJson/164",
        )

    def test_reads_newsletter_url_from_profile_json(self) -> None:
        payload = {
            "newsletter": {
                "newsLetterTitle": "SUNDAY NEWSLETTER FOR SUNDAY AUGUST 16th 2026",
                "newsLetterUrl": (
                    "https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/"
                    "NewsLetter/fede99e0-206f-4ce5-9787-810dbbe0ceb4.pdf"
                ),
            }
        }
        self.assertTrue(
            str(mcn_newsletter_url_from_profile(payload)).endswith(".pdf")
        )
        self.assertIsNone(mcn_newsletter_url_from_profile({"newsletter": {}}))


class ChurchmediaNewsletterHelperTests(unittest.TestCase):
    LISTING = "https://churchmedia.tv/st-patricks-church-2"

    def test_slug_from_listing_not_newsletter_path(self) -> None:
        self.assertEqual(
            churchmedia_slug_from_url(self.LISTING),
            "st-patricks-church-2",
        )
        self.assertIsNone(
            churchmedia_slug_from_url(
                "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf?cb=1787226064"
            )
        )
        self.assertIsNone(
            churchmedia_slug_from_url(
                "https://churchmedia.tv/api/getChannelAbout?slug=st-patricks-church-2"
            )
        )

    def test_about_url_and_strips_cache_buster(self) -> None:
        self.assertEqual(
            churchmedia_channel_about_url("st-patricks-church-2"),
            "https://churchmedia.tv/api/getChannelAbout?slug=st-patricks-church-2",
        )
        payload = {
            "status": "Success",
            "data": {
                "newsletter_enable": 1,
                "newsletter_url": (
                    "https://churchmedia.tv/newsletter/"
                    "s22osz.st-patricks-church-2.pdf?cb=1787226064"
                ),
            },
        }
        out = churchmedia_newsletter_url_from_about(payload)
        self.assertEqual(
            out,
            "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf",
        )
        self.assertNotIn("cb=", out or "")
        self.assertIsNone(churchmedia_newsletter_url_from_about({"data": {}}))
        self.assertIsNone(
            churchmedia_newsletter_url_from_about(
                {"data": {"newsletter_url": "https://churchmedia.tv/st-patricks-church-2"}}
            )
        )

    def test_portaferry_recipe_does_not_pin_cache_token(self) -> None:
        recipe_path = (
            Path(__file__).resolve().parent.parent
            / "parishes"
            / "recipes"
            / "down_and_connor"
            / "portaferryparish.json"
        )
        raw = recipe_path.read_text(encoding="utf-8")
        recipe = json.loads(raw)
        self.assertEqual(recipe["site_type"], "churchmedia_newsletter")
        self.assertEqual(recipe["churchmedia_slug"], "st-patricks-church-2")
        self.assertEqual(recipe["start_url"], self.LISTING)
        self.assertNotIn("cb=", raw)
        self.assertNotIn("ovt7qm", raw)
        self.assertNotRegex(raw, r"/newsletter/[A-Za-z0-9]+\.st-patricks")
        click = recipe["steps"][0]
        self.assertEqual(click["text"], "View Our Latest Newsletter")
        self.assertIn("st-patricks-church-2.pdf", click["selector"])
        self.assertNotIn("cb=", click["selector"])


class StTeresasPredictedPostTests(unittest.TestCase):
    EXAMPLE = (
        "https://stteresasparish.church/2026/08/06/"
        "the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/"
    )
    SLUG = "the-st-teresas-parish-bulletin-for-sunday"

    def test_predicts_sunday_slug_and_nearby_post_dates(self) -> None:
        urls = predicted_wordpress_dated_post_urls(
            self.EXAMPLE, date(2026, 8, 16), weeks_back=1
        )
        self.assertEqual(
            urls[0],
            "https://stteresasparish.church/2026/08/13/"
            "the-st-teresas-parish-bulletin-for-sunday-16th-august-2026/",
        )
        self.assertIn(
            "https://stteresasparish.church/2026/08/14/"
            "the-st-teresas-parish-bulletin-for-sunday-16th-august-2026/",
            urls,
        )
        self.assertIn(
            "https://stteresasparish.church/2026/08/06/"
            "the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/",
            urls,
        )
        self.assertNotIn(
            "https://stteresasparish.church/2026/08/06/"
            "the-st-teresas-parish-bulletin-for-sunday-16th-august-2026/",
            urls,
        )

    def test_rewrite_date_url_keeps_stale_post_day(self) -> None:
        guessed = rewrite_date_url(self.EXAMPLE, date(2026, 8, 16))
        self.assertEqual(
            guessed,
            "https://stteresasparish.church/2026/08/06/"
            "the-st-teresas-parish-bulletin-for-sunday-16th-august-2026/",
        )

    def test_wp_json_picks_newest_sunday_and_skips_no_bulletin(self) -> None:
        payload = [
            {
                "slug": "please-note-there-will-be-no-st-teresas-parish-bulletin-on-sunday-14th-june-2026",
                "link": (
                    "https://stteresasparish.church/2026/06/11/"
                    "please-note-there-will-be-no-st-teresas-parish-bulletin-on-sunday-14th-june-2026/"
                ),
                "title": {"rendered": "Please note there will be no bulletin"},
            },
            {
                "slug": "the-st-teresas-parish-bulletin-for-sunday-9th-august-2026",
                "link": self.EXAMPLE,
                "title": {"rendered": "The St Teresa’s Parish Bulletin for Sunday, 9th August 2026"},
            },
            {
                "slug": "the-st-teresas-parish-bulletin-for-sunday-2nd-august-2026",
                "link": (
                    "https://stteresasparish.church/2026/07/30/"
                    "the-st-teresas-parish-bulletin-for-sunday-2nd-august-2026/"
                ),
                "title": {"rendered": "The St Teresa’s Parish Bulletin for Sunday, 2nd August 2026"},
            },
        ]
        links = _wordpress_post_links_from_payload(payload, [self.SLUG])
        self.assertEqual(links[0], self.EXAMPLE)
        self.assertTrue(all("please-note" not in link for link in links))
        self.assertEqual(
            _pick_newest_dated_post_url(links, date(2026, 8, 16)),
            self.EXAMPLE,
        )

    def test_wp_json_prefers_this_sunday_when_it_exists(self) -> None:
        live_16 = (
            "https://stteresasparish.church/2026/08/13/"
            "the-st-teresas-parish-bulletin-for-sunday-16th-august-2026/"
        )
        links = _wordpress_post_links_from_payload(
            [
                {
                    "slug": "the-st-teresas-parish-bulletin-for-sunday-16th-august-2026",
                    "link": live_16,
                },
                {
                    "slug": "the-st-teresas-parish-bulletin-for-sunday-9th-august-2026",
                    "link": self.EXAMPLE,
                },
            ],
            [self.SLUG],
        )
        self.assertEqual(_pick_newest_dated_post_url(links, date(2026, 8, 16)), live_16)

    def test_rss_and_public_api_urls(self) -> None:
        xml = """
        <rss><channel>
          <link>https://stteresasparish.church</link>
          <item>
            <title>The St Teresa’s Parish Bulletin for Sunday, 9th August 2026</title>
            <link>https://stteresasparish.church/2026/08/06/the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/</link>
          </item>
          <item>
            <title>Please note there will be no bulletin</title>
            <link>https://stteresasparish.church/2026/06/11/please-note-there-will-be-no-st-teresas-parish-bulletin-on-sunday-14th-june-2026/</link>
          </item>
        </channel></rss>
        """
        links = _wordpress_feed_post_links(xml, [self.SLUG])
        self.assertEqual(links, [self.EXAMPLE])
        apis = _wordpress_posts_api_urls("https://stteresasparish.church/")
        self.assertIn(
            "https://public-api.wordpress.com/wp/v2/sites/stteresasparish.church/posts?per_page=10&orderby=date&order=desc",
            apis,
        )

    def test_extracts_two_page_images_any_upload_month(self) -> None:
        html = """
        <img src="https://stteresasparish.church/wp-content/uploads/2023/01/st-teresas-logo-placeholder.png" />
        <img src="https://stteresasparish.church/wp-content/uploads/2026/07/microsoft-word-2-august-2026.docx.jpg" />
        <img src="https://stteresasparish.church/wp-content/uploads/2026/07/microsoft-word-2-august-2026.docx-2.jpg" />
        <img src="https://stteresasparish.church/wp-content/uploads/2026/07/microsoft-word-2-august-2026.docx-300x424.jpg" />
        """
        urls = _extract_post_page_images(html, self.EXAMPLE)
        self.assertEqual(
            urls,
            [
                "https://stteresasparish.church/wp-content/uploads/2026/07/microsoft-word-2-august-2026.docx.jpg",
                "https://stteresasparish.church/wp-content/uploads/2026/07/microsoft-word-2-august-2026.docx-2.jpg",
            ],
        )


class StGerardsListingImageTests(unittest.TestCase):
    """stgerardsparish.org — listing scrape then one full-page scan to PDF."""

    LISTING = "https://stgerardsparish.org/parish-news-events/"
    POST_16 = "https://stgerardsparish.org/sunday-bulletin-16th-august-2026/"
    POST_9 = "https://stgerardsparish.org/parish-bulletin-9th-august-2026/"
    PATTERNS = ["parish-bulletin-", "sunday-bulletin-", "bulletin"]

    def test_recipe_scrapes_news_listing_not_a_hardcoded_post(self) -> None:
        import json
        from pathlib import Path

        recipe = json.loads(
            Path("parishes/recipes/down_and_connor/stgerardsparish.json").read_text()
        )
        self.assertEqual(recipe["start_url"], self.LISTING)
        self.assertEqual(recipe["site_type"], "waf_retry_wordpress")
        self.assertNotIn("sunday-bulletin-16th-august-2026", json.dumps(recipe["steps"]))
        self.assertTrue(
            any("sunday-bulletin-" in p for p in recipe["post_slug_patterns"])
        )

    def test_listing_picks_newest_sunday_bulletin_not_older_parish_bulletin(self) -> None:
        html = f"""
        <a href="{self.POST_16}">Sunday Bulletin: 16th August 2026</a>
        <a href="{self.POST_9}">Parish Bulletin: 9th August 2026</a>
        <a href="https://stgerardsparish.org/sunday-bulletin-2nd-august-2026/">2nd August</a>
        <a href="https://stgerardsparish.org/sunday-message-16th-august-2026/">Sunday Message</a>
        """
        hrefs = _extract_matching_hrefs(html, self.LISTING, self.PATTERNS)
        self.assertIn(self.POST_16, hrefs)
        self.assertIn(self.POST_9, hrefs)
        self.assertTrue(all("sunday-message" not in href for href in hrefs))
        scored = _score_wordpress_post_hrefs(hrefs, date(2026, 8, 16))
        self.assertEqual(max(scored)[1], self.POST_16)
        self.assertEqual(max(scored)[0], date(2026, 8, 16))

    def test_extracts_full_size_scan_and_skips_wp_thumbnails(self) -> None:
        html = """
        <figure class="wp-block-image size-large">
          <img src="https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1-1024x724.png"
               srcset="https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1-300x212.png 300w,
                       https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1-768x543.png 768w,
                       https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1-1024x724.png 1024w,
                       https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1-1536x1086.png 1536w,
                       https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1.png 1588w" />
        </figure>
        """
        urls = _extract_wp_upload_images(html, 2026, 8, self.POST_16)
        self.assertEqual(
            urls,
            ["https://stgerardsparish.org/wp-content/uploads/2026/08/16th_1.png"],
        )


class PdfembedIframeTests(unittest.TestCase):
    PDF = (
        "https://www.stcolmcillesholywood.org/wp-content/uploads/2026/08/"
        "Bulletin-Notice-16th-August-2026.pdf"
    )

    def test_legacy_url_query_still_decoded(self) -> None:
        html = (
            '<iframe class="pdfembed-iframe" '
            'src="https://example.org/viewer/?url='
            "https%3A%2F%2Fexample.org%2Fwp-content%2Fuploads%2F2026%2F08%2Fbulletin.pdf"
            '&title=bulletin.pdf"></iframe>'
        )
        self.assertEqual(
            _extract_pdfembed_target_url(html),
            "https://example.org/wp-content/uploads/2026/08/bulletin.pdf",
        )

    def test_premium_pdfemb_data_base64_json(self) -> None:
        import base64
        import json

        raw = base64.b64encode(
            json.dumps({"url": self.PDF, "title": "Bulletin-Notice-16th-August-2026.pdf"}).encode()
        ).decode()
        html = (
            f'<iframe class="pdfembed-iframe nonfullscreen wppdf-emb-iframe-1"\n'
            f'\tsrc="https://www.stcolmcillesholywood.org/?pdfemb-data={raw}"\n'
            f'\tscrolling="yes"></iframe>'
        )
        self.assertEqual(_extract_pdfembed_target_url(html), self.PDF)
        self.assertEqual(_decode_pdfemb_data_url(raw), self.PDF)


class HolywoodNoticePageTests(unittest.TestCase):
    """stcolmcillesholywood.org — predict dated notice page, then iframe PDF."""

    LISTING = "https://www.stcolmcillesholywood.org/weekly-bulletins/"
    POST_16 = (
        "https://www.stcolmcillesholywood.org/bulletins/"
        "bulletin-notice-sunday-16th-august-2026/"
    )
    POST_9 = (
        "https://www.stcolmcillesholywood.org/bulletins/"
        "bulletin-notice-sunday-9th-august-2026/"
    )
    POST_23 = (
        "https://www.stcolmcillesholywood.org/bulletins/"
        "bulletin-notice-sunday-23rd-august-2026/"
    )
    PATTERNS = ["bulletin-notice-sunday-", "bulletin-notice-"]

    def test_recipe_predicts_notice_pages_not_a_pinned_pdf(self) -> None:
        import json
        from pathlib import Path

        recipe = json.loads(
            Path("parishes/recipes/down_and_connor/stcolmcillesholywood.json").read_text()
        )
        self.assertEqual(recipe["parish_key"], "stcolmcillesholywood")
        self.assertEqual(recipe["start_url"], self.LISTING)
        self.assertEqual(recipe["site_type"], "waf_retry_wordpress")
        self.assertEqual(recipe["example_post_url"], self.POST_16)
        self.assertTrue(
            any("bulletin-notice-sunday-" in p for p in recipe["post_slug_patterns"])
        )
        self.assertNotIn("Bulletin-Notice-16th-August-2026.pdf", json.dumps(recipe["steps"]))
        self.assertNotIn(
            "bulletin-notice-sunday-23rd-august-2026",
            recipe.get("example_post_url", ""),
        )

    def test_rewrite_skips_unposted_next_sunday(self) -> None:
        self.assertEqual(rewrite_date_url(self.POST_16, date(2026, 8, 23)), self.POST_23)
        self.assertEqual(rewrite_date_url(self.POST_16, date(2026, 8, 9)), self.POST_9)
        urls = predicted_dated_upload_urls(self.POST_16, date(2026, 8, 16), weeks_back=2)
        self.assertEqual(urls[0], self.POST_16)
        self.assertIn(self.POST_9, urls)
        self.assertNotIn(self.POST_23, urls)

    def test_listing_picks_newest_notice_not_older_week(self) -> None:
        html = f"""
        <a href="{self.POST_16}">Bulletin Notice Sunday 16th August 2026</a>
        <a href="{self.POST_9}">Bulletin Notice Sunday 9th August 2026</a>
        <a href="https://www.stcolmcillesholywood.org/news-and-events/prayers-for-marriage-and-family-life-august-2026/">Prayers</a>
        """
        hrefs = _extract_matching_hrefs(html, self.LISTING, self.PATTERNS)
        self.assertIn(self.POST_16, hrefs)
        self.assertIn(self.POST_9, hrefs)
        self.assertTrue(all("prayers-for-marriage" not in href for href in hrefs))
        scored = _score_wordpress_post_hrefs(hrefs, date(2026, 8, 16))
        self.assertEqual(max(scored)[1], self.POST_16)
        self.assertEqual(max(scored)[0], date(2026, 8, 16))


class ErrigalAndMalinRecipeTests(unittest.TestCase):
    def test_errigal_allows_eight_page_weekly(self) -> None:
        data = json.loads(
            Path("parishes/recipes/unknown/errigalparish.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["site_type"], "predicted_dated_pdf")
        self.assertGreaterEqual(int(data["max_bulletin_pages"]), 8)

    def test_malin_scrapes_listing_instead_of_rewriting_date(self) -> None:
        data = json.loads(
            Path("parishes/recipes/derry/malinparish.json").read_text(encoding="utf-8")
        )
        self.assertEqual(data["site_type"], "http_scrape_newest_pdf")
        self.assertIn("bulletin-", data.get("href_patterns") or [])
        steps = data.get("steps") or []
        self.assertFalse(
            any(
                str(step.get("url") or "").lower().endswith(".pdf")
                for step in steps
                if isinstance(step, dict)
            ),
            "dated PDF download URL would be rewritten to a missing August file",
        )


class BallymenaRecipeTests(unittest.TestCase):
    THIS_WEEK = (
        "https://ballymenaparish.org/wp-content/uploads/2026/08/"
        "23.8.26-A4-21st-Sunday.pdf"
    )
    LAST_WEEK = (
        "https://ballymenaparish.org/wp-content/uploads/2026/08/"
        "16.8.26-20th-Sunday.pdf"
    )
    WEDDING = (
        "https://ballymenaparish.org/wp-content/uploads/2025/01/Wedding-Parish.pdf"
    )

    def test_recipe_uses_wp_json_not_wedding_download(self) -> None:
        data = json.loads(
            Path("parishes/recipes/down_and_connor/ballymenaparish.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["site_type"], "wp_json_newest_media")
        self.assertIn("sunday", data.get("href_patterns") or [])
        steps = data.get("steps") or []
        self.assertFalse(
            any(
                "wedding-parish" in str(step.get("url") or "").lower()
                or str(step.get("url") or "").lower().endswith(".pdf")
                for step in steps
                if isinstance(step, dict)
            ),
            "pinned Wedding-Parish.pdf / dated download would miss this week's Sunday file",
        )

    def test_dot_date_sunday_beats_wedding(self) -> None:
        scored = _score_http_scrape_pdf_hrefs(
            [self.THIS_WEEK, self.LAST_WEEK, self.WEDDING],
            date(2026, 8, 16),
        )
        best_date, best_url = max(scored)
        self.assertEqual(best_date, date(2026, 8, 23))
        self.assertEqual(best_url, self.THIS_WEEK)
        self.assertTrue(all("Wedding-Parish" not in url for _, url in scored))
        self.assertTrue(_is_non_bulletin_url(self.WEDDING))


if __name__ == "__main__":
    unittest.main()
