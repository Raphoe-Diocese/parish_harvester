"""SSL-insecure recheck for cert-expired parish sites. Do not commit."""
from __future__ import annotations

import json
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ParishHarvester/probe"
CTX = ssl._create_unverified_context()


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[tuple[str, str]] = []
        self._href = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._href = attrs["href"]
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            text = " ".join("".join(self._buf).split())[:90]
            self.hrefs.append((self._href, text))
            self._href = ""
            self._buf = []

    def handle_data(self, data):
        if self._href:
            self._buf.append(data)


def fetch(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read(800_000)
            return r.status, r.headers.get_content_type(), dict(r.headers), data, r.url
    except Exception as exc:
        return 0, type(exc).__name__, {}, str(exc).encode()[:240], url


def show_links(name: str, url: str, data: bytes) -> None:
    p = LinkParser()
    try:
        p.feed(data.decode("utf-8", "replace"))
    except Exception as exc:
        print(name, "parse-err", exc)
        return
    print(f"\n=== {name} links ===")
    for h, t in p.hrefs:
        blob = (h + " " + t).lower()
        if any(x in blob for x in ("pdf", "bulletin", "sunday", "newsletter", "august", "july", "2026")):
            print(" ", t[:60], "->", urljoin(url, h)[:160])


def main() -> None:
    pages = [
        ("clonleigh", "https://clonleighparish.com/category/newsletter/"),
        ("clonleigh-json", "https://clonleighparish.com/wp-json/wp/v2/posts?per_page=6"),
        ("kincasslagh", "https://www.kincasslagh.ie/?post_type=kbp_bulletins"),
        ("stoliver", "https://stoliverplunkettparish.ie/bulletins/"),
        ("stoliver-json", "https://stoliverplunkettparish.ie/wp-json/wp/v2/media?per_page=15&search=Sun"),
    ]
    for name, url in pages:
        st, ctype, hdrs, data, final = fetch(url)
        print(f"\n{name} {st} {ctype} {final} cl={hdrs.get('Content-Length')} lm={hdrs.get('Last-Modified')}")
        if st == 0:
            print(" err", data[:200])
            continue
        if "json" in ctype:
            try:
                js = json.loads(data.decode("utf-8", "replace"))
                if isinstance(js, list):
                    for item in js[:10]:
                        title = item.get("slug") or ""
                        if isinstance(item.get("title"), dict):
                            title = item["title"].get("rendered", title)
                        src = item.get("source_url") or item.get("link")
                        print(" ", item.get("date", "")[:10], title, src)
                else:
                    print(" keys", list(js)[:8])
            except Exception as exc:
                print(" json-err", exc, data[:180])
        else:
            show_links(name, url, data)

    print("\n=== predicted St Oliver files ===")
    guesses = [
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-23rd-August-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-16th-August-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-9th-August-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/08/Sun-2nd-August-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/07/Sun-26th-July-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/06/Sun-28th-June-26.pdf",
        "https://stoliverplunkettparish.ie/wp-content/uploads/2026/06/Sun-21st-June-26.pdf",
        "https://kincasslagh.ie/app/uploads/2026/08/20260823.pdf",
        "https://kincasslagh.ie/app/uploads/2026/08/20260816.pdf",
        "https://kincasslagh.ie/app/uploads/2026/07/20260705.pdf",
    ]
    for url in guesses:
        st, ctype, hdrs, data, final = fetch(url)
        print(st, ctype, "cl", hdrs.get("Content-Length"), "lm", hdrs.get("Last-Modified"), "magic", data[:5], url.rsplit("/", 2)[-2] + "/" + url.rsplit("/", 1)[-1])

    # Full Ballymoney this-week PDF
    print("\n=== BALLYMONEY FULL ===")
    url = "https://www.ballymoneyparish.com/media/other/31871/26-08-23pdf.pdf"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40, context=ssl.create_default_context()) as r:
        data = r.read()
        print("status", r.status, "len", len(data), "lm", r.headers.get("Last-Modified"))
    path = "_tmp_holycross_probe/ballymoney-260823.pdf"
    open(path, "wb").write(data)
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader
    reader = PdfReader(path)
    text = "\n".join((p.extract_text() or "") for p in reader.pages[:1])
    print("pages", len(reader.pages))
    for ln in [x.strip() for x in text.splitlines() if x.strip()][:15]:
        print(" |", ln[:120])


if __name__ == "__main__":
    main()
