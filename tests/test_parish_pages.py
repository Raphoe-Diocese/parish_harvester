from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from ocr import parish_pages


def _make_pdf(num_pages: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(1, num_pages + 1):
        c.drawString(72, 700, f"Test page {i}")
        c.showPage()
    c.save()
    return buf.getvalue()


_RAW_FRAGMENT = """
<p class="page-label">Page 1</p>
<h2 class="b-title">Index</h2>
<p>Welcome to the diocese bulletin.</p>
<hr>
<p class="page-label">Page 2</p>
<p>Ardara Parish<br>
http://ardara.ie</p>
<p>Sunday mass at 10am. Recently deceased: John Smith.</p>
<hr>
<p class="page-label">Page 3</p>
<p>Annagry<br>
https://annagryparish.ie/newsletter-2/</p>
<p>Mass at 11am.</p>
"""


class LoadOkParishesTests(unittest.TestCase):
    def test_filters_by_diocese_and_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_path = Path(tmpdir) / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "url": "http://ardara.ie",
                            },
                            "annagryparish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Annagry",
                                "url": "https://annagryparish.ie/newsletter-2/",
                            },
                            "broken-parish": {
                                "outcome": "failed",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Broken",
                            },
                            "other-diocese-parish": {
                                "outcome": "ok",
                                "diocese": "Derry Diocese",
                                "display_name": "Other",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            parishes = parish_pages.load_ok_parishes("raphoe", parish_status_path=status_path)
            keys = [p.key for p in parishes]
            self.assertEqual(keys, ["annagryparish", "ardara"])  # sorted A-Z by display name

    def test_missing_file_returns_empty(self) -> None:
        parishes = parish_pages.load_ok_parishes("raphoe", parish_status_path=Path("/nonexistent/path.json"))
        self.assertEqual(parishes, [])


class SlicePdfPagesTests(unittest.TestCase):
    def test_slices_expected_page_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mega.pdf"
            pdf_path.write_bytes(_make_pdf(4))
            sliced = parish_pages.slice_pdf_pages(pdf_path, 2, 3)
            self.assertIsNotNone(sliced)
            reader = PdfReader(io.BytesIO(sliced))
            self.assertEqual(len(reader.pages), 2)

    def test_clamps_out_of_range_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mega.pdf"
            pdf_path.write_bytes(_make_pdf(2))
            sliced = parish_pages.slice_pdf_pages(pdf_path, 5, 9)
            reader = PdfReader(io.BytesIO(sliced))
            self.assertEqual(len(reader.pages), 1)

    def test_missing_pdf_returns_none(self) -> None:
        self.assertIsNone(parish_pages.slice_pdf_pages(Path("/nonexistent/mega.pdf"), 1, 1))


class WriteParishPagesForDioceseTests(unittest.TestCase):
    def test_writes_pages_with_sliced_pdf_and_ocr_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "url": "http://ardara.ie",
                            },
                            "annagryparish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Annagry",
                                "url": "https://annagryparish.ie/newsletter-2/",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pdf_path = root / "raphoe_mega_bulletin.pdf"
            pdf_path.write_bytes(_make_pdf(3))
            out_dir = root / "docs" / "parishes" / "raphoe"

            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-09",
                pdf_path,
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )

            self.assertEqual(set(written), {"ardara", "annagryparish"})

            ardara_html = (out_dir / "ardara.html").read_text(encoding="utf-8")
            self.assertIn("Ardara Parish Bulletin", ardara_html)
            self.assertIn("Sunday mass at 10am", ardara_html)
            self.assertIn("Recently deceased", ardara_html)
            self.assertIn("Annagry", ardara_html)  # appears in the "other parishes" grid
            self.assertIn('href="../../dioceses/raphoe/index.html"', ardara_html)
            self.assertIn('href="ardara.pdf"', ardara_html)
            self.assertTrue((out_dir / "ardara.pdf").exists())
            reader = PdfReader(str(out_dir / "ardara.pdf"))
            self.assertEqual(len(reader.pages), 1)  # just page 2 of the mega PDF

            annagry_html = (out_dir / "annagryparish.html").read_text(encoding="utf-8")
            self.assertIn("Mass at 11am", annagry_html)
            self.assertIn('href="annagryparish.pdf"', annagry_html)

            self.assertTrue((out_dir / "ardara-ocr.html").exists())
            self.assertTrue((out_dir / "ardara-pdf.html").exists())

    def test_no_ok_parishes_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(json.dumps({"parishes": {}}), encoding="utf-8")
            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-09",
                root / "missing.pdf",
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=root / "docs" / "parishes" / "raphoe",
                parish_status_path=status_path,
            )
            self.assertEqual(written, [])

    def test_falls_back_gracefully_when_parish_not_found_in_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "unmatched-parish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Totally Unmatched Parish Name",
                                "url": "http://example.com",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pdf_path = root / "raphoe_mega_bulletin.pdf"
            pdf_path.write_bytes(_make_pdf(3))
            out_dir = root / "docs" / "parishes" / "raphoe"

            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-09",
                pdf_path,
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )
            self.assertEqual(written, ["unmatched-parish"])
            html_out = (out_dir / "unmatched-parish.html").read_text(encoding="utf-8")
            self.assertIn("No searchable text was found", html_out)
            # No page range could be found, so it falls back to the full diocese PDF.
            self.assertIn('href="../../mega_pdf/raphoe_mega_bulletin.pdf"', html_out)
            self.assertFalse((out_dir / "unmatched-parish.pdf").exists())


if __name__ == "__main__":
    unittest.main()
