# -*- coding: utf-8 -*-
import json
import re
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
        return r.geturl(), r.status, r.headers.get("content-type", ""), r.read()


class A(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.items = []
        self._h = None
        self._t = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self._h = urljoin(self.base, d["href"].strip())
            self._t = ""

    def handle_data(self, data):
        if self._h is not None:
            self._t += data

    def handle_endtag(self, tag):
        if tag == "a" and self._h:
            self.items.append((self._t.strip()[:80], self._h))
            self._h = None


def page_pdfs(url):
    final, status, ct, data = fetch(url)
    p = A(final)
    p.feed(data.decode("utf-8", "replace"))
    return final, [(t, h) for t, h in p.items if ".pdf" in h.lower()]


print("=== GALLOON LINKS ===")
final, items = page_pdfs("https://www.galloonparish.com/bulletin-1.html")
for t, h in items[:20]:
    print(json.dumps({"t": t, "h": h}, ensure_ascii=False), flush=True)

print("=== ENNISKILLEN LINKS ===")
final, items = page_pdfs("https://www.saintmichaels-parish.com/news.asp")
for t, h in items[:20]:
    print(json.dumps({"t": t, "h": h}, ensure_ascii=False), flush=True)

files = [
    "https://www.lisnaskeamaguiresbridgeparish.com/onewebmedia/23082026.pdf",
    "https://monaghan-rackwallace.com/wp-content/uploads/2026/08/23082026.pdf",
    "https://www.saintmichaels-parish.com/pdf/230826.pdf",
    "https://www.galloonparish.com/onewebmedia/Aug%2016%20%202026.pdf",
]
print("=== FILES ===")
for url in files:
    try:
        final, status, ct, data = fetch(url)
        print(json.dumps({
            "url": url, "final": final, "status": status, "ct": ct,
            "len": len(data), "pdf": data[:5] == b"%PDF-",
        }), flush=True)
    except Exception as e:
        print(json.dumps({"url": url, "err": f"{type(e).__name__} {e}"}), flush=True)
