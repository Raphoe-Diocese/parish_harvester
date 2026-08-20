"""Tests for harvester.stitcher — reject error/security pages in the mega PDF.

Must not remove real (incl. short) bulletin pages or Irish/bilingual text.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import PyPDF2
from reportlab.pdfgen import canvas

from harvester.stitcher import stitch_mega_pdf


def _make_text_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(72, 700, text)
    c.save()


def _fake_result(key: str, file_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        display_name=key.title(),
        url="https://example.com/" + key,
        status="ok",
        file_path=file_path,
        is_stale=False,
        is_fallback=False,
    )


class StitcherJunkPageTests(unittest.TestCase):
    def test_error_page_excluded_but_real_page_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            current_dir = tmp_path / "current"
            current_dir.mkdir()
            bulletins_dir = tmp_path / "bulletins"

            good_pdf = current_dir / "goodparish.pdf"
            _make_text_pdf(
                good_pdf,
                "Good Parish - Mass times Saturday 6pm, Sunday 9am and 11am. "
                "Parish office open Mon-Fri. Contact Fr Smith on 087 1234567.",
            )
            bad_pdf = current_dir / "badparish.pdf"
            _make_text_pdf(bad_pdf, "Access Denied - Security Check - Please verify you are human")

            results = [
                _fake_result("goodparish", good_pdf),
                _fake_result("badparish", bad_pdf),
            ]

            stitch_mega_pdf(results, current_dir, bulletins_dir, date(2026, 7, 26))

            output = bulletins_dir / "all_bulletins_2026-07-26.pdf"
            self.assertTrue(output.exists())
            reader = PyPDF2.PdfReader(str(output))
            all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Mass times", all_text)
            self.assertNotIn("Security Check", all_text)

    def test_irish_bilingual_short_page_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            current_dir = tmp_path / "current"
            current_dir.mkdir()
            bulletins_dir = tmp_path / "bulletins"

            pdf = current_dir / "gaeilgeparish.pdf"
            _make_text_pdf(
                pdf,
                "Ar dheis De go raibh a anam. Aifreann Dé Domhnaigh ar 11am. "
                "Mass times: Sunday 11am. Fr O'Donnell.",
            )
            results = [_fake_result("gaeilgeparish", pdf)]

            stitch_mega_pdf(results, current_dir, bulletins_dir, date(2026, 7, 26))

            output = bulletins_dir / "all_bulletins_2026-07-26.pdf"
            self.assertTrue(output.exists())
            reader = PyPDF2.PdfReader(str(output))
            all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Aifreann", all_text)
            index_path = output.with_name(output.stem + ".pages.json")
            self.assertTrue(index_path.exists())
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertIn("gaeilgeparish", payload["parishes"])
            rng = payload["parishes"]["gaeilgeparish"]
            self.assertEqual(rng["start_page"], 1)
            self.assertGreaterEqual(rng["end_page"], 1)


if __name__ == "__main__":
    unittest.main()
