"""Probe Errigal news page and dated PDFs. Local junk."""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from datetime import date

from harvester.utils import predicted_dated_upload_urls, rewrite_date_url

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
URLS = [
    "https://www.errigalparish.com/news.html",
    "https://www.errigalparish.com/pdf/160826.pdf",
    "https://www.errigalparish.com/pdf/230826.pdf",
    "https://www.errigalparish.com/pdf/090826.pdf",
    "https://errigalparish.com/pdf/160826.pdf",
]


def fetch(url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            body = resp.read(12)
            rest = resp.read()
            print(f"OK {resp.status} bytes={len(body)+len(rest)} ctype={resp.headers.get('content-type')} {url}")
            print(f"  magic={body!r}")
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} {url} {exc.reason}")
    except Exception as exc:
        print(f"ERR {type(exc).__name__} {url} {exc}")


if __name__ == "__main__":
    example = "https://www.errigalparish.com/pdf/160826.pdf"
    print("REWRITE 23 Aug", rewrite_date_url(example, date(2026, 8, 23)))
    print("PREDICT 16 Aug", predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=2)[:6])
    for url in URLS:
        fetch(url)
