"""Tests for harvest mega-PDF git conflict handling."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from harvester.mega_pdf_git import (
    continue_git_integration,
    harvest_side_flag,
    is_generated_harvest_output,
    is_generated_mega_pdf,
    is_protected_source_path,
    push_with_mega_conflict_retry,
    rebase_keeping_harvest_megas,
    resolve_harvest_output_conflicts,
    resolve_mega_pdf_conflicts,
    snapshot_harvest_outputs,
    snapshot_mega_pdfs,
)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=mega-test@example.com",
            "-c",
            "user.name=Mega Test",
            *args,
        ],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def _write_pdf(path: Path, marker: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n" + marker + b"\n")


class GeneratedMegaPdfPathTests(unittest.TestCase):
    def test_accepts_repo_and_docs_mega_pdfs(self) -> None:
        self.assertTrue(is_generated_mega_pdf("mega_pdf/derry_mega_bulletin.pdf"))
        self.assertTrue(is_generated_mega_pdf("docs/mega_pdf/raphoe_mega_bulletin.pdf"))
        self.assertTrue(is_generated_mega_pdf("./mega_pdf/down_and_connor_mega_bulletin.pdf"))

    def test_rejects_other_paths(self) -> None:
        self.assertFalse(is_generated_mega_pdf("Bulletins/current/ballycastle.pdf"))
        self.assertFalse(is_generated_mega_pdf("docs/mega_pdf/derry_mega_bulletin.pages.json"))
        self.assertFalse(is_generated_mega_pdf("mega_pdf/readme.txt"))
        self.assertFalse(is_generated_mega_pdf("other/mega_pdf/derry_mega_bulletin.pdf"))


class GeneratedHarvestOutputPathTests(unittest.TestCase):
    def test_accepts_generated_harvest_outputs(self) -> None:
        self.assertTrue(is_generated_harvest_output("mega_pdf/derry_mega_bulletin.pdf"))
        self.assertTrue(is_generated_harvest_output("docs/mega_pdf/raphoe_mega_bulletin.pdf"))
        self.assertTrue(is_generated_harvest_output("docs/mega_pdf/derry.pages.json"))
        self.assertTrue(is_generated_harvest_output("docs/dioceses/derry/index.html"))
        self.assertTrue(
            is_generated_harvest_output("docs/dioceses/down-and-connor/index.html")
        )
        self.assertTrue(is_generated_harvest_output("docs/parishes/bangorparish/index.html"))
        self.assertTrue(is_generated_harvest_output("docs/index.html"))
        self.assertTrue(is_generated_harvest_output("docs/manifest.json"))
        self.assertTrue(is_generated_harvest_output("Bulletins/report.json"))
        self.assertTrue(is_generated_harvest_output("parishes/parish_status.json"))
        self.assertTrue(is_generated_harvest_output("parish_status.json"))
        self.assertTrue(is_generated_harvest_output("Bulletins/current/bangorparish.pdf"))

    def test_rejects_recipes_and_harvester_source(self) -> None:
        self.assertTrue(is_protected_source_path("parishes/recipes/raphoe/bangorparish.json"))
        self.assertTrue(is_protected_source_path("harvester/fetcher.py"))
        self.assertFalse(is_generated_harvest_output("parishes/recipes/raphoe/foo.json"))
        self.assertFalse(is_generated_harvest_output("harvester/mega_pdf_git.py"))
        self.assertFalse(is_generated_harvest_output("tests/test_mega_pdf_git.py"))
        self.assertFalse(is_generated_harvest_output("extension/sidepanel.js"))
        self.assertFalse(is_generated_harvest_output(".github/workflows/harvest.yml"))
        self.assertFalse(is_generated_harvest_output("notes.txt"))


class MegaPdfGitConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-b", "main")
        _git(self.root, "config", "user.email", "mega-test@example.com")
        _git(self.root, "config", "user.name", "Mega Test")
        (self.root / "README").write_text("base\n", encoding="utf-8")
        _git(self.root, "add", "README")
        _git(self.root, "commit", "-m", "base")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _commit_pdfs(self, marker: bytes, message: str, *, docs: bool = False) -> None:
        _write_pdf(self.root / "mega_pdf" / "derry_mega_bulletin.pdf", marker)
        _write_pdf(self.root / "mega_pdf" / "raphoe_mega_bulletin.pdf", marker)
        if docs:
            _write_pdf(self.root / "docs" / "mega_pdf" / "derry_mega_bulletin.pdf", marker)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", message)

    def test_rebase_add_add_keeps_harvest_megas(self) -> None:
        # Same history as the failed Sunday harvest: both sides added megas.
        _git(self.root, "checkout", "-b", "harvest")
        self._commit_pdfs(b"HARVEST-NEW", "harvest megas", docs=True)

        _git(self.root, "checkout", "main")
        self._commit_pdfs(b"MAIN-OLD", "main megas", docs=True)

        _git(self.root, "checkout", "harvest")
        rebase = _git(self.root, "rebase", "main", check=False)
        self.assertNotEqual(rebase.returncode, 0, rebase.stderr)
        self.assertIn("CONFLICT (add/add)", rebase.stdout + rebase.stderr)
        self.assertEqual(harvest_side_flag(self.root), "--theirs")

        resolved, leftover = resolve_mega_pdf_conflicts(self.root)
        self.assertEqual(leftover, [])
        self.assertIn("mega_pdf/derry_mega_bulletin.pdf", resolved)
        self.assertIn("docs/mega_pdf/derry_mega_bulletin.pdf", resolved)

        continue_git_integration(self.root)

        derry = (self.root / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes()
        docs_derry = (self.root / "docs" / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes()
        self.assertIn(b"HARVEST-NEW", derry)
        self.assertNotIn(b"MAIN-OLD", derry)
        self.assertIn(b"HARVEST-NEW", docs_derry)

    def test_rebase_helper_restores_snapshot_on_add_add(self) -> None:
        _git(self.root, "checkout", "-b", "harvest")
        self._commit_pdfs(b"HARVEST-NEW", "harvest megas")

        _git(self.root, "checkout", "main")
        self._commit_pdfs(b"MAIN-OLD", "main megas")

        _git(self.root, "checkout", "harvest")
        rebase_keeping_harvest_megas(self.root, "main")

        derry = (self.root / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes()
        self.assertIn(b"HARVEST-NEW", derry)
        self.assertNotIn(b"MAIN-OLD", derry)
        status = _git(self.root, "status", "--porcelain")
        self.assertEqual(status.stdout.strip(), "")

    def test_merge_add_add_keeps_harvest_ours(self) -> None:
        _git(self.root, "checkout", "-b", "harvest")
        self._commit_pdfs(b"HARVEST-NEW", "harvest megas")

        _git(self.root, "checkout", "main")
        self._commit_pdfs(b"MAIN-OLD", "main megas")

        _git(self.root, "checkout", "harvest")
        merge = _git(self.root, "merge", "main", check=False)
        self.assertNotEqual(merge.returncode, 0)
        self.assertEqual(harvest_side_flag(self.root), "--ours")

        resolved, leftover = resolve_mega_pdf_conflicts(self.root)
        self.assertEqual(leftover, [])
        self.assertTrue(resolved)
        _git(self.root, "commit", "--no-edit")

        derry = (self.root / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes()
        self.assertIn(b"HARVEST-NEW", derry)

    def test_modify_modify_keeps_harvest_megas(self) -> None:
        self._commit_pdfs(b"SHARED", "shared megas")
        _git(self.root, "checkout", "-b", "harvest")
        self._commit_pdfs(b"HARVEST-NEW", "harvest rewrite")

        _git(self.root, "checkout", "main")
        self._commit_pdfs(b"MAIN-OLD", "main rewrite")

        _git(self.root, "checkout", "harvest")
        rebase_keeping_harvest_megas(self.root, "main")
        derry = (self.root / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes()
        self.assertIn(b"HARVEST-NEW", derry)

    def test_non_mega_conflicts_are_left_for_a_human(self) -> None:
        _git(self.root, "checkout", "-b", "harvest")
        (self.root / "notes.txt").write_text("harvest notes\n", encoding="utf-8")
        self._commit_pdfs(b"HARVEST-NEW", "harvest both")

        _git(self.root, "checkout", "main")
        (self.root / "notes.txt").write_text("main notes\n", encoding="utf-8")
        self._commit_pdfs(b"MAIN-OLD", "main both")

        _git(self.root, "checkout", "harvest")
        with self.assertRaises(RuntimeError) as ctx:
            rebase_keeping_harvest_megas(self.root, "main")
        self.assertIn("notes.txt", str(ctx.exception))

    def test_snapshot_copies_both_mega_trees(self) -> None:
        _write_pdf(self.root / "mega_pdf" / "derry_mega_bulletin.pdf", b"A")
        _write_pdf(self.root / "docs" / "mega_pdf" / "derry_mega_bulletin.pdf", b"B")
        dest = self.root / "snap"
        copied = snapshot_mega_pdfs(self.root, dest)
        self.assertEqual(
            set(copied),
            {
                "mega_pdf/derry_mega_bulletin.pdf",
                "docs/mega_pdf/derry_mega_bulletin.pdf",
            },
        )
        self.assertIn(b"A", (dest / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes())
        self.assertIn(b"B", (dest / "docs" / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes())

    def _commit_diocese_pages(self, marker: str, message: str) -> None:
        for diocese in ("derry", "down-and-connor"):
            path = self.root / "docs" / "dioceses" / diocese / "index.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"<html>{marker}</html>\n", encoding="utf-8")
        report = self.root / "Bulletins" / "report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(f'{{"marker": "{marker}"}}\n', encoding="utf-8")
        status = self.root / "parishes" / "parish_status.json"
        status.parent.mkdir(parents=True, exist_ok=True)
        status.write_text(f'{{"marker": "{marker}"}}\n', encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-m", message)

    def test_rebase_content_conflict_keeps_harvest_diocese_pages(self) -> None:
        # Same failure as run 32384891762: both sides edited diocese HTML.
        self._commit_diocese_pages("SHARED", "shared pages")
        _git(self.root, "checkout", "-b", "harvest")
        self._commit_diocese_pages("HARVEST-NEW", "harvest pages")

        _git(self.root, "checkout", "main")
        self._commit_diocese_pages("MAIN-OLD", "main pages")

        _git(self.root, "checkout", "harvest")
        rebase = _git(self.root, "rebase", "main", check=False)
        self.assertNotEqual(rebase.returncode, 0, rebase.stderr)
        combined = rebase.stdout + rebase.stderr
        self.assertIn("docs/dioceses/derry/index.html", combined)
        self.assertIn("docs/dioceses/down-and-connor/index.html", combined)

        resolved, leftover = resolve_harvest_output_conflicts(self.root)
        self.assertEqual(leftover, [])
        self.assertIn("docs/dioceses/derry/index.html", resolved)
        self.assertIn("docs/dioceses/down-and-connor/index.html", resolved)
        self.assertIn("Bulletins/report.json", resolved)
        self.assertIn("parishes/parish_status.json", resolved)

        continue_git_integration(self.root)
        derry = (self.root / "docs" / "dioceses" / "derry" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("HARVEST-NEW", derry)
        self.assertNotIn("MAIN-OLD", derry)

    def test_rebase_helper_keeps_diocese_pages_from_snapshot(self) -> None:
        self._commit_diocese_pages("SHARED", "shared pages")
        _git(self.root, "checkout", "-b", "harvest")
        self._commit_diocese_pages("HARVEST-NEW", "harvest pages")

        _git(self.root, "checkout", "main")
        self._commit_diocese_pages("MAIN-OLD", "main pages")

        _git(self.root, "checkout", "harvest")
        rebase_keeping_harvest_megas(self.root, "main")

        derry = (self.root / "docs" / "dioceses" / "derry" / "index.html").read_text(
            encoding="utf-8"
        )
        report = (self.root / "Bulletins" / "report.json").read_text(encoding="utf-8")
        self.assertIn("HARVEST-NEW", derry)
        self.assertIn("HARVEST-NEW", report)
        self.assertNotIn("MAIN-OLD", derry)

    def test_recipe_conflicts_are_not_auto_resolved(self) -> None:
        _git(self.root, "checkout", "-b", "harvest")
        recipe = self.root / "parishes" / "recipes" / "raphoe" / "bangorparish.json"
        recipe.parent.mkdir(parents=True, exist_ok=True)
        recipe.write_text('{"from": "harvest"}\n', encoding="utf-8")
        self._commit_diocese_pages("HARVEST-NEW", "harvest recipe+pages")

        _git(self.root, "checkout", "main")
        recipe = self.root / "parishes" / "recipes" / "raphoe" / "bangorparish.json"
        recipe.parent.mkdir(parents=True, exist_ok=True)
        recipe.write_text('{"from": "main"}\n', encoding="utf-8")
        self._commit_diocese_pages("MAIN-OLD", "main recipe+pages")

        _git(self.root, "checkout", "harvest")
        with self.assertRaises(RuntimeError) as ctx:
            rebase_keeping_harvest_megas(self.root, "main")
        self.assertIn("parishes/recipes/raphoe/bangorparish.json", str(ctx.exception))

    def test_snapshot_includes_diocese_pages_and_status(self) -> None:
        path = self.root / "docs" / "dioceses" / "derry" / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html>HARVEST</html>\n", encoding="utf-8")
        report = self.root / "Bulletins" / "report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text('{"ok": true}\n', encoding="utf-8")
        dest = self.root / "snap"
        copied = snapshot_harvest_outputs(self.root, dest)
        self.assertIn("docs/dioceses/derry/index.html", copied)
        self.assertIn("Bulletins/report.json", copied)
        self.assertIn(
            "HARVEST",
            (dest / "docs" / "dioceses" / "derry" / "index.html").read_text(
                encoding="utf-8"
            ),
        )


class MegaPdfPushRetryTests(unittest.TestCase):
    def test_push_rebases_over_remote_add_add_and_keeps_harvest(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            root = Path(tmp.name)
            bare = root / "remote.git"
            harvest = root / "harvest"
            other = root / "other"

            seed = root / "seed"
            seed.mkdir()
            _git(seed, "init", "-b", "main")
            _git(seed, "config", "user.email", "mega-test@example.com")
            _git(seed, "config", "user.name", "Mega Test")
            (seed / "README").write_text("base\n", encoding="utf-8")
            _git(seed, "add", "README")
            _git(seed, "commit", "-m", "base")
            _git(root, "clone", "--bare", str(seed), str(bare))
            _git(root, "clone", str(bare), str(harvest))
            _git(harvest, "config", "user.email", "mega-test@example.com")
            _git(harvest, "config", "user.name", "Mega Test")

            _git(root, "clone", str(bare), str(other))
            _git(other, "config", "user.email", "mega-test@example.com")
            _git(other, "config", "user.name", "Mega Test")
            _write_pdf(other / "mega_pdf" / "derry_mega_bulletin.pdf", b"MAIN-OLD")
            _git(other, "add", "-A")
            _git(other, "commit", "-m", "main megas")
            _git(other, "push", "origin", "HEAD:main")

            _write_pdf(harvest / "mega_pdf" / "derry_mega_bulletin.pdf", b"HARVEST-NEW")
            _git(harvest, "add", "-A")
            _git(harvest, "commit", "-m", "harvest megas")

            push_with_mega_conflict_retry(harvest, remote="origin", branch="main", attempts=3)

            pulled = root / "verify"
            _git(root, "clone", str(bare), str(pulled))
            data = (pulled / "mega_pdf" / "derry_mega_bulletin.pdf").read_bytes()
            self.assertIn(b"HARVEST-NEW", data)
            self.assertNotIn(b"MAIN-OLD", data)
        finally:
            tmp.cleanup()


class HarvestWorkflowMegaPushTests(unittest.TestCase):
    def test_workflow_calls_python_push_helper_and_keeps_mega_on(self) -> None:
        workflow = (
            Path(__file__).resolve().parent.parent
            / ".github"
            / "workflows"
            / "harvest.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("scripts/push_harvest_results.py", workflow)
        self.assertIn('HARVEST_MEGA_PDF: "1"', workflow)
        self.assertIn("git add -f mega_pdf/*_mega_bulletin.pdf", workflow)
        self.assertIn("git add -f docs/mega_pdf/*_mega_bulletin.pdf", workflow)
        self.assertIn("docs/dioceses/", workflow)
        self.assertIn("cron: '0 9 * * 0'", workflow)
        self.assertNotIn("HARVEST_MEGA_PDF: \"0\"", workflow)
