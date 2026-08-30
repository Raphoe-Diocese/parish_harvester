import re
import urllib.request
from datetime import date
from pathlib import Path

from harvester.bulletin_freshness import check_bulletin_freshness, extract_bulletin_date
from harvester.replay import (
    _is_non_bulletin_url,
    _score_http_scrape_pdf_hrefs,
    liturgical_date_from_text,
)
from harvester.utils import extract_date_from_string

UA = "Mozilla/5.0 (compatible; ParishHarvester/1.0)"
THIS = "https://ballymenaparish.org/wp-content/uploads/2026/08/23.8.26-A4-21st-Sunday.pdf"
LAST = "https://ballymenaparish.org/wp-content/uploads/2026/08/16.8.26-20th-Sunday.pdf"
WEDDING = "https://ballymenaparish.org/wp-content/uploads/2025/01/Wedding-Parish.pdf"
LISTING = "https://ballymenaparish.org/bulletin-and-parish-documents/"


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, dict(resp.headers), resp.read()


print("=== LISTING ===")
status, headers, body = get(LISTING)
html = body.decode("utf-8", errors="ignore")
print("status", status, "bytes", len(body), "ct", headers.get("Content-Type"))
hrefs = re.findall(r"""href=["']([^"']+)["']""", html, flags=re.I)
pdfs = [item for item in hrefs if ".pdf" in item.lower()]
print("pdf hrefs:")
for item in pdfs:
    print(" ", item)
for needle in (
    "Wedding",
    "23.8.26",
    "16.8.26",
    "filebird",
    "folder",
    "DownloadFile",
    "wp-content/uploads",
):
    print(f"contains {needle!r}:", needle.lower() in html.lower())

print()
print("=== THIS WEEK PDF ===")
status, headers, body = get(THIS)
print("status", status, "bytes", len(body), "ct", headers.get("Content-Type"))
print("magic", body[:8])
print("is pdf", body.startswith(b"%PDF"))
out = Path("_tmp_proof_ballymena.pdf")
out.write_bytes(body)
print("saved", out, out.stat().st_size)

print()
print("=== LAST WEEK PDF HEAD ===")
status, headers, body = get(LAST)
print("status", status, "bytes", len(body), "ct", headers.get("Content-Type"), "magic", body[:5])

print()
print("wedding non-bulletin", _is_non_bulletin_url(WEDDING))
print("this week extract_date_from_string", extract_date_from_string(THIS))
print("this week extract_bulletin_date", extract_bulletin_date(THIS))
print("this week liturgical", liturgical_date_from_text(THIS, 2026))
print("last week extract_bulletin_date", extract_bulletin_date(LAST))
print("freshness this vs 16 Aug", check_bulletin_freshness(THIS, date(2026, 8, 16)))
print("freshness this vs 23 Aug", check_bulletin_freshness(THIS, date(2026, 8, 23)))
scored = _score_http_scrape_pdf_hrefs([THIS, LAST, WEDDING], date(2026, 8, 16))
print("scored", scored)
if scored:
    print("best", max(scored))
