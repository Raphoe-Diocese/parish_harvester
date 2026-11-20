"""Shared parish newsletters count as one download, while serving many parishes.

Known shared-issue aliases are proven by parish_aliases, not guessed from a
shared hosting domain or superficially similar PDF filename.
"""
from __future__ import annotations

from harvester.report import (
    _recompute_summary,
    merge_diocese_reports,
    reconcile_report_with_recipes,
)


GARTAN_ID = "1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa"
DRIVE = f"https://drive.usercontent.google.com/download?id={GARTAN_ID}&export=download"
VIEW = f"https://drive.google.com/file/d/{GARTAN_ID}/view"


def _report(primary, alias, week="2026-11-15"):
    return {
        "target_date": week,
        "downloaded": [primary, alias],
        "html_links": [], "skipped": [], "failed": [], "stale_rejected": [],
    }


def test_one_shared_drive_bulletin_downloaded_once_with_coverage_retained(tmp_path):
    report = _report(
        {"parish": "drive-1kna8f6t54", "url": DRIVE, "last_pdf_sha256": "a" * 64},
        {"parish": "kilmacrenan", "url": VIEW, "last_pdf_sha256": "a" * 64},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 1
    assert [x["parish"] for x in report["downloaded"]] == ["drive-1kna8f6t54"]
    assert report["shared_download_aliases"][0]["alias"] == "kilmacrenan"
    assert report["shared_download_aliases"][0]["proof"] == "matching_pdf_sha256"
    assert {
        "canonical": "drive-1kna8f6t54",
        "shared_with": ["kilmacrenan"],
        "basis": "known_shared_bulletin_mapping",
    } in report["shared_bulletin_coverage"]
    assert report["alias_downloads_without_canonical"] == []
    # Staging/mega creation recomputes counts; that must not lose the audit.
    _recompute_summary(report)
    assert report["summary"]["downloaded"] == 1
    assert len(report["shared_download_aliases"]) == 1


def test_shared_parish_same_drive_file_id_without_hash_collapses(tmp_path):
    report = _report(
        {"parish": "drive-1kna8f6t54", "url": DRIVE},
        {"parish": "kilmacrenan", "url": VIEW},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 1
    assert report["shared_download_aliases"][0]["proof"] == "same_google_drive_file_id"


def test_two_different_pdfs_from_shared_parish_are_never_silently_erased(tmp_path):
    report = _report(
        {"parish": "drumholm-parish", "url": "https://parish.example.org/a.pdf",
         "last_pdf_sha256": "1" * 64},
        {"parish": "ballintra", "url": "https://parish.example.org/b.pdf",
         "last_pdf_sha256": "2" * 64},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 2
    assert report.get("shared_download_aliases") is None
    assert report["alias_downloads_without_canonical"] == []


def test_conflicting_hashes_veto_even_identical_permanent_url(tmp_path):
    url = "https://example.org/bulletin.pdf"
    report = _report(
        {"parish": "drumholm-parish", "url": url, "last_pdf_sha256": "1" * 64},
        {"parish": "ballintra", "url": url, "last_pdf_sha256": "2" * 64},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 2


def test_conflicting_issue_dates_veto_duplicate_even_same_drive_id(tmp_path):
    report = _report(
        {"parish": "drive-1kna8f6t54", "url": DRIVE, "bulletin_date": "2026-11-15"},
        {"parish": "kilmacrenan", "url": VIEW, "bulletin_date": "2026-11-08"},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 2


def test_identical_pdf_from_unrelated_parishes_is_not_automatically_collapsed(tmp_path):
    report = _report(
        {"parish": "ardara", "url": "https://one.example/a.pdf", "last_pdf_sha256": "a" * 64},
        {"parish": "glencolmcille", "url": "https://other.example/b.pdf", "last_pdf_sha256": "a" * 64},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 2


def test_alias_download_with_missing_canonical_is_flagged_not_invented(tmp_path):
    report = {
        "target_date": "2026-11-15",
        "downloaded": [{"parish": "kilmacrenan", "url": VIEW}],
        "stale_rejected": [{"parish": "drive-1kna8f6t54",
                             "url": "https://another-source.example.org/old.pdf",
                             "bulletin_date": "2026-11-08"}],
        "failed": [], "skipped": [], "html_links": [],
    }
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 1
    assert report["alias_downloads_without_canonical"] == [
        {"alias": "kilmacrenan", "canonical": "drive-1kna8f6t54"}
    ]
    assert report["shared_bulletin_coverage"] == []


def test_previous_week_shared_metadata_does_not_survive_new_harvest(tmp_path):
    report = _report(
        {"parish": "drive-1kna8f6t54", "url": DRIVE},
        {"parish": "kilmacrenan", "url": VIEW},
    )
    reconcile_report_with_recipes(report, parishes_dir=tmp_path)
    assert report["shared_download_aliases"]
    report["target_date"] = "2026-11-22"
    _recompute_summary(report)
    assert "shared_download_aliases" not in report


def test_parallel_diocese_reports_are_deduplicated_after_merge():
    report = _report(
        {"parish": "drumholm-parish", "url": "https://example.org/same.pdf"},
        {"parish": "ballintra", "url": "https://example.org/same.pdf"},
    )
    merged = merge_diocese_reports([report])
    assert merged["summary"]["downloaded"] == 1
    assert merged["downloaded"][0]["parish"] == "drumholm-parish"
    assert merged["shared_bulletin_coverage"][0]["shared_with"] == ["ballintra"]
