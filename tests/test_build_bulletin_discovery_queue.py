"""Regression tests for repeatable bulletin source discovery and matching."""
from __future__ import annotations

import json

from scripts.build_bulletin_discovery_queue import (
    build_queue, church_id, drive_id, load_seeds, normalise_name, source_type,
)


def _seed(name, url, source="test.txt"):
    return {"name": name, "url": url, "source_type": source_type(url), "source_file": source}


def test_mcn_id_matches_changed_uuid_and_parish_name():
    stale = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/NewsLetter/old.pdf"
    found = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/NewsLetter/new.pdf"
    report = {"target_date": "2026-11-15", "stale_rejected": [
        {"parish": "glenfin-parish", "display_name": "Glenfin", "url": stale}
    ]}
    queue = build_queue([], [_seed("Our Lady of Perpetual Succour, Glenfinn", found)], report)
    assert queue["leads"][0]["status_hint"] == "stale"
    assert queue["leads"][0]["match_method"] == "mcn_church_id"
    assert queue["leads"][0]["matched_parish"] == "glenfin-parish"


def test_drive_id_matches_download_host_and_prioritises_stale():
    shared = "1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa"
    report = {
        "target_date": "2026-11-15",
        "stale_rejected": [{"parish": "kilmacrenan", "url": f"https://drive.usercontent.google.com/download?id={shared}&export=download"}],
        "downloaded": [{"parish": "kilmacrenan", "url": f"https://drive.usercontent.google.com/download?id={shared}&export=download"}],
    }
    queue = build_queue([_seed("Gartan/Termon", f"https://drive.google.com/file/d/{shared}/view")], [], report)
    assert queue["leads"][0]["status_hint"] == "stale"
    assert queue["leads"][0]["match_method"] == "drive_file_id"


def test_unmatched_lead_is_not_claimed_as_a_newly_harvested_bulletin():
    queue = build_queue([_seed("Unknown Parish", "https://example.org/bulletin")], [], {})
    row = queue["leads"][0]
    assert row["status_hint"] == "unmatched"
    assert row["validation"] == "unverified_seed"
    assert row["matched_parish"] is None


def test_duplicate_leads_are_kept_once_and_share_website_gets_no_false_match():
    site = _seed("Barryroe", "https://onefaith.ie/newsletter")
    other = _seed("Clonakilty", "https://onefaith.ie/newsletter")
    queue = build_queue([site, site, other], [], {"target_date": "2026-11-15"})
    assert queue["stats"]["raw_leads"] == 3
    assert queue["stats"]["deduplicated_leads"] == 2
    assert all(x["status_hint"] == "unmatched" for x in queue["leads"])


def test_seed_parser_handles_mcn_dates_and_spaced_docx_urls(tmp_path):
    file = tmp_path / "specialised.txt"
    file.write_text(
        "MCN camera files from 29/10/2026. 40 links.\n"
        "Glenfin  25/10/2026  https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/NewsLetter/a.pdf\n"
        "Claudy  onewebmedia  http://parishofclaudy.com/onewebmedia/NEWSLETTER 25-10-26.docx\n",
        encoding="utf-8",
    )
    rows = load_seeds(file)
    assert len(rows) == 2
    assert rows[0]["name"] == "Glenfin"
    assert rows[0]["source_type"] == "mcn_live"
    assert rows[1]["url"].endswith("NEWSLETTER 25-10-26.docx")
    assert rows[1]["source_type"] == "onewebmedia"


def test_stable_id_parsing():
    assert church_id("https://host/live/Uploads/164/NewsLetter/uuid.pdf") == "164"
    assert drive_id("https://drive.google.com/file/d/1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa/view") == "1KnA8F6t54NmbyeitUGgtfWxN2IqFMDOa"
    assert normalise_name("Gartan/Termon (Kilmacrenan)") == "gartantermon"
