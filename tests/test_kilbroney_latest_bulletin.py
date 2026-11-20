"""Recover Kilbroney's actual homepage 'Latest Bulletin' instead of stale media."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas

from harvester.newsletter_brain import same_sunday_urls
from harvester.replay import _score_http_scrape_pdf_hrefs, _try_http_scrape_newest_pdf

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://kilbroneyparish.com"
CURRENT = BASE + "/wp-content/uploads/2026/11/Bulletin-13.11.26-.pdf"
OLD = BASE + "/wp-content/uploads/2026/10/Bulletin-30.10.26-.pdf"

def test_kilbroney_recipe_uses_live_homepage_instead_of_media_api():
    recipe = json.loads((ROOT / "parishes/recipes/dromore/kilbroney.json").read_text(encoding="utf-8"))
    assert recipe["site_type"] == "http_scrape_newest_pdf"
    assert recipe["start_url"] == BASE + "/"
    assert "Bulletin-" in recipe["href_patterns"]
    assert not any("13.11.26" in str(step) for step in recipe["steps"])

def test_latest_friday_upload_beats_previous_month_file_for_15_nov():
    scored = _score_http_scrape_pdf_hrefs([OLD, CURRENT], date(2026, 11, 15))
    assert same_sunday_urls(scored,date(2026, 11, 15)) == [CURRENT]

def test_homepage_link_fetches_pdf_without_pin(tmp_path):
    pdf = tmp_path / "source.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 720, "KILBRONEY PARISH BULLETIN")
    c.drawString(72, 700, "Thirty-Third Sunday in Ordinary Time | 15th November 2026")
    c.save()
    payload = pdf.read_bytes()
    homepage = f'<html><a href="{CURRENT}">Latest Bulletin</a></html>'
    captured = []
    def fake_fetch(url, **kwargs):
        captured.append(url)
        if url.rstrip("/") == BASE:
            return homepage.encode(), {"content-type":"text/html"}
        if url == CURRENT:
            return payload, {"content-type":"application/pdf"}
        return None
    dest = tmp_path / "harvest.pdf"
    with patch("harvester.replay._fetch_bytes_with_retries", side_effect=fake_fetch):
        found = asyncio.run(_try_http_scrape_newest_pdf(BASE + "/", dest, href_patterns=["Bulletin-", ".pdf"], target_date=date(2026, 11, 15)))
    assert found is not None
    assert found[0] == CURRENT
    assert dest.read_bytes().startswith(b"%PDF")
    assert OLD not in captured
