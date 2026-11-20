"""Donaghmore's real dated homepage bulletin, without weekly PDF pins."""
from __future__ import annotations
import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import patch
from reportlab.pdfgen import canvas

from harvester.replay import _score_http_scrape_pdf_hrefs, _try_http_scrape_newest_pdf
from harvester.newsletter_brain import same_sunday_urls
from harvester.bulletin_freshness import check_bulletin_freshness

BASE="https://donaghmoreparish.org/"
NOV8=BASE+"wp-content/uploads/2026/11/Donaghmore-Bulletin-8th-November-2026.pdf"
NOV15=BASE+"wp-content/uploads/2026/11/Donaghmore-Bulletin-15th-November-2026.pdf"

def test_15_nov_pdf_beats_old_pdf_when_both_are_present():
    scored=_score_http_scrape_pdf_hrefs([NOV8,NOV15],date(2026,11,15))
    assert same_sunday_urls(scored,date(2026,11,15)) == [NOV15]
    assert check_bulletin_freshness(NOV8,date(2026,11,15)).status=="stale"

def test_current_homepage_latest_bulletin_pdf_is_downloaded(tmp_path):
    original=tmp_path/"original.pdf"
    c=canvas.Canvas(str(original));c.drawString(72,710,"DONAGHMORE PARISH BULLETIN 15TH NOVEMBER 2026");c.showPage();c.save()
    pdf_bytes=original.read_bytes()
    page=f'<html><a href="{NOV15}">Parish Weekly Bulletin</a></html>'
    urls=[]
    def fake_get(url,**kwargs):
        urls.append(url)
        if url.rstrip("/")==BASE.rstrip("/"):return page.encode(),{"content-type":"text/html"}
        if url==NOV15:return pdf_bytes,{"content-type":"application/pdf"}
        return None
    dest=tmp_path/"harvest.pdf"
    with patch("harvester.replay._fetch_bytes_with_retries",side_effect=fake_get):
        found=asyncio.run(_try_http_scrape_newest_pdf(BASE,dest,href_patterns=["Donaghmore-Bulletin-"],target_date=date(2026,11,15)))
    assert found is not None and found[0]==NOV15
    assert dest.read_bytes().startswith(b"%PDF")
    assert NOV8 not in urls
