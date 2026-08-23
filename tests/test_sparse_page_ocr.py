from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from ocr.sparse_page_ocr import (
    column_gutter_xs,
    join_ocr_html_pages,
    ocr_lines_look_smashed,
    ocr_lines_look_usable,
    page_html_is_sparse,
    page_ocr_needs_image_repair,
    prefer_embedded_pages_in_ocr_html,
    render_pdf_page_image,
    repair_image_page_ocr,
    repair_image_pages_in_ocr_html,
    split_ocr_html_pages,
)

_ANNAGRY_SMASH = [
    "i gi Teach = 9 ? at i Réalt n; ii haite | We An thth Ma Sat 22™Aug 6.30pm",
    "21* Sunday Re of on § Ordinary @ F 4 Time Sun 23“Aug 9.00am F 11.00am",
    "mail: pp.annagry@gmail.com | Instagram: #annagry_parish Fri. 28\"Aug = 7.00pm",
    "Mass Bookings: Anyone wishing to | Holy Water is available fror",
    "Aifrinn, Loch an Iúir - Croic | Location: Eircode F94 XO4",
]

_CLEAN_COLUMN = [
    "Teach Pobail Mhuire Réalt na Mara Anagaire",
    "An tAth Nigel Ó Gallachóir SP",
    "Parish Office: 074-9548902",
    "Email: pp.annagry@gmail.com",
    "Aifrinn na Seachtaine Saturday 22nd August 6.30pm John Gillespie, Braade",
    "Sunday 23rd August 9.00am and 11.00am Missa Pro Populo",
    "Your Sunday gift to God and His Church last week was one thousand nine hundred euro.",
    "The Holy Rosary is prayed before Mass every Tuesday to Friday and Sunday at eleven.",
    "Safeguarding Children Diocese of Raphoe: contact Margaret Northage if you have a concern.",
]


