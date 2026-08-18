from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from harvester.retention import DEFAULT_POLICY, apply_retention


def _write_file(path: Path, content: bytes = b"data", age_days: int = 0) -> Path:
    """Write a file and optionally back-date its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


class RetentionDryRunTests(unittest.TestCase):
    def test_dry_run_makes_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_pdf = _write_file(root / "Bulletins" / "current" / "old.pdf", age_days=70)
            report = apply_retention(root, dry_run=True)
            self.assertTrue(old_pdf.exists(), "dry_run must not delete files")
            self.assertIn("before_bytes", report)
            self.assertIn("after_bytes", report)
            self.assertEqual(report["zipped_files"], [])


class RetentionOldFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self.root = Path(self._tmp)
        policy = {
            "create_archives": False,
            "keep_weeks_individual": 1,
            "keep_weeks_mega_pdf": 1,
            "keep_months_archive": 0,
            "hard_size_cap_gb": 100.0,
        }
        (self.root / "parishes").mkdir(parents=True, exist_ok=True)
        (self.root / "parishes" / "retention_policy.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_old_individual_pdfs_deleted_without_zip(self) -> None:
        old_pdf = _write_file(
            self.root / "Bulletins" / "current" / "old_parish.pdf",
            content=b"%PDF-1.4 old",
            age_days=14,
        )
        report = apply_retention(self.root, dry_run=False)

        self.assertFalse(old_pdf.exists(), "Old PDF should be removed without archiving")
        archive_dir = self.root / "Bulletins" / "archive"
        zips = list(archive_dir.glob("*.zip")) if archive_dir.is_dir() else []
        self.assertEqual(zips, [], "Must not create archive zip files")
        self.assertEqual(report["zipped_files"], [])
        self.assertGreater(len(report["deleted_files"]), 0)

    def test_recent_pdfs_not_touched(self) -> None:
        new_pdf = _write_file(
            self.root / "Bulletins" / "current" / "new.pdf",
            content=b"%PDF-1.4 new",
            age_days=0,
        )
        apply_retention(self.root, dry_run=False)
        self.assertTrue(new_pdf.exists(), "Recent PDF should NOT be removed")

    def test_mega_pdfs_never_deleted(self) -> None:
        mega = _write_file(
            self.root / "mega_pdf" / "raphoe_mega_bulletin.pdf",
            content=b"%PDF-1.4 mega",
            age_days=400,
        )
        docs_mega = _write_file(
            self.root / "docs" / "mega_pdf" / "derry_mega_bulletin.pdf",
            content=b"%PDF-1.4 docs mega",
            age_days=400,
        )
        apply_retention(self.root, dry_run=False)
        self.assertTrue(mega.exists(), "Mega PDF must stay for OCR/viewer")
        self.assertTrue(docs_mega.exists(), "docs/mega_pdf must stay")
        archive_dir = self.root / "Bulletins" / "archive"
        zips = list(archive_dir.glob("*.zip")) if archive_dir.is_dir() else []
        self.assertEqual(zips, [])

    def test_report_keys_present(self) -> None:
        report = apply_retention(self.root, dry_run=False)
        for key in ("before_bytes", "after_bytes", "zipped_files", "deleted_files", "warnings"):
            self.assertIn(key, report, f"Missing key: {key}")

    def test_old_archives_deleted(self) -> None:
        archive_dir = self.root / "Bulletins" / "archive"
        old_zip = _write_file(
            archive_dir / "2024-01-individual-pdfs.zip",
            content=b"PK\x03\x04",
            age_days=1,
        )
        apply_retention(self.root, dry_run=False)
        self.assertFalse(old_zip.exists(), "Leftover archive zip should be deleted")

    def test_default_policy_disables_archives(self) -> None:
        self.assertFalse(DEFAULT_POLICY["create_archives"])
        self.assertEqual(DEFAULT_POLICY["keep_months_archive"], 0)


class RetentionHardCapTests(unittest.TestCase):
    def test_hard_cap_triggers_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = {
                "create_archives": False,
                "keep_weeks_individual": 1,
                "keep_weeks_mega_pdf": 1,
                "keep_months_archive": 0,
                "hard_size_cap_gb": 0.000001,
            }
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (root / "parishes" / "retention_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            _write_file(root / "Bulletins" / "current" / "big.pdf", content=b"x" * 2048)

            report = apply_retention(root, dry_run=False)
            self.assertTrue(
                any("hard cap" in w.lower() or "exceeds" in w.lower() for w in report["warnings"]),
                f"Expected a hard cap warning, got: {report['warnings']}",
            )
            self.assertEqual(report["zipped_files"], [])

    def test_default_policy_loaded_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = apply_retention(root, dry_run=True)
            self.assertIn("before_bytes", report)
            self.assertEqual(report["zipped_files"], [])


class RetentionPolicyTests(unittest.TestCase):
    def test_custom_policy_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = {
                "create_archives": False,
                "keep_weeks_individual": 52,
                "keep_weeks_mega_pdf": 52,
                "keep_months_archive": 0,
                "hard_size_cap_gb": 100.0,
            }
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (root / "parishes" / "retention_policy.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            old_pdf = _write_file(
                root / "Bulletins" / "current" / "old.pdf",
                content=b"%PDF-1.4",
                age_days=21,
            )
            apply_retention(root, dry_run=False)
            self.assertTrue(old_pdf.exists(), "File within retention window should NOT be pruned")


class RetentionWorkflowTests(unittest.TestCase):
    def test_workflow_does_not_auto_run_after_harvest(self) -> None:
        workflow = Path(".github/workflows/retention.yml").read_text(encoding="utf-8")
        self.assertNotIn("workflow_run:", workflow)
        self.assertIn("archives disabled", workflow.lower())
        self.assertNotIn("zip old", workflow.lower())


if __name__ == "__main__":
    unittest.main()
