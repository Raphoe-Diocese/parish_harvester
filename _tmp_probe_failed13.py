"""Live probe of the 13 Problems-tab parishes. Do not invent PDFs."""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ParishHarvesterProbe/1.0"
CTX = ssl.create_default_context()

PDF_RE = re.compile(r"""(?i)href=["']([^"']+\.(?:pdf|docx)[^"']*)["']""")
WP_MEDIA = re.compile(r"/wp-content/uploads/\d{4}/\d{2}/[^\"']+\.pdf", re.I)
DATEISH = re.compile(
    r"(20\d{2}[-_/]?\d{1,2}[-_/]?\d{1,2}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+20\d{2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\s*,?\s*20\d{2}|"
    r"\d{6,8})",
    re.I,
)

TARGETS = [
    ("ballymoneyparish", "https://www.ballymoneyparish.com/"),
    ("bangorparish", "https://www.bangorparish.com/parish-bulletin/"),
    ("clonleighparish", "https://clonleighparish.com/category/newsletter/"),
    ("dunsfordandardglassparish", "https://www.dunsfordandardglassparish.com/?page_id=623"),
    ("glenariffeparish", "https://glenariffeparish.org/whats-on"),
    ("holycrossparishbelfast", "http://www.holycrossparishbelfast.com/parishnews.html"),
    ("kincasslagh", "https://www.kincasslagh.ie/?post_type=kbp_bulletins"),
    ("malinparish", "https://malinparish.ie/index.php/bulletin/"),
    ("parishofhannahstown", "https://www.parishofhannahstown.com/weekly-bulletins"),
    ("saintmalachysparish", "https://www.saintmalachysparish.com/"),
    ("stoliverplunkettparish", "https://stoliverplunkettparish.ie/bulletins/"),
    ("stpatricksbelfast", "https://www.stpatricksbelfast.org/category/weekly-bulletins/"),
    ("stranorlarparish", "https://www.stranorlarparish.ie/newsletter/"),
]

EXTRA_URLS = {
    "holycrossparishbelfast": [
        "http://www.holycrossparishbelfast.com/pdf/230826.pdf",
        "http://www.holycrossparishbelfast.com/pdf/160826.pdf",
    ],
    "malinparish": [
        "https://malinparish.ie/wp-content/uploads/2026/08/Bulletin-23rd-August-2026.pdf",
        "https://malinparish.ie/wp-content/uploads/2026/08/Bulletin-16th-August-2026.pdf",
        "https://malinparish.ie/wp-content/uploads/2026/04/Bulletin-5th-April-2026.pdf",
    ],
    "stoliverplunkettparish": [
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-23rd-August-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-16th-August-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-28th-June-26.pdf",
    ],
    "saintmalachysparish": [
        "https://www.saintmalachysparish.com/documents/bulletin.pdf",
    ],
    "ballymoneyparish": [
        "https://www.ballymoneyparish.com/media/other/31871/26-08-16pdf.pdf",
    ],
    "stranorlarparish": [
        "https://www.stranorlarparish.ie/current-newsletter/",
        "https://www.stranorlarparish.ie/wp-content/uploads/2026/08/23rd-August-2026.pdf",
        "https://www.stranorlarparish.ie/wp-content/uploads/2026/08/16th-August-2026.pdf",
    ],
    "kincasslagh": [
        "https://kincasslagh.ie/app/uploads/2026/08/20260823.pdf",
        "https://kincasslagh.ie/app/uploads/2026/08/20260816.pdf",
        "https://kincasslagh.ie/app/uploads/2026/07/20260705.pdf",
    ],
    "bangorparish": [
        "https://www.bangorparish.com/wp-content/uploads/23-August-2026-NEWSLETTER.pdf",
        "https://www.bangorparish.com/wp-content/uploads/16-August-2026-NEWSLETTER.pdf",
        "https://www.bangorparish.com/wp-content/uploads/14-June-2026-NEWSLETTER.pdf",
    ],
}


def fetch(url: str, timeout: int = 25) -> tuple[int, str, bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            data = resp.read(400_000)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, str(resp.geturl()), data, headers
    except urllib.error.HTTPError as exc:
        body = exc.read(8000) if exc.fp else b""
        return exc.code, url, body, {}
    except Exception as exc:
        return 0, url, str(exc).encode("utf-8", "replace"), {}


def sniff(data: bytes) -> str:
    if data.startswith(b"%PDF"):
        return "pdf"
    low = data[:200].lower()
    if b"<html" in low or b"<!doctype" in low:
        return "html"
    if data[:2] == b"PK":
        return "zip/docx"
    return f"other:{data[:12]!r}"


print("=== LISTING PAGES ===")
found: dict[str, list[str]] = {}
for key, url in TARGETS:
    status, final, data, headers = fetch(url)
    kind = sniff(data)
    print(f"\n{key} listing {status} {kind} {final}")
    if kind != "html":
        found[key] = []
        continue
    html = data.decode("utf-8", "replace")
    hrefs = []
    for m in PDF_RE.findall(html):
        hrefs.append(urljoin(final, m))
    for m in WP_MEDIA.findall(html):
        hrefs.append(urljoin(final, m))
    # unique keep order
    seen = []
    for h in hrefs:
        if h not in seen:
            seen.append(h)
    found[key] = seen[:20]
    for h in seen[:12]:
        dates = DATEISH.findall(h)[:3]
        print("  href", h, dates)
    titles = re.findall(
        r"(?i)(?:newsletter|bulletin|sunday)[^<]{0,80}",
        html,
    )
    for t in titles[:8]:
        t = re.sub(r"\s+", " ", t).strip()
        if DATEISH.search(t) or "2026" in t:
            print("  text", t[:120])

print("\n=== PREDICTED / KNOWN URLS ===")
for key, urls in EXTRA_URLS.items():
    print(f"\n{key}")
    for url in urls:
        status, final, data, headers = fetch(url)
        kind = sniff(data)
        cl = headers.get("content-length") or headers.get("content-type")
        lm = headers.get("last-modified")
        print(f"  {status} {kind} len={len(data)} cl={cl} lm={lm}")
        print(f"    {final}")
        if kind == "pdf":
            # cheap date sniff from first bytes
            try:
                text = data.decode("latin-1", "replace")
            except Exception:
                text = ""
            hits = DATEISH.findall(text)[:8]
            if hits:
                print("    pdf-bytes dates", hits[:8])