class SparsePageOcrHtmlTests(unittest.TestCase):
    def test_split_and_join_plain_page_markers(self) -> None:
        fragment = (
            "<p>Page 14</p>\n"
            "<p>Gortahork</p>\n"
            "<hr>\n"
            "<p>Page 15</p>\n"
            "<p>Inver mass times.</p>"
        )
        pages = split_ocr_html_pages(fragment)
        self.assertEqual([num for num, _ in pages], [14, 15])
        self.assertTrue(page_html_is_sparse(pages[0][1]))
        self.assertFalse(page_html_is_sparse(pages[1][1] + " extra body " * 20))
        joined = join_ocr_html_pages(pages)
        self.assertIn('class="page-label"', joined)
        self.assertIn("Page 14", joined)
        self.assertIn("Page 15", joined)

    def test_irish_body_is_not_sparse(self) -> None:
        body = (
            "<p>AIFRINN NA SEACHTAINE<br>\n"
            "16ú Lúnasa 2026<br>\n"
            "An tAth. Donnchadh Ó Baoill, Pobal Chríost Rí, Gort a' Choirce<br>\n"
            "Nora O'Donnell, An Bhealtaine / An Chlochán Liath<br>\n"
            "Eamon Mc Ginley, Inis Bó Finne / An Fál Carrach<br>\n"
            "Tógadh €1,530 an tseachtain s'chuaigh thart. Buíochas don phobal.</p>"
        )
        self.assertFalse(page_html_is_sparse(body))
        self.assertFalse(
            page_html_is_sparse(
                "<p>Weekend Mass Times<br>\nSaturday Vigil Kilclooney 6.00pm Ardara 7.30pm</p>"
            )
        )
        irish = [
            "POBAL CHRÍOST RÍ GORT A’ CHOIRCE AIFRINN NA SEACHTAINE",
            "16ú Lúnasa 2026 An tAth. Donnchadh Ó Baoill paróiste",
            "Nora O'Donnell, An Bhealtaine agus Eamon Mc Ginley Inis Bó Finne",
            "Tógadh €1,530 an tseachtain s'chuaigh thart. Buíochas don phobal uile.",
            "Seo mar a deir an Tiarna: Coinnígí an ceart, cleachtaígí an fhíréanacht.",
        ]
        self.assertTrue(ocr_lines_look_usable(irish))
        self.assertFalse(ocr_lines_look_usable(["H", "q", "‘", ". aN wy ?", "at i Réalt n"]))

    def test_prefer_embedded_pages_restores_church_car_park(self) -> None:
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        y = 760
        for line in (
            "MASS TIMES and parish notices for this week.",
            "Vigil Mass on Saturday 22nd August at 6.30pm in St Patrick's.",
            "Please do not park in the Church Car Park during funerals this week.",
            "Recently deceased: please keep the family in your prayers this Sunday.",
            "Community notices continue below with weekday Masses and contacts.",
        ):
            c.drawString(72, y, line)
            y -= 16
        c.showPage()
        c.save()
        fragment = (
            '<p class="page-label">Page 1</p>\n'
            "<p>MASS TIMES</p>\n"
            "<p>Vigil Mass on Saturday 2nd August at 6.30pm in St Patrick's.</p>\n"
            "<p>Recently deceased: please keep the family in your prayers this Sunday.</p>"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "parish.pdf"
            pdf_path.write_bytes(buf.getvalue())
            out = prefer_embedded_pages_in_ocr_html(fragment, pdf_path)
        self.assertIn("Church Car Park", out)
        self.assertIn("22nd", out)
        self.assertNotIn("Saturday 2nd August", out)

    def test_annagry_vision_looks_smashed_irish_does_not(self) -> None:
        self.assertTrue(ocr_lines_look_smashed(_ANNAGRY_SMASH))
        self.assertTrue(page_ocr_needs_image_repair(_ANNAGRY_SMASH, ["Annagry", "https://x"]))
        irish = [
            "POBAL CHRÍOST RÍ GORT A’ CHOIRCE AIFRINN NA SEACHTAINE",
            "16ú Lúnasa 2026 An tAth. Donnchadh Ó Baoill paróiste",
            "Nora O'Donnell, An Bhealtaine agus Eamon Mc Ginley Inis Bó Finne",
            "Tógadh €1,530 an tseachtain s'chuaigh thart. Buíochas don phobal uile.",
            "Seo mar a deir an Tiarna: Coinnígí an ceart, cleachtaígí an fhíréanacht.",
        ]
        self.assertFalse(ocr_lines_look_smashed(irish))
        mass_list = [
            "m John Gillespie, Braade and Girvan Burial of ashes",
            "m Mary T. O'Donnell, Braade and Mullaghduff",
            "m Patrick and Annie Walsh, Loch an Iúir",
            "m Teresa Skillen, Annagry East, First Anniversary",
            "m Eddie Neddie Eoin Gallagher, Annagry East and Swords",
        ]
        self.assertFalse(ocr_lines_look_smashed(mass_list))
        self.assertFalse(
            page_ocr_needs_image_repair(
                _ANNAGRY_SMASH,
                irish + ["Weekend Mass Times Saturday Vigil Kilclooney 6.00pm extra body text"],
            )
        )

    def test_column_gutter_finds_sidebar_not_midpage(self) -> None:
        from PIL import Image, ImageDraw

        image = Image.new("L", (800, 1000), 255)
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 70, 230, 980), fill=30)
        draw.rectangle((290, 70, 780, 980), fill=30)
        gutters = column_gutter_xs(image)
        self.assertEqual(len(gutters), 1)
        self.assertGreater(gutters[0], 220)
        self.assertLess(gutters[0], 300)

        single = Image.new("L", (800, 1000), 255)
        ImageDraw.Draw(single).rectangle((40, 40, 760, 960), fill=30)
        self.assertEqual(column_gutter_xs(single), [])

    def test_annagry_pdf_has_sidebar_gutter(self) -> None:
        pdf = Path("docs/parishes/raphoe/annagryparish.pdf")
        if not pdf.is_file() or pdf.stat().st_size < 20000:
            self.skipTest("real Annagry parish PDF missing")
        image = render_pdf_page_image(pdf, 0, dpi=100)
        if image is None:
            self.skipTest("no PDF page renderer")
        gutters = column_gutter_xs(image)
        self.assertEqual(len(gutters), 1, gutters)
        self.assertGreater(gutters[0], image.size[0] * 0.22)
        self.assertLess(gutters[0], image.size[0] * 0.42)

    def test_repair_replaces_smashed_image_page(self) -> None:
        from unittest.mock import patch

        smashed_html = (
            '<p class="page-label">Page 1</p>\n'
            "<p>" + " ".join(_ANNAGRY_SMASH) + "</p>"
        )
        with patch(
            "ocr.sparse_page_ocr.ocr_pdf_page_lines",
            return_value=_CLEAN_COLUMN,
        ), patch(
            "ocr.sparse_page_ocr.extract_all_page_lines",
            return_value=[["Annagry", "https://annagryparish.ie/newsletter-2/"]],
        ):
            lines_out = repair_image_page_ocr("dummy.pdf", [_ANNAGRY_SMASH])
            html_out = repair_image_pages_in_ocr_html(smashed_html, "dummy.pdf")
        self.assertIn("Aifrinn na Seachtaine", "\n".join(lines_out[0]))
        self.assertNotIn("gi Teach", "\n".join(lines_out[0]))
        self.assertIn("John Gillespie", html_out)
        self.assertNotIn("gi Teach", html_out)

    def test_repair_leaves_born_digital_page(self) -> None:
        from unittest.mock import patch

        good = [
            "Ramoan Parish Ballycastle weekend bulletin Church Car Park closed",
            "Coffee morning Saturday 22nd August in the crypt after morning Mass.",
            "Lough Derg retreats August 18th, 22nd, 23rd please book in the sacristy.",
            "Weekend Mass Times Saturday Vigil 6.30pm Sunday 10.00am and 12.00noon.",
        ]
        with patch("ocr.sparse_page_ocr.extract_all_page_lines", return_value=[good]), patch(
            "ocr.sparse_page_ocr.ocr_pdf_page_lines"
        ) as mocked:
            out = repair_image_page_ocr("dummy.pdf", [good])
        mocked.assert_not_called()
        self.assertEqual(out[0], good)


if __name__ == "__main__":
    unittest.main()
