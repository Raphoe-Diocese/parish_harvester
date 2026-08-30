from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from ocr.convert_bulletin import clean_ocr_line
from ocr.text_extract import (
    all_pages_have_embedded_text,
    extract_all_page_lines,
    page_is_sparse,
    pick_richer_page_lines,
    prefer_embedded_page_text,
)


def _pdf_with_lines(pages: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for lines in pages:
        y = 760
        for line in lines:
            c.drawString(72, y, line[:110])
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


_BALLYCASTLE_LINES = [
    "Ramoan Parish Ballycastle — 21st Sunday in Ordinary Time",
    "Coffee morning in the crypt at 10.30am on Saturday 22nd August.",
    "Door collection at the Vigil Mass on Saturday 22nd August and Sunday 23rd August.",
    "Church Car Park will be closed immediately after 12noon Mass on Sunday 23rd August.",
    "Lough Derg retreats August 18th, 22nd, 23rd — please book with the parish office.",
    "Weekend Mass Times Saturday Vigil 6.30pm Sunday 10.00am and 12.00noon.",
]


class PreferEmbeddedPageTextTests(unittest.TestCase):
    def test_rich_embedded_text_beats_incomplete_vision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "parish.pdf"
            pdf_path.write_bytes(_pdf_with_lines([_BALLYCASTLE_LINES]))
            vision = [
                [
                    "Ramoan Parish Ballycastle",
                    "Coffee morning in the crypt at 10.30am on Saturday 2nd August.",
                    "Lough Derg retreats August 18th, 2nd, 23rd.",
                ]
            ]
            merged = prefer_embedded_page_text(pdf_path, vision)
            assert merged is not None
            text = "\n".join(merged[0])
            self.assertIn("Church Car Park will be closed", text)
            self.assertIn("Saturday 22nd August", text)
            self.assertNotIn("Saturday 2nd August", text)

    def test_sparse_embedded_keeps_vision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "banner.pdf"
            pdf_path.write_bytes(_pdf_with_lines([["Gortahork", "https://parishpress.ie/gort"]]))
            vision = [["Aifrinn na seachtaine " * 8, "Nora O'Donnell, An Bhealtaine"]]
            merged = prefer_embedded_page_text(pdf_path, vision)
            assert merged is not None
            self.assertEqual(merged[0], vision[0])

    def test_extract_all_keeps_mixed_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mixed.pdf"
            pdf_path.write_bytes(_pdf_with_lines([_BALLYCASTLE_LINES, ["Hi"]]))
            pages = extract_all_page_lines(pdf_path)
            assert pages is not None
            self.assertEqual(len(pages), 2)
            self.assertFalse(page_is_sparse(pages[0]))
            self.assertTrue(page_is_sparse(pages[1]))
            self.assertFalse(all_pages_have_embedded_text(pages))

    def test_pick_richer_keeps_boxed_notice_the_weaker_reader_missed(self) -> None:
        weak = [["Dorothy McKinley", "Requiescant in Pace"]]
        strong = [
            [
                "Dorothy McKinley",
                "Requiescant in Pace",
                "Enda Hill, R.I.P.",
                "The family of the late Edna Hill would like to express their sincere appreciation.",
                "Month's Mind Mass for Edna will be on Sat 29th Aug at 10am.",
                "The Causeway Coast Peace Group",
            ]
        ]
        merged = pick_richer_page_lines(weak, strong)
        assert merged is not None
        text = "\n".join(merged[0])
        self.assertIn("Enda Hill, R.I.P.", text)
        self.assertIn("Edna Hill", text)
        self.assertIn("Causeway Coast Peace Group", text)


class CleanOcrLineTests(unittest.TestCase):
    def test_keeps_real_two_digit_ordinals(self) -> None:
        self.assertEqual(
            clean_ocr_line("Coffee morning Saturday 22nd August"),
            "Coffee morning Saturday 22nd August",
        )
        self.assertEqual(clean_ocr_line("Sunday 11th and 23rd"), "Sunday 11th and 23rd")

    def test_still_collapses_true_doubled_ordinals(self) -> None:
        self.assertEqual(clean_ocr_line("1717th Sunday"), "17th Sunday")


if __name__ == "__main__":
    unittest.main()
