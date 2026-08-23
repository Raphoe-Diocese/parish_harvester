"""test_bulletin_archive_prune.py — docs/bulletins stays this-week only.

``ocr-bulletin.yml`` writes ``{diocese}-{TODAY}.html`` plus its ``-ocr`` and
``-pdf`` twins on every run and commits the folder, so without a prune the
published site gains another dated trio every week. These tests lock the prune
rule and — the part that must never break — prove a diocese keeps its
current-week OCR and PDF links afterwards.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import harvester.site_builder as site_builder
import ocr.generate_bulletin_pages as gbp

THIS_WEEK = "2026-08-23"
LAST_WEEK = "2026-08-16"
OLD_WEEK = "2026-08-09"


def _write_trio(bulletins: Path, diocese: str, page_date: str) -> list[Path]:
    """Write the three pages a viewer run produces for one diocese and date."""
    paths = [
        bulletins / f"{diocese}-{page_date}.html",
        bulletins / f"{diocese}-{page_date}-ocr.html",
        bulletins / f"{diocese}-{page_date}-pdf.html",
    ]
    for path in paths:
        path.write_text(
            f'<html><body><div id="ocr-panel">{diocese} {page_date}</div>'
            '<div class="note-box">note</div></body></html>',
            encoding="utf-8",
        )
    return paths


class ArchivePruneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bulletins = Path(self.tmp.name) / "bulletins"
        self.bulletins.mkdir(parents=True)

        # Derry regenerated three weeks running; Raphoe not regenerated this
        # run, so last week is still its newest.
        for page_date in (OLD_WEEK, LAST_WEEK, THIS_WEEK):
            _write_trio(self.bulletins, "derry", page_date)
        _write_trio(self.bulletins, "down_and_connor", OLD_WEEK)
        _write_trio(self.bulletins, "down_and_connor", THIS_WEEK)
        _write_trio(self.bulletins, "raphoe", LAST_WEEK)

        # Files the prune must never touch.
        (self.bulletins / "index.html").write_text("<html>archive</html>", encoding="utf-8")
        (self.bulletins / "raphoe").mkdir()
        (self.bulletins / "raphoe" / "index.html").write_text("<html>stub</html>", encoding="utf-8")
        (self.bulletins / "armagh-2026-05-20.html").write_text("<html>unknown</html>", encoding="utf-8")
        (self.bulletins / "notes.html").write_text("<html>notes</html>", encoding="utf-8")

        self._orig_gbp_dir = gbp.BULLETINS_DIR
        self._orig_site_dir = site_builder.BULLETINS_DIR
        gbp.BULLETINS_DIR = self.bulletins
        site_builder.BULLETINS_DIR = self.bulletins

    def tearDown(self) -> None:
        gbp.BULLETINS_DIR = self._orig_gbp_dir
        site_builder.BULLETINS_DIR = self._orig_site_dir
        self.tmp.cleanup()

    def _names(self) -> set[str]:
        return {path.name for path in self.bulletins.glob("*.html")}

    def test_prune_keeps_only_the_newest_trio_per_diocese(self) -> None:
        removed = gbp.prune_old_viewers()

        names = self._names()
        for suffix in ("", "-ocr", "-pdf"):
            self.assertIn(f"derry-{THIS_WEEK}{suffix}.html", names)
            self.assertNotIn(f"derry-{LAST_WEEK}{suffix}.html", names)
            self.assertNotIn(f"derry-{OLD_WEEK}{suffix}.html", names)
            self.assertIn(f"down_and_connor-{THIS_WEEK}{suffix}.html", names)
            self.assertNotIn(f"down_and_connor-{OLD_WEEK}{suffix}.html", names)
        self.assertEqual(9, len(removed))

    def test_diocese_not_regenerated_this_run_keeps_its_newest_trio(self) -> None:
        gbp.prune_old_viewers()

        names = self._names()
        for suffix in ("", "-ocr", "-pdf"):
            self.assertIn(f"raphoe-{LAST_WEEK}{suffix}.html", names)

    def test_current_week_ocr_and_pdf_links_survive_prune(self) -> None:
        gbp.prune_old_viewers()

        for diocese in ("derry", "down_and_connor"):
            viewer, viewer_date = site_builder._latest_viewer(diocese)
            self.assertIsNotNone(viewer, f"{diocese} lost its viewer page")
            self.assertEqual(THIS_WEEK, viewer_date)
            self.assertTrue(viewer.exists())

            ocr_page = site_builder._latest_ocr_standalone(diocese)
            self.assertIsNotNone(ocr_page, f"{diocese} lost its OCR page")
            self.assertEqual(f"{diocese}-{THIS_WEEK}-ocr.html", ocr_page.name)

            pdf_page = site_builder._latest_pdf_standalone(diocese)
            self.assertIsNotNone(pdf_page, f"{diocese} lost its PDF page")
            self.assertEqual(f"{diocese}-{THIS_WEEK}-pdf.html", pdf_page.name)

            # docs/index.html "Text" button — must stay a dated page, not the
            # bulletins/index.html fallback.
            ocr_url = site_builder._ocr_standalone_url(diocese)
            self.assertTrue(ocr_url.endswith(f"bulletins/{diocese}-{THIS_WEEK}-ocr.html"), ocr_url)
            self.assertTrue(
                site_builder._pdf_standalone_url(diocese).endswith(
                    f"bulletins/{diocese}-{THIS_WEEK}-pdf.html"
                )
            )

        # Raphoe was not regenerated this run — it keeps last week's links.
        self.assertTrue(
            site_builder._ocr_standalone_url("raphoe").endswith(f"bulletins/raphoe-{LAST_WEEK}-ocr.html")
        )

    def test_prune_never_touches_index_subfolders_or_unknown_files(self) -> None:
        gbp.prune_old_viewers()

        names = self._names()
        self.assertIn("index.html", names)
        self.assertIn("notes.html", names)
        self.assertIn("armagh-2026-05-20.html", names)
        self.assertTrue((self.bulletins / "raphoe" / "index.html").exists())

    def test_prune_spares_a_deliberately_rewritten_older_date(self) -> None:
        gbp.prune_old_viewers({"derry": LAST_WEEK})

        names = self._names()
        self.assertIn(f"derry-{LAST_WEEK}-ocr.html", names)
        self.assertIn(f"derry-{THIS_WEEK}-ocr.html", names)
        self.assertNotIn(f"derry-{OLD_WEEK}-ocr.html", names)

    def test_prune_can_be_switched_off(self) -> None:
        with mock.patch.dict("os.environ", {"BULLETIN_PRUNE_DISABLE": "1"}):
            removed = gbp.prune_old_viewers()

        self.assertEqual([], removed)
        self.assertIn(f"derry-{OLD_WEEK}-ocr.html", self._names())

    def test_rebuild_indexes_prunes_then_lists_only_survivors(self) -> None:
        gbp.rebuild_indexes()

        index_html = (self.bulletins / "index.html").read_text(encoding="utf-8")
        self.assertIn(f"derry-{THIS_WEEK}.html", index_html)
        self.assertIn(f"raphoe-{LAST_WEEK}.html", index_html)
        self.assertNotIn(f"derry-{LAST_WEEK}.html", index_html)
        self.assertNotIn(f"derry-{OLD_WEEK}.html", index_html)
        # UK dates for readers.
        self.assertIn("23/08/2026", index_html)


if __name__ == "__main__":
    unittest.main()
