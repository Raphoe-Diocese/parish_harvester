"""Leftover 08/11/2026 PDF pins: wordpress direct_download, not predicted_dated_pdf."""
from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from harvester.bulletin_freshness import check_bulletin_freshness


def _recipe(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class Leftover0811PinTests(unittest.TestCase):
    def _assert_wordpress_direct(self, recipe: dict, needle: str) -> None:
        self.assertIn(needle, recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe.get("skip"), True)
        self.assertEqual(recipe["steps"][0]["action"], "goto")
        self.assertIn(needle, recipe["steps"][0]["url"])
        self.assertEqual(recipe["steps"][1]["action"], "download")
        self.assertIn(needle, recipe["steps"][1]["url"])

    def test_mulhuddart_pins_ugd_8_november_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/dublin/mulhuddart.json")
        self._assert_wordpress_direct(
            recipe, "a0b31f_664f57d81a59457ca7a9501409534181.pdf"
        )
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://www.stlukesparishd15.com"
        )

    def test_stjohnsfallsroad_pins_8_november_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/down_and_connor/stjohnsfallsroad.json")
        self._assert_wordpress_direct(recipe, "Sunday-8th-Nov-2026-ws.pdf")
        self.assertIn("/2022/06/", recipe["start_url"])
        self.assertNotIn("index.php/bulletin", recipe["start_url"])
        self.assertNotIn("1st-Nov", recipe["start_url"])

    def test_gurranabraher_pins_32nd_nov_8_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/cork_and_ross/gurranabraher.json")
        self._assert_wordpress_direct(
            recipe, "Gurranabraher-32nd-Ordinary-Time-Nov-8th-2026-A.pdf"
        )
        self.assertNotIn("category/newsletters", recipe["start_url"])
        self.assertNotIn("All-Saints", recipe["start_url"])
        self.assertNotIn("Nov-1st", recipe["start_url"])

    def test_salthill_pins_parish_news_nov_8_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/galway/salthill.json")
        self._assert_wordpress_direct(recipe, "Parish-News-Nov-8th-2026-1.pdf")
        self.assertNotEqual(recipe["start_url"].rstrip("/"), "https://salthillparish.ie")
        self.assertNotIn("September-13th", recipe["start_url"])

    def test_claudy_pins_9_november_docx_not_listing(self) -> None:
        recipe = _recipe("parishes/recipes/derry/parishofclaudy.json")
        self._assert_wordpress_direct(recipe, "NEWSLETTER 9-11-26.docx")
        self.assertGreaterEqual(int(recipe["max_bulletin_pages"]), 8)
        self.assertTrue(recipe["steps"][1].get("use_captured_url"))
        self.assertNotIn("8-11-26", recipe["start_url"])
        self.assertNotIn("15-11-26", recipe["start_url"])
        self.assertNotIn("25-10-26", recipe["start_url"])
        self.assertNotIn("weekly-bulletin.html", recipe["start_url"])
        self.assertNotIn("financial statement", recipe["start_url"].lower())

    def test_stoliver_pins_8th_nov_pdf_not_15th(self) -> None:
        recipe = _recipe("parishes/recipes/down_and_connor/stoliverplunkettparish.json")
        self._assert_wordpress_direct(recipe, "Bulletin-8th-Nov-26.pdf")
        self.assertGreaterEqual(int(recipe["max_bulletin_pages"]), 8)
        self.assertNotIn("15th-November-2026", recipe["start_url"])
        self.assertNotIn("1st-Nov-26", recipe["start_url"])
        self.assertNotIn("25-Oct-26", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"),
            "https://stoliverplunkettparish.ie/bulletins",
        )

    def test_ardfinnan_print_to_pdf_is_wordpress_not_scrape(self) -> None:
        recipe = _recipe("parishes/recipes/waterford_and_lismore/ardfinnan.json")
        self.assertIn("newsletter-7th-8th-november-2026", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_html")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))
        self.assertNotIn("newsletter-14th-15th-november-2026", recipe["start_url"])

    def test_emly_pins_8th_november_docx_not_listing(self) -> None:
        recipe = _recipe("parishes/recipes/cashel_and_emly/emly.json")
        self._assert_wordpress_direct(
            recipe, "Emly-Parish-Bulletin-8th-November-2026.docx"
        )
        self.assertGreaterEqual(int(recipe["max_bulletin_pages"]), 8)
        self.assertNotIn("1st-November", recipe["start_url"])
        self.assertNotIn("Octaber", recipe["start_url"])
        self.assertNotIn("category/parish-bulletin", recipe["start_url"])

    def test_wexford_stacks_8_november_jpegs_not_15th(self) -> None:
        recipe = _recipe("parishes/recipes/ferns/wexford.json")
        self.assertIn("Sunday-November-8th-1-scaled.jpg", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "direct_download")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_images")
        fallbacks = recipe.get("fallback_document_urls") or []
        self.assertIn(
            "https://wexfordparish.com/wp-content/uploads/2026/11/Sunday-November-8th-2-scaled.jpg",
            fallbacks,
        )
        self.assertIn(
            "https://wexfordparish.com/wp-content/uploads/2026/11/Sunday-November-8th-3-scaled.jpg",
            fallbacks,
        )
        self.assertIn(
            "https://wexfordparish.com/wp-content/uploads/2026/11/Sunday-November-8th-4-scaled.jpg",
            fallbacks,
        )
        self.assertEqual(int(recipe["image_count"]), 4)
        self.assertNotIn("Sunday-November-15th", recipe["start_url"])
        self.assertNotIn("Sunday-November-15th", json.dumps(fallbacks))
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://wexfordparish.com"
        )

    def test_dkr_pins_8_november_pdf_not_predicted(self) -> None:
        recipe = _recipe("parishes/recipes/limerick/donaghmoreknockearoxboro.json")
        self._assert_wordpress_direct(recipe, "Newsletter-2026-11-08.pdf")
        self.assertIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("/2026/10/", recipe["start_url"])
        self.assertNotIn("2026-11-01", recipe["start_url"])
        self.assertNotIn("useful-links/newsletters", recipe["start_url"])

    def test_shanagolden_pins_7th_8th_nov_pdf_not_archive(self) -> None:
        recipe = _recipe(
            "parishes/recipes/limerick/shanagoldenrobertstownfoynes.json"
        )
        self._assert_wordpress_direct(recipe, "NL-7th-and-8th-Nov.-2026.pdf")
        self.assertNotIn("newsletter-archive", recipe["start_url"])
        self.assertNotIn("31st-Oct", recipe["start_url"])
        self.assertNotIn("1st-Nov", recipe["start_url"])

    def test_faughart_print_to_pdf_is_08_11_newsboard(self) -> None:
        recipe = _recipe("parishes/recipes/armagh/faughart.json")
        self.assertIn("newsboard-08-11-2026", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "html_text_bulletin")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_html")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))
        self.assertNotIn("/2026/10/30/1335/", recipe["start_url"])
        self.assertNotIn("01/11/2026", recipe["start_url"])
        self.assertNotIn("armagharchdiocese.org", recipe["start_url"])
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://www.faughartparish.ie"
        )

    def test_headford_pins_7th_8th_nov_churchtv_pdf(self) -> None:
        recipe = _recipe("parishes/recipes/tuam/headford.json")
        self._assert_wordpress_direct(recipe, "Newsletter-7th-8th-November-2026.pdf")
        self.assertIn("/2021/02/", recipe["start_url"])
        self.assertNotIn("14th-15th-November", recipe["start_url"])
        self.assertNotIn("31st-October", recipe["start_url"])
        self.assertNotIn("1st-November", recipe["start_url"])
        self.assertNotIn("September", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://headfordchurch.com"
        )

    def test_bekan_pins_8_november_png_not_listing(self) -> None:
        recipe = _recipe("parishes/recipes/tuam/bekan.json")
        self._assert_wordpress_direct(recipe, "bpn8nov26.png")
        self.assertFalse(recipe.get("skip"))
        self.assertNotIn("bekanparishnewsletter01nov26", recipe["start_url"])
        self.assertNotIn("bpn8nov26.jpg", recipe["start_url"])
        self.assertNotIn("1st-november", recipe["start_url"])
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "http://www.bekan-parish.ie"
        )
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://bekan-parish.ie"
        )

    def test_magherafelt_print_to_pdf_is_wordpress_not_diocese_card(self) -> None:
        recipe = _recipe("parishes/recipes/armagh/magherafelt.json")
        self.assertIn("bulletin-8th-of-november-2026", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertEqual(recipe["playbook_type"], "html_text_bulletin")
        self.assertTrue(recipe.get("http_first"))
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_html")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://www.magherafeltparish.org"
        )
        self.assertNotIn("armagharchdiocese.org", recipe["start_url"])
        self.assertNotIn("1st-of-november", recipe["start_url"])
        self.assertNotIn("15th-of-november", recipe["start_url"])

    def test_charleville_pins_8th_november_doc_not_15th_or_diocese_card(self) -> None:
        recipe = _recipe("parishes/recipes/cloyne/charleville.json")
        self._assert_wordpress_direct(
            recipe, "8th-November-2026-CHARLEVILLE-PARISH-NEWSLETTER.doc"
        )
        self.assertIn("wpdmdl=6240", recipe["start_url"])
        self.assertNotIn("wpdmdl=6241", recipe["start_url"])
        self.assertNotIn("15th-november", recipe["start_url"])
        self.assertNotIn("1st-november", recipe["start_url"])
        self.assertNotIn("newsletters-2026", recipe["start_url"])
        self.assertNotIn("cloynediocese.ie", recipe["start_url"])
        verdict = check_bulletin_freshness(
            recipe["start_url"], date(2026, 11, 8)
        )
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 11, 8))

    def test_dungannon_print_to_pdf_is_this_week_post_not_diocese_card(self) -> None:
        recipe = _recipe("parishes/recipes/armagh/dungannon.json")
        self.assertIn("a_id=903", recipe["start_url"])
        self.assertEqual(recipe["site_type"], "wordpress")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_html")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe["steps"][-1]["action"], "print_to_pdf")
        self.assertTrue(recipe["steps"][-1].get("skip_listing_nav"))
        self.assertNotIn("armagharchdiocese.org", recipe["start_url"])
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "http://parishofdungannon.com"
        )
        self.assertNotIn("imagews?id=1443", recipe["start_url"])

    def test_mourneabbey_aliases_mallow_8_nov_pdf_not_diocese_card(self) -> None:
        recipe = _recipe("parishes/recipes/cloyne/mourneabbey.json")
        mallow = _recipe("parishes/recipes/cloyne/mallow.json")
        self.assertTrue(recipe.get("skip"))
        self.assertEqual(recipe.get("alias_of"), "mallow")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertIn("mallowparish.ie", recipe["start_url"])
        self.assertNotIn("cloynediocese.ie", recipe["start_url"])
        self.assertIn("Sunday-8th-November-2026.pdf", recipe.get("example_url") or "")
        self.assertFalse(mallow.get("skip"))
        self.assertNotEqual(mallow["site_type"], "predicted_dated_pdf")
        self.assertEqual(mallow["playbook_type"], "direct_download")
        verdict = check_bulletin_freshness(
            "https://mallowparish.ie/wp-content/uploads/2026/11/Sunday-8th-November-2026.pdf",
            date(2026, 11, 8),
        )
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 11, 8))
        self.assertNotIn("Sunday-1st-November", recipe.get("example_url") or "")
        self.assertNotIn("Sunday-15th-November", recipe.get("example_url") or "")

    def test_dromoreparish_pins_8_nov_archive_id_not_latest(self) -> None:
        recipe = _recipe("parishes/recipes/dromore/dromoreparish.json")
        self._assert_wordpress_direct(recipe, "id=1277")
        self.assertIn("get_pdf.php", recipe["start_url"])
        self.assertIn("do=archive", recipe["start_url"])
        self.assertTrue(recipe["start_url"].startswith("http://"))
        self.assertFalse(recipe.get("skip"))
        self.assertNotIn("do=latest", recipe["start_url"])
        self.assertNotIn("id=1275", recipe["start_url"])
        self.assertNotIn("dromorediocese.org", recipe["start_url"])
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "http://www.stcolmans.org"
        )

    def test_crossmaglen_pins_8th_nov_pdf_not_15th(self) -> None:
        recipe = _recipe("parishes/recipes/armagh/crossmaglen.json")
        self._assert_wordpress_direct(recipe, "8th%20NOV%202026.pdf")
        self.assertFalse(recipe.get("skip"))
        self.assertNotIn("15th", recipe["start_url"])
        self.assertNotIn("1st%20NOV", recipe["start_url"])
        self.assertNotIn("news.php", recipe["start_url"])
        self.assertNotIn("armagharchdiocese.org", recipe["start_url"])
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://www.uppercreggan.co.uk"
        )
        verdict = check_bulletin_freshness(recipe["start_url"], date(2026, 11, 8))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 11, 8))

    def test_dromahair_pins_08_11_churchtv_pdf_not_diocese_card(self) -> None:
        recipe = _recipe("parishes/recipes/kilmore/dromahair.json")
        self._assert_wordpress_direct(
            recipe, "Dromahair-Newsletter-08-11-2026.pdf"
        )
        self.assertIn("/2021/02/", recipe["start_url"])
        self.assertFalse(recipe.get("skip"))
        self.assertNotIn("01-11-2026", recipe["start_url"])
        self.assertNotIn("09-11-2026", recipe["start_url"])
        self.assertNotIn("16-11-2026", recipe["start_url"])
        self.assertNotIn("drumlease-killargue.com", recipe["start_url"])
        self.assertNotIn("kilmorediocese.ie", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        verdict = check_bulletin_freshness(
            recipe["start_url"], date(2026, 11, 8)
        )
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 11, 8))

    def test_dromara_pins_8_nov_nebula_not_15th(self) -> None:
        recipe = _recipe("parishes/recipes/dromore/dromara.json")
        self._assert_wordpress_direct(recipe, "345cac9267121d452bf093c40184c0ca")
        self.assertFalse(recipe.get("skip"))
        self.assertNotIn("366f88e3f30e7d6de57c562a15ce3910", recipe["start_url"])
        self.assertNotIn("9baacf34b2c04679a933099d5093fd93", recipe["start_url"])
        self.assertNotIn("6eed6dbb6454a17ae5ab6399b3d59c2d", recipe["start_url"])
        self.assertNotIn("bulletins-1.html", recipe["start_url"])
        self.assertNotIn("dromorediocese.org", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "http://www.dromaradgooland.org"
        )

    def test_drumgooland_aliases_dromara_same_08_11_file(self) -> None:
        recipe = _recipe("parishes/recipes/dromore/drumgooland.json")
        self.assertEqual(recipe["alias_of"], "dromara")
        self.assertTrue(recipe.get("skip"))
        self.assertEqual(recipe["site_type"], "link_only")
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotIn("345cac9267121d452bf093c40184c0ca", recipe["start_url"])
        self.assertNotIn("366f88e3f30e7d6de57c562a15ce3910", recipe["start_url"])
        self.assertNotIn("dromorediocese.org", recipe["start_url"])

    def test_togher_pins_8th_november_pdf_not_diocese_card(self) -> None:
        recipe = _recipe("parishes/recipes/armagh/togher.json")
        self._assert_wordpress_direct(
            recipe, "bulletin-32nd-ord-a-8th-november-2026.pdf"
        )
        self.assertFalse(recipe.get("skip"))
        self.assertEqual(recipe.get("status"), "active")
        self.assertIn("/2026/11/", recipe["start_url"])
        self.assertNotIn("1st-november", recipe["start_url"])
        self.assertNotIn("all-saints", recipe["start_url"])
        self.assertNotIn("parish-bulletins", recipe["start_url"])
        self.assertNotIn("familyofparishes.ie", recipe["start_url"])
        self.assertNotIn("armagharchdiocese.org", recipe["start_url"])
        self.assertNotEqual(recipe["site_type"], "predicted_dated_pdf")
        self.assertNotEqual(recipe["site_type"], "http_scrape_newest_pdf")
        self.assertNotEqual(recipe["site_type"], "link_only")
        self.assertNotEqual(
            recipe["start_url"].rstrip("/"), "https://togherparish.com"
        )
        verdict = check_bulletin_freshness(recipe["start_url"], date(2026, 11, 8))
        self.assertEqual(verdict.status, "fresh")
        self.assertEqual(verdict.extracted_date, date(2026, 11, 8))


if __name__ == "__main__":
    unittest.main()

