"""Probe St Colmcille's Holywood bulletin iframe / PDF URLs."""
from __future__ import annotations

import json
import re
import urllib.request

URLS = [
    "https://www.stcolmcillesholywood.org/bulletins/bulletin-notice-sunday-16th-august-2026/",
    "https://www.stcolmcillesholywood.org/bulletins/",
    "https://www.stcolmcillesholywood.org/wp-json/wp/v2/media?parent=16183",
    "https://www.stcolmcillesholywood.org/wp-json/wp/v2/posts?categories=4&per_page=5",
    "https://www.stcolmcillesholywood.org/wp-json/wp/v2/media?search=bulletin&per_page=10",
]


def fetch(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.status, resp.headers.get("content-type", ""), resp.read()


def main() -> None:
    for url in URLS:
        print("=" * 80)
        print("URL", url)
        try:
            status, ct, body = fetch(url)
        except Exception as exc:
            print("ERR", type(exc).__name__, exc)
            continue
        print("status", status, "ct", ct, "len", len(body))
        text = body.decode("utf-8", "replace")
        if "json" in url:
            print(text[:4000])
            continue
        for pat in ("iframe", "embed", "pdfemb", ".pdf", "viewer", "object", "google"):
            print(pat, text.lower().count(pat.lower()))
        iframes = re.findall(r"<iframe[^>]*>", text, re.I)
        print("IFRAMES", len(iframes))
        for frame in iframes[:20]:
            print(frame[:700])
        pdfs = re.findall(r"https?://[^\s\"'>]+\.pdf[^\s\"'>]*", text, re.I)
        print("PDF URLS", pdfs[:20])
        uploads = re.findall(r"wp-content/uploads/[^\s\"'>]+", text, re.I)
        print("UPLOADS", uploads[:40])
        # data attributes often hide the real PDF
        data_attrs = re.findall(r"data-[a-z0-9_-]+=\"[^\"]{10,200}\"", text, re.I)
        print("DATA ATTRS", data_attrs[:30])


if __name__ == "__main__":
    main()
