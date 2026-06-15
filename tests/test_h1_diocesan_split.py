"""test_h1_diocesan_split.py — tests for diocesan bulletin output paths."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class BulletinsPathTests(unittest.TestCase):
    """generate_bulletin_pages writes per-diocese summaries and diffs."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self.tmp.name)

        import ocr.generate_bulletin_pages as gbp

        self._orig_summaries = gbp.SUMMARIES_DIR
        self._orig_diffs = gbp.DIFFS_DIR
        self._orig_bulletins_dir = gbp.BULLETINS_DIR

        gbp.SUMMARIES_DIR = self.tmp_root / "summaries"
        gbp.DIFFS_DIR = self.tmp_root / "diffs"
        gbp.BULLETINS_DIR = self.tmp_root / "bulletins"

        self.gbp = gbp

    def tearDown(self) -> None:
        self.gbp.SUMMARIES_DIR = self._orig_summaries
        self.gbp.DIFFS_DIR = self._orig_diffs
        self.gbp.BULLETINS_DIR = self._orig_bulletins_dir
        self.tmp.cleanup()

    def test_summaries_written_under_diocese_subfolder(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="derry",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("Blessed Sacrament", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        summaries_dir = self.tmp_root / "summaries" / "derry"
        json_files = [f for f in summaries_dir.iterdir() if f.suffix == ".json" and f.name != "_index.json"]
        self.assertGreater(len(json_files), 0, "At least one summary JSON should be written")

    def test_diffs_written_under_diocese_subfolder(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="down_and_connor",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("St Mary's", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        diffs_dir = self.tmp_root / "diffs" / "down_and_connor"
        json_files = [f for f in diffs_dir.iterdir() if f.suffix == ".json" and f.name != "_index.json"]
        self.assertGreater(len(json_files), 0, "At least one diff JSON should be written")

    def test_index_json_created_for_summaries(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="derry",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("Blessed Sacrament", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        index_path = self.tmp_root / "summaries" / "derry" / "_index.json"
        self.assertTrue(index_path.exists(), "_index.json should be created for summaries")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual("derry", index["diocese"])
        self.assertIsInstance(index["entries"], dict)
        self.assertGreater(len(index["entries"]), 0)

    def test_index_json_created_for_diffs(self) -> None:
        os.environ["PARISH_AI_SUMMARIES_DISABLE"] = "1"
        try:
            self.gbp._write_parish_reader_outputs(
                diocese="derry",
                bulletin_date="2026-05-22",
                ocr_text="Some bulletin text.",
                parish_links=[("Blessed Sacrament", "https://example.com")],
            )
        finally:
            del os.environ["PARISH_AI_SUMMARIES_DISABLE"]

        index_path = self.tmp_root / "diffs" / "derry" / "_index.json"
        self.assertTrue(index_path.exists(), "_index.json should be created for diffs")


if __name__ == "__main__":
    unittest.main()
