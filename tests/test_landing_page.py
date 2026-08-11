from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import harvester.site_builder as site_builder


class LandingPageTests(unittest.TestCase):
    def test_landing_lists_all_dioceses_and_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs = root / "docs"
            recipes = root / "parishes" / "recipes"
            bulletins = docs / "bulletins"
            report = root / "Bulletins" / "report.json"

            (recipes / "derry").mkdir(parents=True, exist_ok=True)
            (recipes / "down_and_connor").mkdir(parents=True, exist_ok=True)
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (recipes / "derry" / "ardmoreparish.json").write_text(
                json.dumps({"parish_key": "ardmoreparish", "parish_name": "Ardmore", "start_url": "https://example.com/a"}),
                encoding="utf-8",
            )
            (recipes / "down_and_connor" / "antrimparish.json").write_text(
                json.dumps({"parish_key": "antrimparish", "parish_name": "Antrim", "start_url": "https://example.com/b"}),
                encoding="utf-8",
            )
            (root / "parishes" / "raphoe_diocese_bulletin_urls.txt").write_text(
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
                '<div id="ocr-panel">Derry text</div><div class="note-box">note</div>',
                encoding="utf-8",
            )
            (bulletins / "down_and_connor-2026-05-22.html").write_text(
                '<div id="ocr-panel">Down text</div><div class="note-box">note</div>',
                encoding="utf-8",
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps({"downloaded": [{"parish": "ardmoreparish"}, {"parish": "antrimparish"}]}),
                encoding="utf-8",
            )
            (docs / "reliability.json").write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardmoreparish": {"success_rate": 0.9},
                            "antrimparish": {"success_rate": 0.4},
                        }
                    }
                ),
                encoding="utf-8",
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

            index_html = (docs / "index.html").read_text(encoding="utf-8")

            # The 3 live dioceses are prominent, near the top, each with a
            # one-click link to its collated (mega) bulletin and its text
            # bulletin — not a full-size "coming soon" card.
            self.assertIn("Live dioceses", index_html)
            self.assertEqual(index_html.count("live-card\""), 3)
            self.assertIn("Derry Diocese", index_html)
            self.assertIn("Down and Connor Diocese", index_html)
            self.assertIn("Raphoe Diocese", index_html)
            self.assertIn("Open Collated Bulletin", index_html)
            self.assertIn("Mega PDF", index_html)
            self.assertIn("Text Bulletin", index_html)
            self.assertIn("🟢", index_html)
            self.assertIn("🔴", index_html)

            # The other 23 dioceses collapse into one small expandable list.
            self.assertIn("More dioceses — coming soon (23)", index_html)
            self.assertNotIn("Parish of Raphoe", index_html)

            links = re.findall(r'href="dioceses/([a-z0-9-]+)/"', index_html)
            self.assertEqual(len(links), 26)
            for key in links:
                self.assertTrue((docs / "dioceses" / key / "index.html").exists(), key)


if __name__ == "__main__":
    unittest.main()
