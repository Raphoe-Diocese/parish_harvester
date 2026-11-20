"""Joomla newsletter download recovery for Ballybrack-Killiney."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
import asyncio

from harvester.replay import _score_http_scrape_pdf_hrefs, _try_http_scrape_newest_pdf
from harvester.newsletter_brain import same_sunday_urls

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.ballybrack-killiney-parish.org"
CURRENT = BASE + "/news/routedownload/newsletter-14th-15th-november-2026.html"
PREVIOUS = BASE + "/news/routedownload/newsletter-7th-8th-november-2026.html"


def test_ballybrack_archive_recognises_joomla_pdf_routes():
    scored = _score_http_scrape_pdf_hrefs([PREVIOUS, CURRENT], date(2026, 11, 15))
    assert any(url == CURRENT for _day, url in scored)
    assert same_sunday_urls(scored, date(2026, 11, 15)) == [CURRENT]


def test_recipe_uses_archive_not_pinned_pdf():
    recipe = json.loads((ROOT / "parishes/recipes/dublin/ballybrackkilliney.json").read_text())
    assert recipe["site_type"] == "http_scrape_newest_pdf"
    assert recipe["start_url"] == BASE + "/news.html"
    assert recipe["href_patterns"] == ["/routedownload/"]
    assert recipe["skip"] is False
    assert all("november" not in str(step).lower() for step in recipe["steps"])


def test_actual_joomla_pdf_route_is_used_without_fetching_thank_you(tmp_path):
    from reportlab.pdfgen import canvas
    pdf = tmp_path / "genuine.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 720, "Newsletter 14th & 15th November 2026")
    c.save()
    payload = pdf.read_bytes()
    listing = '<html><a href="/news/routedownload/newsletter-7th-8th-november-2026.html">Download</a><a href="/news/routedownload/newsletter-14th-15th-november-2026.html">Download</a></html>'
    seen = []
    def fake_fetch(url, **kwargs):
        seen.append(url)
        if url.endswith("/news.html"):
            return listing.encode(), {"content-type":"text/html"}
        if "/news/download/" in url:
            return payload, {"content-type":"application/pdf"}
        return None
    dest = tmp_path / "ballybrack.pdf"
    with patch("harvester.replay._fetch_bytes_with_retries", side_effect=fake_fetch):
        result = asyncio.run(_try_http_scrape_newest_pdf(BASE + "/news.html",dest,href_patterns=["/routedownload/"],target_date=date(2026,11,15)))
    assert result is not None
    assert result[0].endswith("/news/download/newsletter-14th-15th-november-2026.html")
    assert dest.read_bytes().startswith(b"%PDF")
    assert not any("/routedownload/" in url for url in seen)
