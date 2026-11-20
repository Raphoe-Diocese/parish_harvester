"""Regression coverage for permanent-link bulletin freshness.

A changed PDF at the same URL and with the same byte length must be
distinguishable from the prior week's download.
"""
from datetime import date
from types import SimpleNamespace

from harvester import bulletin_freshness as freshness


def test_permanent_url_changed_bytes_not_marked_unchanged(tmp_path, monkeypatch):
    old = tmp_path / "old.pdf"
    new = tmp_path / "new.pdf"
    old.write_bytes(b"%PDF-1.4\nBulletin A\n")
    new.write_bytes(b"%PDF-1.4\nBulletin B\n")
    assert old.stat().st_size == new.stat().st_size

    monkeypatch.setattr(freshness, "_parish_status_row", lambda key: {
        "last_pdf_week": "2026-11-08",
        "last_pdf_sha256": freshness.pdf_sha256(old),
    })
    monkeypatch.setattr(freshness, "previous_harvest_url", lambda key: "https://example.org/bulletin")
    monkeypatch.setattr(freshness, "previous_harvest_file_bytes", lambda key: old.stat().st_size)
    monkeypatch.setattr(freshness, "pdf_date_before_harvest_week", lambda path, target: None)
    monkeypatch.setattr(freshness, "pdf_body_heading_verdict", lambda path, target: None)
    result = SimpleNamespace(url="https://example.org/bulletin", file_path=new, key="newtownkilleaparish")
    verdict = freshness.freshness_verdict_for_ok_result(result, date(2026, 11, 15))
    assert verdict.reason != "unchanged_pdf_from_prior_week"
    assert verdict.status != "stale"
