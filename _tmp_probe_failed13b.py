"""Deeper live checks for the 13 Problems-tab parishes. Do not commit."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ParishHarvester/probe"
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read(600_000)
            return r.status, r.headers.get_content_type(), dict(r.headers), data, r.url
    except Exception as exc:
        return 0, f"err:{type(exc).__name__}", {}, str(exc).encode()[:200], url


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[tuple[str, str]] = []
        self._href = ""
        self._buf: list[str] = []
        self.texts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._href = attrs["href"]
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = " ".join("".join(self._buf).split())[:80]
            self.hrefs.append((self._href, text))
            self._href = ""
            self._buf = []

    def handle_data(self, data):
        if self._href:
            self._buf.append(data)
        t = " ".join(data.split())
        if t:
            self.texts.append(t[:120])


def main() -> None:
    from harvester.bulletin_freshness import (
        check_bulletin_freshness,
        extract_bulletin_date,
        extract_bulletin_date_from_text,
    )
    from harvester.liturgical import liturgical_date_from_text
    from harvester.utils import extract_date_from_string, rewrite_date_url

    target = date(2026, 8, 23)
    print("=== DATE PARSE ===")
    for s in [
        "26-08-16pdf.pdf",
        "26-08-23pdf.pdf",
        "230826.pdf",
        "160826.pdf",
        "http://www.holycrossparishbelfast.com/pdf/230826.pdf",
        "https://www.ballymoneyparish.com/media/other/31871/26-08-23pdf.pdf",
        "Sun-28th-June-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/06/Sun-21st-June-26.pdf",
    ]:
        print(s, "->", extract_date_from_string(s), "| freshness", extract_bulletin_date(s), check_bulletin_freshness(s, target).status)

    print("\n=== REWRITE vs 23/08/2026 ===")
    for u in [
        "https://www.ballymoneyparish.com/media/other/31871/26-08-16pdf.pdf",
        "http://www.holycrossparishbelfast.com/pdf/230826.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/06/Sun-21st-June-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/06/Sun-28th-June-26.pdf",
        "https://glenariffeparish.org/wp-content/uploads/2025/04/Easter-Sunday-20th-April-2025.pdf",
        "https://glenariffeparish.org/wp-content/uploads/2026/07/Sixteenth-Sunday-of-Ordinary-Time.pdf",
    ]:
        print(rewrite_date_url(u, target))
        print("  from", u)

    print("\n=== LITURGICAL ===")
    for name in [
        "Twenty-First-Sunday-of-Ordinary-Time.pdf",
        "Sixteenth-Sunday-of-Ordinary-Time.pdf",
        "Easter-Sunday-20th-April-2025.pdf",
    ]:
        print(name, liturgical_date_from_text(name, 2026))

    # Holy Cross PDFs
    print("\n=== HOLY CROSS PDF TEXT ===")
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader
    for name in ("230826.pdf", "160826.pdf", "120726.pdf"):
        url = f"http://www.holycrossparishbelfast.com/pdf/{name}"
        st, ctype, hdrs, data, final = fetch(url)
        print(name, st, ctype, "cl", hdrs.get("Content-Length"), "lm", hdrs.get("Last-Modified"), "n", len(data))
        if st == 200 and data[:4] == b"%PDF":
            path = Path("_tmp_holycross_probe") / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data[:500_000] if len(data) > 500_000 else data)
            # re-fetch full if truncated
            if len(data) >= 500_000:
                st2, _, _, data2, _ = fetch(url)
                if st2 == 200:
                    path.write_bytes(data2)
                    data = data2
            try:
                reader = PdfReader(str(path))
                text = "\n".join((p.extract_text() or "") for p in reader.pages[:2])
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:25]
                print("  pages", len(reader.pages), "heading-date", extract_bulletin_date_from_text(text))
                for ln in lines[:12]:
                    print("  |", ln[:110])
            except Exception as exc:
                print("  pdf-read-err", exc)

    # Ballymoney this week
    print("\n=== BALLYMONEY 26-08-23 ===")
    u = "https://www.ballymoneyparish.com/media/other/31871/26-08-23pdf.pdf"
    st, ctype, hdrs, data, final = fetch(u)
    print(st, ctype, "cl", hdrs.get("Content-Length"), "lm", hdrs.get("Last-Modified"), "magic", data[:5])
    if st == 200 and data[:4] == b"%PDF":
        path = Path("_tmp_holycross_probe") / "ballymoney-260823.pdf"
        path.write_bytes(data)
        try:
            reader = PdfReader(str(path))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:1])
            print("  pages", len(reader.pages), "heading", extract_bulletin_date_from_text(text))
            for ln in [x.strip() for x in text.splitlines() if x.strip()][:10]:
                print("  |", ln[:110])
        except Exception as exc:
            print("  pdf-read-err", exc)

    # Glenariffe Aug PDF
    print("\n=== GLENARIFFE AUG PDF ===")
    u = "https://glenariffeparish.org/wp-content/uploads/2026/08/Twenty-First-Sunday-of-Ordinary-Time.pdf"
    st, ctype, hdrs, data, final = fetch(u)
    print(st, ctype, "cl", hdrs.get("Content-Length"), "lm", hdrs.get("Last-Modified"), "magic", data[:5])
    if st == 200 and data[:4] == b"%PDF":
        path = Path("_tmp_holycross_probe") / "glenariffe-21st.pdf"
        path.write_bytes(data)
        try:
            reader = PdfReader(str(path))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:1])
            print("  pages", len(reader.pages), "heading", extract_bulletin_date_from_text(text))
            for ln in [x.strip() for x in text.splitlines() if x.strip()][:10]:
                print("  |", ln[:110])
        except Exception as exc:
            print("  pdf-read-err", exc)

    # Listing title scans
    print("\n=== LISTING TITLES / WP-JSON ===")
    listings = [
        ("dunsford", "https://www.dunsfordandardglassparish.com/?page_id=623"),
        ("clonleigh", "https://clonleighparish.com/category/newsletter/"),
        ("clonleigh-json", "https://clonleighparish.com/wp-json/wp/v2/posts?per_page=5"),
        ("kincasslagh", "https://www.kincasslagh.ie/?post_type=kbp_bulletins"),
        ("kincasslagh-wwwless", "https://kincasslagh.ie/?post_type=kbp_bulletins"),
        ("stoliver", "https://stoliverplunkettparish.ie/bulletins/"),
        ("stoliver-home", "https://stoliverplunkettparish.ie/"),
        ("stoliver-json", "https://stoliverplunkettparish.ie/wp-json/wp/v2/media?per_page=10"),
        ("hannahstown", "https://www.parishofhannahstown.com/weekly-bulletins"),
        ("stpat-json", "https://www.stpatricksbelfast.org/wp-json/wp/v2/posts?per_page=8"),
        ("stranorlar-current", "https://www.stranorlarparish.ie/current-newsletter/"),
    ]
    for name, url in listings:
        st, ctype, hdrs, data, final = fetch(url)
        print(f"\n{name} {st} {ctype} {final}")
        if st == 0:
            print("  err", data[:160])
            continue
        body = data.decode("utf-8", "replace")
        if "json" in ctype or url.endswith("posts?per_page=5") or "wp-json" in url:
            try:
                js = json.loads(body)
                if isinstance(js, list):
                    for item in js[:6]:
                        print("  post", item.get("date", "")[:10], item.get("slug") or item.get("source_url") or item.get("title"))
                else:
                    print("  json keys", list(js)[:8])
            except Exception as exc:
                print("  json-err", exc, body[:180])
            continue
        p = LinkParser()
        try:
            p.feed(body)
        except Exception:
            pass
        interesting = [
            (h, t)
            for h, t in p.hrefs
            if any(x in (h + t).lower() for x in ("pdf", "bulletin", "sunday", "newsletter", "august", "july", "june", "docx"))
        ]
        for h, t in interesting[:15]:
            print("  ", t[:50], "->", urljoin(url, h)[:140])
        if name == "hannahstown":
            blob = " ".join(p.texts)
            for needle in ("August", "July", "June", "2026", "Bulletin"):
                if needle.lower() in blob.lower():
                    print("  page-has", needle)


if __name__ == "__main__":
    main()
