"""Probe Malin bulletin listing and dated PDFs. Local junk."""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser

from harvester.utils import rewrite_date_url

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
LISTING = "https://malinparish.ie/index.php/bulletin/"
URLS = [
    LISTING,
    "https://malinparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026.pdf",
    "http://malinparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026.pdf",
    "https://malinparish.ie/wp-content/uploads/2026/08/Bulletin-16th-August-2026.pdf",
    "http://malinparish.ie/wp-content/uploads/2026/08/Bulletin-16th-August-2026.pdf",
    "https://malinparish.ie/wp-content/uploads/2026/08/Bulletin-23rd-August-2026.pdf",
    "https://malinparish.ie/wp-json/wp/v2/media?per_page=20",
]


class HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        if ".pdf" in href.lower() or "bulletin" in href.lower():
            self.hrefs.append(href)


def fetch(url: str, max_bytes: int = 80_000) -> tuple[int | None, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
            body = resp.read(max_bytes)
            return resp.status, str(resp.headers.get("content-type") or ""), body
    except urllib.error.HTTPError as exc:
        return exc.code, "", b""
    except Exception as exc:
        print(f"ERR {type(exc).__name__} {url} {exc}")
        return None, "", b""


if __name__ == "__main__":
    example = "http://malinparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026.pdf"
    print("REWRITE 16 Aug", rewrite_date_url(example, date(2026, 8, 16)))
    for url in URLS:
        status, ctype, body = fetch(url, 200_000 if url.endswith(".pdf") else 120_000)
        print(f"{status} {len(body):6} {ctype} {url}")
        if body[:4] == b"%PDF":
            print("  PDF magic ok")
        if "bulletin/" in url and body:
            parser = HrefParser()
            try:
                parser.feed(body.decode("utf-8", errors="ignore"))
            except Exception:
                pass
            for href in parser.hrefs[:25]:
                print("  href", href)
        if "wp/v2/media" in url and body:
            print(body[:800])
