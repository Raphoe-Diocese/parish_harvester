"""Proof: newest Tawnawilly PDF bytes + date scoring. Local junk."""
from __future__ import annotations

import ssl
import urllib.request
from datetime import date
from pathlib import Path

from harvester.replay import _is_non_bulletin_url, _score_http_scrape_pdf_hrefs
from harvester.utils import extract_date_from_string, yearless_slug_date

URL = "https://tawnawillyparish.ie/wp-content/uploads/Sunday-23rd-Aug.pdf"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
OUT = Path("_tmp_proof_tawnawilly.pdf")


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
        body = resp.read()
        print("status", resp.status, "ctype", resp.headers.get("content-type"), "bytes", len(body), "magic", body[:5])
    OUT.write_bytes(body)
    print("yearless", yearless_slug_date(URL, 2026, near=date(2026, 8, 16)))
    print("extract", extract_date_from_string(URL))
    hrefs = [
        "https://tawnawillyparish.ie/wp-content/uploads/GDPR-Parish-Bulletin.pdf",
        "https://tawnawillyparish.ie/wp-content/uploads/Sunday-26-July-2026.pdf",
        "https://tawnawillyparish.ie/wp-content/uploads/Sunday-16th-Aug.pdf",
        URL,
    ]
    print("gdpr skip", _is_non_bulletin_url(hrefs[0]))
    print("scored", _score_http_scrape_pdf_hrefs(hrefs, date(2026, 8, 16)))


if __name__ == "__main__":
    main()
