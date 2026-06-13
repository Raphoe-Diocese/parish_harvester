from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harvester.site_health import (
    hostname_from_url,
    load_health,
    probe_dns,
    record_probe,
    should_mark_inactive,
)
from ocr.parish_splitter import split_ocr_by_parish
from ocr.text_extract import extract_text_pages


class TextExtractTests(unittest.TestCase):
    def test_extract_returns_none_for_missing_file(self) -> None:
        self.assertIsNone(extract_text_pages("/no/such/file.pdf"))

    def test_extract_returns_none_for_empty_pdf(self) -> None:
        from PyPDF2 import PdfWriter

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with path.open("wb") as fh:
                writer.write(fh)
            # Blank page has no text — should return None
            self.assertIsNone(extract_text_pages(path))


class ParishSplitterTests(unittest.TestCase):
    def test_split_finds_parish_sections(self) -> None:
        text = (
            "PAGE 1\n"
            "Banagher\n"
            "Mass Sunday 10am\n"
            "PAGE 2\n"
            "Culdaff\n"
            "Bingo Friday 8pm\n"
        )
        chunks = split_ocr_by_parish(
            text,
            [("banagher", "Banagher"), ("culdaff", "Culdaff")],
        )
        self.assertIn("Mass Sunday", chunks["banagher"])
        self.assertIn("Bingo Friday", chunks["culdaff"])


class SiteHealthTests(unittest.TestCase):
    def test_hostname_from_url(self) -> None:
        self.assertEqual(hostname_from_url("http://www.example.com/path"), "www.example.com")

    def test_record_probe_nxdomain_strikes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "health.json"
            record_probe("testparish", "http://dead.example", "nxdomain", path=path)
            entry = record_probe("testparish", "http://dead.example", "nxdomain", path=path)
            self.assertTrue(should_mark_inactive(entry))

    def test_ok_resets_strikes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "health.json"
            record_probe("p", "http://a.example", "nxdomain", path=path)
            entry = record_probe("p", "http://a.example", "ok", path=path)
            self.assertFalse(should_mark_inactive(entry))
            self.assertEqual(entry.get("nxdomain_strikes"), 0)

    def test_probe_dns_localhost_ok(self) -> None:
        with mock.patch("harvester.site_health.socket.getaddrinfo", return_value=[(0,)]):
            self.assertEqual(probe_dns("localhost"), "ok")


if __name__ == "__main__":
    unittest.main()
