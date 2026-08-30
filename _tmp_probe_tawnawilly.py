"""Probe Tawnawilly listing, PDFs, and wp-json. Local junk — not for GitHub."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from datetime import date

URLS = [
    "https://tawnawillyparish.ie/bulletin/",
    "https://tawnawillyparish.ie/wp-json/wp/v2/media?per_page=20&orderby=date&order=desc",
    "https://tawnawillyparish.ie/wp-content/uploads/Sunday-23rd-August.pdf",
    "https://tawnawillyparish.ie/wp-content/uploads/Sunday-16th-August.pdf",
    "https://tawnawillyparish.ie/wp-content/uploads/Sunday-9th-August.pdf",
    "https://tawnawillyparish.ie/wp-content/uploads/Sunday-2nd-August.pdf",
    "https://tawnawillyparish.ie/wp-content/uploads/Sunday-26th-July.pdf",
    "https://tawnawillyparish.ie/wp-content/uploads/Sunday-28th-June.pdf",
    "https://tawnawillyparish.ie/",
    "http://tawnawillyparish.ie/bulletin/",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def fetch(url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            body = resp.read(800)
            print(f"OK {resp.status} {len(resp.read()) + len(body)}ish {resp.headers.get('content-type','')} {url}")
            print(f"  magic={body[:8]!r} final={resp.geturl()}")
            if b"{" in body[:1] or b"[" in body[:1] or "json" in (resp.headers.get("content-type") or ""):
                with urllib.request.urlopen(req, timeout=20, context=ctx) as resp2:
                    payload = json.loads(resp2.read().decode("utf-8", "replace"))
                if isinstance(payload, list):
                    print(f"  media items={len(payload)}")
                    for item in payload[:12]:
                        src = (item.get("source_url") or "") if isinstance(item, dict) else ""
                        title = ""
                        if isinstance(item, dict) and isinstance(item.get("title"), dict):
                            title = item["title"].get("rendered") or ""
                        print(f"    {src} | {title}")
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} {url} {exc.reason}")
    except Exception as exc:
        print(f"ERR {url} {type(exc).__name__}: {exc}")


def rewrite_check() -> None:
    from harvester.utils import predicted_dated_upload_urls, rewrite_date_url

    example = "https://tawnawillyparish.ie/wp-content/uploads/Sunday-28th-June.pdf"
    print("REWRITE", rewrite_date_url(example, date(2026, 8, 23)))
    print("PREDICT", predicted_dated_upload_urls(example, date(2026, 8, 16), weeks_back=4)[:8])


if __name__ == "__main__":
    rewrite_check()
    for url in URLS:
        fetch(url)
