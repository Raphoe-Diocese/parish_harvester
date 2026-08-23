from __future__ import annotations

import unittest

from ocr.bulletin_layout import (
    _is_url_only_line,
    classify_heading_line,
    render_parish_masthead,
    split_heading_prefix,
    structure_ocr_html,
)
from ocr.generate_bulletin_pages import prepare_ocr_fragment


class BulletinLayoutTests(unittest.TestCase):
    def test_promotes_mass_times_and_anniversaries_without_inventing(self) -> None:
        self.assertEqual(classify_heading_line("MASS TIMES"), "MASS TIMES")
        self.assertEqual(
            classify_heading_line("MASS TIMES ANNIVERSARIES /INTENTIONS"),
            "MASS TIMES ANNIVERSARIES /INTENTIONS",
        )
        self.assertEqual(classify_heading_line("Recently Deceased"), "Recently Deceased")
        self.assertEqual(classify_heading_line("Useful numbers"), "Useful numbers")
        self.assertEqual(classify_heading_line("Amanna Aifrinn"), "Amanna Aifrinn")
        self.assertIsNone(classify_heading_line("Vigil Mass on Saturday at 6.30pm"))
        self.assertIsNone(classify_heading_line("Please keep Fr Morty in your prayers."))

    def test_splits_heading_from_following_schedule(self) -> None:
        head, rest = split_heading_prefix("Mass times Saturday 15th August 10:00am")
        self.assertEqual(head.lower(), "mass times")
        self.assertIn("Saturday", rest)

    def test_keeps_irish_prayer_intact(self) -> None:
        html_out = structure_ocr_html(
            "<p>Ar dheis Dé go raibh a anam dílis.</p>",
            single_parish_name="Gaoth Dobhair",
            bulletin_date="2026-08-16",
        )
        self.assertIn("Ar dheis Dé go raibh a anam dílis.", html_out)
        self.assertIn("Gaoth Dobhair", html_out)
        self.assertIn("16/08/2026", html_out)

    def test_does_not_promote_contact_phone_or_bingo_sentence(self) -> None:
        self.assertIsNone(classify_heading_line("Contact 085 8285228 or email kilmacshed@gmail.com"))
        self.assertIsNone(classify_heading_line("Bingo every Tuesday night in the Market Hall."))
        self.assertIsNone(classify_heading_line("Parish Office : 028 9066 5409"))
        self.assertIsNone(classify_heading_line("Anniversary Masses will be offered"))
        self.assertIsNone(classify_heading_line("Parochial House, Falcarragh, Co. Donegal. F92 N6Y9."))

    def test_skips_trailing_directory_of_parish_urls(self) -> None:
        fragment = (
            "<p>Ballycastle</p><p>https://www.ballycastleparish.com</p>"
            "<p>Mass times Saturday 6.30pm</p>"
            "<p>Lisburn</p><p>https://parishoflisburn.org</p>"
            "<p>Portstewart</p><p>https://portstewartparish.website</p>"
        )
        html_out = structure_ocr_html(
            fragment,
            parish_entries=[
                ("ballycastleparish", "Ballycastle"),
                ("parishoflisburn", "Lisburn"),
                ("portstewartparish", "Portstewart"),
            ],
            bulletin_date="2026-08-16",
        )
        self.assertEqual(html_out.count("ocr-parish-masthead"), 1)
        self.assertIn("Ballycastle", html_out)
        self.assertNotIn('ocr-parish-name">Lisburn', html_out)

    def test_does_not_invent_missing_fundraising_section(self) -> None:
        html_out = structure_ocr_html("<p>Sunday Mass at 11am.</p><p>Parish office closed Friday.</p>")
        self.assertNotIn("Fundraising", html_out)
        self.assertNotIn("Bingo", html_out)

    def test_inserts_parish_masthead_from_stitcher_banner(self) -> None:
        fragment = (
            "<p>Annagry\n"
            '<a href="https://annagryparish.ie/newsletter-2/">'
            "https://annagryparish.ie/newsletter-2/</a></p>\n"
            "<p>MASS TIMES ANNIVERSARIES /INTENTIONS<br>\n"
            "Saturday 15th August 10:00am</p>"
        )
        html_out = structure_ocr_html(
            fragment,
            parish_entries=[("annagryparish", "Annagry")],
            bulletin_date="2026-08-16",
        )
        self.assertIn('class="ocr-parish-masthead"', html_out)
        self.assertIn('class="ocr-parish-name"', html_out)
        self.assertIn("Annagry", html_out)
        self.assertIn("16/08/2026", html_out)
        self.assertIn('<h3 class="b-head">', html_out)
        self.assertIn("MASS TIMES", html_out)
        self.assertNotIn("<details", html_out)
        self.assertLess(html_out.index("ocr-parish-masthead"), html_out.index("MASS TIMES"))

    def test_masthead_is_idempotent(self) -> None:
        first = structure_ocr_html(
            "<p>Ardara Parish</p><p>Mass times Saturday 6pm</p>",
            parish_entries=[("ardara", "Ardara Parish")],
            bulletin_date="2026-08-16",
        )
        second = structure_ocr_html(
            first,
            parish_entries=[("ardara", "Ardara Parish")],
            bulletin_date="2026-08-16",
        )
        self.assertEqual(first.count("ocr-parish-masthead"), 1)
        self.assertEqual(second.count("ocr-parish-masthead"), 1)

    def test_render_parish_masthead_escapes_and_dates(self) -> None:
        html_out = render_parish_masthead("St Mary's <Parish>", "2026-08-16")
        self.assertIn("St Mary", html_out)
        self.assertIn("&lt;Parish&gt;", html_out)
        self.assertIn("16/08/2026", html_out)
        self.assertIn('target="_blank"', render_parish_masthead("X", website="https://x.ie"))

    def test_convert_bulletin_promotes_plain_topic_lines(self) -> None:
        from ocr.convert_bulletin import render_markdown_lines

        parts = render_markdown_lines(
            [
                "MASS TIMES",
                "Saturday 6pm",
                "Recently Deceased",
                "Mary Murphy",
            ]
        )
        joined = "\n".join(parts)
        self.assertIn('<h3 class="b-head">MASS TIMES</h3>', joined)
        self.assertIn('<h3 class="b-head">Recently Deceased</h3>', joined)
        self.assertIn("Saturday 6pm", joined)
        self.assertIn("Mary Murphy", joined)

    def test_prepare_ocr_fragment_adds_masthead_without_accordion(self) -> None:
        parish_links = [
            ("Ardara Parish", "https://example.com/ardara"),
            ("Bangor Parish", "https://example.com/bangor"),
        ]
        ocr_fragment = (
            '<p class="page-label">Page 1</p>'
            "<h2>Ardara Parish</h2>"
            "<p>Mass times this week: Saturday 6pm, Sunday 11am.</p>"
            "<h2>Bangor Parish</h2>"
            "<p>Confessions after Saturday evening Mass.</p>"
        )
        result = prepare_ocr_fragment("test", ocr_fragment, parish_links, bulletin_date="2026-08-16")
        self.assertNotIn("<details", result)
        self.assertIn("ocr-parish-masthead", result)
        self.assertIn("Ardara Parish", result)
        self.assertIn("Mass times this week", result)
        self.assertLess(result.index("Mass times this week"), result.index("Confessions"))

    def test_preserves_page_label_class(self) -> None:
        html_out = structure_ocr_html(
            "<p>Page 14</p><p>Aifrinn na seachtaine</p><p>16ú Lúnasa 2026</p>",
            single_parish_name="Gortahork",
            bulletin_date="2026-08-21",
        )
        self.assertIn('class="page-label"', html_out)
        self.assertIn("Page 14", html_out)
        self.assertIn("Aifrinn na seachtaine", html_out)

    def test_promotes_irish_section_headings(self) -> None:
        self.assertEqual(classify_heading_line("AIFRINN NA SEACHTAINE"), "AIFRINN NA SEACHTAINE")
        self.assertEqual(classify_heading_line("BÁS LE GAIRID"), "BÁS LE GAIRID")
        self.assertEqual(classify_heading_line("AN CHÉAD LÉACHT"), "AN CHÉAD LÉACHT")

    def test_keeps_notice_when_parish_name_glued_on_the_end(self) -> None:
        fragment = (
            "<p>Please do not park in the Church Car Park Ballycastle</p>"
            "<p>https://www.ballycastleparish.com</p>"
            "<p>Mass times Saturday 6.30pm</p>"
        )
        html_out = structure_ocr_html(
            fragment,
            parish_entries=[("ballycastleparish", "Ballycastle")],
            bulletin_date="2026-08-23",
        )
        self.assertIn("Church Car Park", html_out)
        self.assertIn("Ballycastle", html_out)
        self.assertIn("ocr-parish-masthead", html_out)

    def test_keeps_wrapped_recently_and_music_lines(self) -> None:
        fragment = (
            "<p>Ballycastle</p>"
            "<p>https://www.ballycastleparish.com</p>"
            "<p>The choir sang beautifully</p>"
            "<p>recently.</p>"
            "<p>and there will be live</p>"
            "<p>music.</p>"
        )
        html_out = structure_ocr_html(
            fragment,
            parish_entries=[("ballycastleparish", "Ballycastle")],
            bulletin_date="2026-08-23",
        )
        self.assertIn("recently.", html_out)
        self.assertIn("music.", html_out)

    def test_is_url_only_line_requires_real_host(self) -> None:
        self.assertTrue(_is_url_only_line("https://www.ballycastleparish.com"))
        self.assertTrue(_is_url_only_line("parishoflisburn.org"))
        self.assertFalse(_is_url_only_line("recently."))
        self.assertFalse(_is_url_only_line("music."))
        self.assertFalse(_is_url_only_line("St."))


if __name__ == "__main__":
    unittest.main()
