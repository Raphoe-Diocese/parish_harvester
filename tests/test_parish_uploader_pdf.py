from __future__ import annotations

import unittest
from datetime import date

from harvester.replay import _resolve_download_candidates
from harvester.utils import (
    PARISH_UPLOADER_EXT_PRIORITY,
    is_parish_uploader_bulletin_url,
    parish_uploader_bulletin_candidates,
)

_BASE = "https://www.parishpress.net/wp-content/uploads/parish-bulletins/donegal/raphoe/drumholm-parish/bulletin"


class TestIsParishUploaderBulletinUrl(unittest.TestCase):
    def test_recognises_every_supported_extension(self) -> None:
        for ext in PARISH_UPLOADER_EXT_PRIORITY:
            with self.subTest(ext=ext):
                self.assertTrue(is_parish_uploader_bulletin_url(f"{_BASE}.{ext}"))

    def test_recognises_url_with_cache_bust_query(self) -> None:
        self.assertTrue(is_parish_uploader_bulletin_url(f"{_BASE}.pdf?t=1782303743"))

    def test_case_insensitive_extension(self) -> None:
        self.assertTrue(is_parish_uploader_bulletin_url(f"{_BASE}.PDF"))

    def test_rejects_non_uploader_urls(self) -> None:
        self.assertFalse(is_parish_uploader_bulletin_url("https://example.org/newsletter.pdf"))
        self.assertFalse(is_parish_uploader_bulletin_url(""))
        self.assertFalse(is_parish_uploader_bulletin_url("not a url"))


class TestParishUploaderBulletinCandidates(unittest.TestCase):
    def test_pdf_url_tries_pdf_first_then_all_other_extensions(self) -> None:
        candidates = parish_uploader_bulletin_candidates(f"{_BASE}.pdf?t=1782303743")
        exts = [c.split(".")[-1].split("?")[0] for c in candidates]
        self.assertEqual(exts[0], "pdf")
        self.assertEqual(set(exts), set(PARISH_UPLOADER_EXT_PRIORITY))
        self.assertEqual(len(exts), len(set(exts)), "no duplicate extensions")

    def test_docx_url_still_tries_pdf_first(self) -> None:
        """Even if the recipe was recorded against a bulletin.docx URL, pdf
        should be tried first since that's what most weeks will actually be."""
        candidates = parish_uploader_bulletin_candidates(f"{_BASE}.docx")
        exts = [c.split(".")[-1].split("?")[0] for c in candidates]
        self.assertEqual(exts[0], "docx", "matched extension is tried first")
        self.assertIn("pdf", exts)

    def test_every_candidate_starts_with_same_base_and_has_cache_bust(self) -> None:
        candidates = parish_uploader_bulletin_candidates(f"{_BASE}.pdf")
        for candidate in candidates:
            self.assertTrue(candidate.startswith(_BASE + "."))
            self.assertIn("?t=", candidate)

    def test_non_uploader_url_returns_empty(self) -> None:
        self.assertEqual(parish_uploader_bulletin_candidates("https://example.org/x.pdf"), [])

    def test_empty_url_returns_empty(self) -> None:
        self.assertEqual(parish_uploader_bulletin_candidates(""), [])


class TestResolveDownloadCandidatesForUploaderUrls(unittest.TestCase):
    def test_uploader_url_expands_to_all_extensions_even_with_use_captured_url(self) -> None:
        """Real recipes (drumholm-parish.json etc.) set use_captured_url=True
        on the download step because there's no per-week date to rewrite —
        but that must not stop the harvester trying bulletin.docx / .jpg
        etc. when bulletin.pdf 404s that week."""
        candidates = _resolve_download_candidates(
            f"{_BASE}.pdf?t=1782303743",
            target_date=None,
            use_captured_url=True,
        )
        self.assertGreater(len(candidates), 1)
        self.assertTrue(candidates[0].startswith(f"{_BASE}.pdf"))

    def test_non_uploader_url_unaffected_by_use_captured_url(self) -> None:
        candidates = _resolve_download_candidates(
            "https://example.org/some/bulletin.pdf",
            target_date=None,
            use_captured_url=True,
        )
        self.assertEqual(candidates, ["https://example.org/some/bulletin.pdf"])

    def test_non_uploader_url_still_gets_date_rewritten(self) -> None:
        candidates = _resolve_download_candidates(
            "https://example.org/2026/06/14/bulletin.pdf",
            target_date=date(2026, 8, 9),
        )
        self.assertEqual(len(candidates), 1)
        self.assertNotEqual(candidates[0], "https://example.org/2026/06/14/bulletin.pdf")


if __name__ == "__main__":
    unittest.main()
