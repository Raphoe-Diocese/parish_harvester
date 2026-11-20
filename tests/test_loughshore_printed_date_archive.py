"""Loughshore's WordPress archive links to PDF-response permalinks without .pdf."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import patch

from reportlab.pdfgen import canvas
from harvester.replay import _try_archive_pdf_with_printed_date
from harvester.bulletin_freshness import check_bulletin_freshness, heading_date_in_pdf_bytes

BASE = "https://www.loughshoreparishes.org"
LISTING = BASE + "/sunday-bulletin/"
NOV22 = BASE + "/sunday-bulletin/our-lord-jesus-christ-king-of-the-universe/"
NOV15 = BASE + "/sunday-bulletin/33rd-sunday-in-ordinary-time-3/"

def pdf_bytes(path: Path, issue: date) -> bytes:
    c=canvas.Canvas(str(path))
    c.drawString(72,735,"THE LOUGHSHORE PARISHES")
    c.drawString(72,710, f"{issue.day} November 2026 - Sunday Parish Bulletin")
    c.drawString(72,685,"MASS TIMES & SERVICES")
    c.showPage()
    c.save()
    return path.read_bytes()

def test_loughshore_printed_issue_date_from_pdf_is_required(tmp_path):
    nov22=pdf_bytes(tmp_path/"nov22.pdf",date(2026,11,22))
    nov15=pdf_bytes(tmp_path/"nov15.pdf",date(2026,11,15))
    assert heading_date_in_pdf_bytes(nov22,target=date(2026,11,22))==date(2026,11,22)
    assert heading_date_in_pdf_bytes(nov15,target=date(2026,11,15))==date(2026,11,15)

def test_archive_picks_exact_sunday_not_newer_or_old_2025_twin(tmp_path):
    body22=pdf_bytes(tmp_path/"22.pdf",date(2026,11,22))
    body15=pdf_bytes(tmp_path/"15.pdf",date(2026,11,15))
    listing=(
        '<html><a href="/sunday-bulletin/">Sunday Bulletin</a>'
        '<a href="/sunday-bulletin/our-lord-jesus-christ-king-of-the-universe/">Our Lord Jesus Christ</a> – 22 November 2026'
        '<a href="/sunday-bulletin/33rd-sunday-in-ordinary-time-3/">33rd Sunday</a> – 15 November 2026'
        '</html>'
    )
    def fake_fetch(url,**kwargs):
        if url==LISTING:return listing.encode(),{"content-type":"text/html"}
        if url==NOV22:return body22,{"content-type":"application/pdf"}
        if url==NOV15:return body15,{"content-type":"application/pdf"}
        return None
    for target,expected in [(date(2026,11,22),NOV22),(date(2026,11,15),NOV15)]:
        dest=tmp_path/f"{target}.pdf"
        with patch("harvester.replay._fetch_bytes_with_retries",side_effect=fake_fetch):
            found=asyncio.run(_try_archive_pdf_with_printed_date(LISTING,dest,target_date=target,href_patterns=["/sunday-bulletin/"]))
        assert found is not None
        assert found[0].startswith(expected)
        assert "bulletin_date="+target.isoformat() in found[0]
        assert check_bulletin_freshness(found[0],target).status=="fresh"
        assert dest.read_bytes().startswith(b"%PDF")

def test_old_only_archive_does_not_forge_a_new_sunday(tmp_path):
    body15=pdf_bytes(tmp_path/"15.pdf",date(2026,11,15))
    listing='<html><a href="/sunday-bulletin/33rd-sunday-in-ordinary-time-3/">33rd Sunday</a> – 15 November 2026</html>'
    def fake_fetch(url,**kwargs):
        if url==LISTING:return listing.encode(),{"content-type":"text/html"}
        if url==NOV15:return body15,{"content-type":"application/pdf"}
        return None
    dest=tmp_path/"missing.pdf"
    with patch("harvester.replay._fetch_bytes_with_retries",side_effect=fake_fetch):
        found=asyncio.run(_try_archive_pdf_with_printed_date(LISTING,dest,target_date=date(2026,11,22),href_patterns=["/sunday-bulletin/"]))
    assert found is None
    assert not dest.exists()
