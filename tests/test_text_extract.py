from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from ocr.convert_bulletin import clean_ocr_line
from ocr.text_extract import (
    extract_all_page_lines,
    page_is_sparse,
    pick_richer_page_lines,
    prefer_embedded_page_text,
)


def _text_pdf(pages: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for text in pages:
        y = 760
        for line in text.splitlines():
            c.drawString(72, y, line[:110])
            y -= 16
            if y < 80:
                c.showPage()
                y = 760
        c.showPage()
    c.save()
    return buf.getvalue()


_RICH_PAGE = (
    "MASS TIMES and parish notices for this week.\n"
    "Vigil Mass on Saturday 22nd August at 6.30pm in St Patrick's.\n"
    "Please do not park in the Church Car Park during funerals this week.\n"
    "Recently deceased: please keep the family in your prayers this Sunday.\n"
    "Community notices continue below with weekday Masses and contacts."
)


class PreferEmbeddedTextTests(unittest.TestCase):
    def test_prefer_embedded_beats_incomplete_vision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "ballycastle.pdf"
            pdf_path.write_bytes(_text_pdf([_RICH_PAGE]))
            vision = [
                [
                    "MASS TIMES",
                    "Vigil Mass on Saturday 2nd August at 6.30pm in St Patrick's.",
                    "Recently deceased: please keep the family in your prayers this Sunday.",
                ]
            ]
            preferred = prefer_embedded_page_text(pdf_path, vision)
            joined = "\n".join(preferred[0])
            self.assertIn("Church Car Park", joined)
            self.assertIn("Saturday 22nd August", joined)
            self.assertNotIn("Saturday 2nd August", joined)

    def test_sparse_page_keeps_vision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "banner.pdf"
            pdf_path.write_bytes(
                _text_pdf(["Ballycastle\nhttps://www.ballycastleparish.com"])
            )
            vision = [
                [
                    "MASS TIMES and a full parish body from vision OCR of the image page.",
                    "Vigil Mass on Saturday 22nd August at 6.30pm in St Patrick's Church.",
                    "Please do not park in the Church Car Park during funerals this week.",
                    "Recently deceased notices and community events continue below here.",
                ]
            ]
            preferred = prefer_embedded_page_text(pdf_path, vision)
            joined = "\n".join(preferred[0])
            self.assertTrue(page_is_sparse(extract_all_page_lines(pdf_path)[0]))
            self.assertIn("Church Car Park", joined)
            self.assertIn("vision OCR", joined)

    def test_extract_all_keeps_mixed_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mixed.pdf"
            pdf_path.write_bytes(
                _text_pdf(
                    [
                        _RICH_PAGE,
                        "Ballycastle\nhttps://www.ballycastleparish.com",
                    ]
                )
            )
            pages = extract_all_page_lines(pdf_path)
            self.assertIsNotNone(pages)
            self.assertEqual(len(pages), 2)
            self.assertFalse(page_is_sparse(pages[0]))
            self.assertTrue(page_is_sparse(pages[1]))
            self.assertIn("Church Car Park", "\n".join(pages[0]))

    def test_pick_richer_keeps_boxed_notice(self) -> None:
        pypdf = [
            [
                "MASS TIMES Saturday 22nd August at 6.30pm.",
                "Recently deceased notices continue this week in the parish.",
            ]
        ]
        pymupdf = [
            [
                "MASS TIMES Saturday 22nd August at 6.30pm.",
                "Please pray for Enda Hill R.I.P. and Edna Hill of the parish.",
                "Recently deceased notices continue this week in the parish.",
            ]
        ]
        picked = pick_richer_page_lines(pymupdf, pypdf)
        joined = "\n".join(picked[0])
        self.assertIn("Enda Hill", joined)
        self.assertIn("Edna Hill", joined)

    def test_clean_ocr_line_keeps_real_ordinals(self) -> None:
        self.assertEqual(clean_ocr_line("Saturday 22nd August"), "Saturday 22nd August")
        self.assertEqual(clean_ocr_line("Sunday 11th August"), "Sunday 11th August")
        self.assertEqual(clean_ocr_line("the 1717th of the month"), "the 17th of the month")

    def test_collapse_ocr_spacing_fixes_letter_spaced_titles(self) -> None:
        from ocr.convert_bulletin import collapse_ocr_spacing, clean_ocr_line

        self.assertEqual(
            collapse_ocr_spacing("PA R O C H IA L HO U S E"),
            "PAROCHIALHOUSE",
        )
        self.assertIn("Sunday", collapse_ocr_spacing("S unday Mass"))
        self.assertIn("Week", collapse_ocr_spacing("We e k beginning"))
        self.assertIn("Twenty", collapse_ocr_spacing("Tw e nty -fourth"))
        self.assertIn("Saturday", collapse_ocr_spacing("Sa tur da y Vigil"))
        self.assertIn("Ardara", collapse_ocr_spacing("Ar da r a 7.30pm"))
        # Do not glue ordinary English.
        self.assertEqual(
            collapse_ocr_spacing("Weekend Mass Times"),
            "Weekend Mass Times",
        )

    def test_collapse_ardara_style_bulletin_dump(self) -> None:
        from ocr.convert_bulletin import clean_ocr_line

        # Real letter-spaced dump from docs/bulletins/raphoe-2026-09-23.html
        raw = (
            "Jimmy M c Gill Aighe w ho w as burie d on We dne sday "
            "Je ssie & C harle s C unningham, S e attle & M e e ntashask "
            "w hose ashe s w e re in inte rre d during the w e e k. "
            "C athle e n M c Ne lis Dublin & Tully be g w ho passe d aw ay on 7 th "
            "S e pte mbe r. Fune ral arrange me nts late r. "
            "Et ern a l rest gra n t u n t o t h em O Lord"
        )
        out = clean_ocr_line(raw)
        self.assertIn("Jimmy McGill Aighe who was buried on Wednesday", out)
        self.assertIn("Jessie & Charles Cunningham", out)
        self.assertIn("Seattle", out)
        self.assertIn("ashes were interred", out)
        self.assertIn("Cathleen McNelis", out)
        self.assertIn("passed away on 7th", out)
        self.assertIn("Funeral arrangements later", out)
        self.assertIn("Eternal rest grant unto them O Lord", out)
        self.assertNotIn("Aighew", out)
        self.assertNotIn("whowas", out)
        self.assertNotIn("Tully be g", out)
        self.assertNotIn("pmArdara", out)


if __name__ == "__main__":
    unittest.main()
