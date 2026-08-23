from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from ocr.fidelity import (
    check_parish_files,
    missing_phrases,
    normalize_for_compare,
)


def _text_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 760
    for line in text.splitlines():
        c.drawString(72, y, line[:110])
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()


def _ocr_html(body: str) -> str:
    return (
        "<html><body>"
        f'<div class="ocr-body">{body}</div>'
        '<p class="note-box">Auto-generated from the bulletin PDF.</p>'
        "</body></html>"
    )


_PDF_BODY = (
    "MASS TIMES Vigil Mass on Saturday 22nd August at 6.30pm.\n"
    "Please do not park in the Church Car Park during funerals.\n"
    "Please pray for Enda Hill R.I.P. and Edna Hill of the parish this week.\n"
    "Community notices continue with weekday Masses and parish contacts listed."
)


class OcrFidelityTests(unittest.TestCase):
    def test_reports_dropped_church_car_park_and_edna_hill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf_path = root / "ballycastleparish.pdf"
            ocr_path = root / "ballycastleparish-ocr.html"
            pdf_path.write_bytes(_text_pdf(_PDF_BODY))
            ocr_path.write_text(
                _ocr_html(
                    "<p>MASS TIMES Vigil Mass on Saturday 2nd August at 6.30pm.</p>"
                    "<p>Community notices continue with weekday Masses and parish contacts listed.</p>"
                ),
                encoding="utf-8",
            )
            row = check_parish_files(
                pdf_path, ocr_path, diocese="down_and_connor", parish_key="ballycastleparish"
            )
            self.assertFalse(row.ok)
            blob = " ".join(row.missing).lower()
            self.assertIn("church", blob)
            self.assertIn("car", blob)
            self.assertIn("park", blob)
            self.assertTrue("edna" in blob or "enda" in blob or "hill" in blob)

    def test_ok_when_ocr_has_the_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf_path = root / "ballycastleparish.pdf"
            ocr_path = root / "ballycastleparish-ocr.html"
            pdf_path.write_bytes(_text_pdf(_PDF_BODY))
            ocr_path.write_text(
                _ocr_html(
                    "<p>MASS TIMES Vigil Mass on Saturday 22nd August at 6.30pm.</p>"
                    "<p>Please do not park in the Church Car Park during funerals.</p>"
                    "<p>Please pray for Enda Hill R.I.P. and Edna Hill of the parish this week.</p>"
                    "<p>Community notices continue with weekday Masses and parish contacts listed.</p>"
                ),
                encoding="utf-8",
            )
            row = check_parish_files(pdf_path, ocr_path)
            self.assertTrue(row.ok, row.missing)
            self.assertEqual(row.missing, [])

    def test_normalize_enda_hill_rip(self) -> None:
        norm = normalize_for_compare("Enda Hill R.I.P.")
        self.assertIn("enda", norm)
        self.assertIn("hill", norm)
        self.assertIn("rip", norm)
        self.assertEqual(normalize_for_compare("Enda Hill RIP"), "enda hill rip")

    def test_parish_name_glue_is_not_a_gap_when_words_exist(self) -> None:
        pdf = (
            "please do not park in the church car park ballycastle after five extra words"
        )
        ocr = (
            "please do not park in the church car park after five extra words "
            "ballycastle parish bulletin"
        )
        self.assertEqual(missing_phrases(pdf, ocr, window=8), [])


if __name__ == "__main__":
    unittest.main()
