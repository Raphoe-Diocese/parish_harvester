from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import harvester.site_builder as site_builder


class SiteBuilderTests(unittest.TestCase):
    def test_run_writes_live_and_placeholder_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs = root / "docs"
            recipes = root / "parishes" / "recipes"
            bulletins = docs / "bulletins"
            report = root / "Bulletins" / "report.json"
            parishes_dir = root / "parishes"

            (recipes / "derry").mkdir(parents=True, exist_ok=True)
            (recipes / "derry" / "ardmoreparish.json").write_text(
                json.dumps(
                    {
                        "parish_key": "ardmoreparish",
                        "parish_name": "Ardmore",
                        "start_url": "https://example.com/ardmore",
                    }
                ),
                encoding="utf-8",
            )
            parishes_dir.mkdir(parents=True, exist_ok=True)
            (parishes_dir / "raphoe_diocese_bulletin_urls.txt").write_text(
                "\n".join(
                    [
                        "# --- Parish of Raphoe ---",
                        "# key: drive-raphoe-town",
                        "# page: https://drive.google.com/file/d/abc/view",
                        "https://drive.usercontent.google.com/download?id=abc&export=download",
                    ]
                ),
                encoding="utf-8",
            )
            bulletins.mkdir(parents=True, exist_ok=True)
            (bulletins / "derry-2026-05-22.html").write_text(
                '<div id="ocr-panel">Line one</div><div class="note-box">note</div>',
                encoding="utf-8",
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps({"downloaded": [{"parish": "ardmoreparish"}]}),
                encoding="utf-8",
            )

            # A per-parish page already generated for this diocese this week
            # (see ocr.parish_pages) — the diocese A-Z grid should link to it.
            parish_status_path = parishes_dir / "parish_status.json"
            parish_status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardmoreparish": {
                                "outcome": "ok",
                                "diocese": "Derry Diocese",
                                "display_name": "Ardmore",
                                "url": "https://example.com/ardmore",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            derry_parish_pages_dir = docs / "parishes" / "derry"
            derry_parish_pages_dir.mkdir(parents=True, exist_ok=True)
            (derry_parish_pages_dir / "ardmoreparish.html").write_text(
                "<html><body>Ardmore parish page</body></html>", encoding="utf-8"
            )

            old = (site_builder.RECIPES_DIR, site_builder.BULLETINS_DIR, site_builder.RELIABILITY_PATH, site_builder.REPO_ROOT)
            site_builder.RECIPES_DIR = recipes
            site_builder.BULLETINS_DIR = bulletins
            site_builder.RELIABILITY_PATH = docs / "reliability.json"
            site_builder.REPO_ROOT = root
            try:
                site_builder.run(report_path=report, docs_dir=docs)
            finally:
                site_builder.RECIPES_DIR, site_builder.BULLETINS_DIR, site_builder.RELIABILITY_PATH, site_builder.REPO_ROOT = old

            derry_page = (docs / "dioceses" / "derry" / "index.html").read_text(encoding="utf-8")
            raphoe_page = (docs / "dioceses" / "raphoe" / "index.html").read_text(encoding="utf-8")
            armagh_page = (docs / "dioceses" / "armagh" / "index.html").read_text(encoding="utf-8")

            self.assertIn("Download PDF", derry_page)
            self.assertIn("Open PDF in new tab", derry_page)
            self.assertIn("Open bulletin text in new tab", derry_page)
            self.assertIn("Distraction-free view", derry_page)
            self.assertIn("Line one", derry_page)
            self.assertIn("DERRY", derry_page)
            self.assertIn("Derry Collated Bulletin", derry_page)
            self.assertIn("Parish of Raphoe", raphoe_page)
            self.assertIn("We're still collecting bulletins for this diocese", armagh_page)

            # Same canonical viewer design used for every trained live diocese page.
            self.assertIn('id="panel-pdf"', derry_page)
            self.assertIn('id="panel-ocr"', derry_page)

            # A-Z grid links to the already-generated internal parish page
            # (ocr.parish_pages) instead of only the external parish site.
            self.assertIn('href="../../parishes/derry/ardmoreparish.html"', derry_page)
            self.assertIn("🔗 Site", derry_page)


if __name__ == "__main__":
    unittest.main()
