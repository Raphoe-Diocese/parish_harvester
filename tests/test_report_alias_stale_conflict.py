"""Never count one stale Drive file as both fresh and stale via an alias."""
from __future__ import annotations

from copy import deepcopy

from harvester.report import (
    merge_diocese_reports,
    merge_parish_report_rows,
    reconcile_report_with_recipes,
    suppress_unverified_alias_successes,
)


DRIVE_URL = (
    "https://drive.usercontent.google.com/download?"
    "id=1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa&export=download"
)


def _same_source_report() -> dict:
    return {
        "target_date": "2026-11-15",
        "downloaded": [
            {
                "parish": "kilmacrenan",
                "display_name": "Gartan/Termon (Kilmacrenan)",
                "url": DRIVE_URL,
                "file": "kilmacrenan.pdf",
            }
        ],
        "stale_rejected": [
            {
                "parish": "drive-1kna8f6t54",
                "display_name": "Gartan/Termon (Kilmacrenan)",
                "url": DRIVE_URL,
                "bulletin_date": "2026-11-08",
                "reason": "date_behind_of_target",
            }
        ],
        "failed": [],
        "skipped": [],
        "html_links": [],
    }


def test_canonical_stale_file_not_counted_again_as_undated_alias_success(tmp_path):
    report = reconcile_report_with_recipes(_same_source_report(), parishes_dir=tmp_path)
    assert report["summary"]["downloaded"] == 0
    assert report["summary"]["stale_rejected"] == 1
    assert report["downloaded"] == []
    assert report["alias_conflicts"] == [{
        "alias": "kilmacrenan",
        "canonical": "drive-1kna8f6t54",
        "reason": "same_source_as_proven_stale_canonical_no_fresh_issue_date",
        "url": DRIVE_URL,
    }]


def test_current_dated_alias_not_erased_even_if_canonical_was_stale():
    report = _same_source_report()
    report["downloaded"][0]["bulletin_date"] = "2026-11-15"
    suppress_unverified_alias_successes(report)
    assert len(report["downloaded"]) == 1
    assert not report.get("alias_conflicts")


def test_unrelated_source_maintained_even_if_parish_alias():
    report = _same_source_report()
    report["downloaded"][0]["url"] = "https://another.example.org/current-week.pdf"
    suppress_unverified_alias_successes(report)
    assert len(report["downloaded"]) == 1


def test_same_document_detected_across_google_drive_url_formats():
    report = _same_source_report()
    report["downloaded"][0]["url"] = (
        "https://drive.google.com/file/d/"
        "1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa/view"
    )
    suppress_unverified_alias_successes(report)
    assert report["downloaded"] == []
    assert len(report["alias_conflicts"]) == 1


def test_unrelated_failed_canonical_does_not_suppress_alias_download():
    report = _same_source_report()
    report["failed"] = report.pop("stale_rejected")
    suppress_unverified_alias_successes(report)
    assert len(report["downloaded"]) == 1


def test_merged_reports_do_not_restore_undated_false_success():
    old = _same_source_report()
    mine = deepcopy(old)
    mine["downloaded"] = []
    mine["stale_rejected"] = []
    assert merge_diocese_reports([old])["summary"]["downloaded"] == 0
    assert merge_parish_report_rows(old, mine, {"unrelated-key"})["summary"]["downloaded"] == 0


def test_other_parish_untouched():
    report = _same_source_report()
    report["downloaded"].append({
        "parish": "ardara",
        "url": "https://ardara.ie/current-bulletin.pdf",
        "bulletin_date": "2026-11-15",
    })
    suppress_unverified_alias_successes(report)
    assert [x["parish"] for x in report["downloaded"]] == ["ardara"]
