# -*- coding: utf-8 -*-
import json
import re
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


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
            self.items.append((" ".join(self._t.split())[:100], self._h))
            self._h = None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
        return r.geturl(), r.status, r.headers.get("content-type", ""), r.read()


def page(url, keep=None):
    final, status, ct, data = fetch(url)
    rec = {"url": url, "final": final, "status": status, "ct": ct, "len": len(data), "head": data[:8]}
    if data[:5] == b"%PDF-":
        rec["pdf"] = True
        return rec
    text = data.decode("utf-8", "replace")
    p = A(final)
    try:
        p.feed(text)
    except Exception:
        pass
    rec["hrefs"] = [
        {"t": t, "h": h}
        for t, h in p.items
        if keep is None or any(x in (t + h).lower() for x in keep)
    ][:40]
    rec["dates"] = sorted(set(re.findall(
        r"(?:sunday\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}",
        text.lower(),
    )))[:20]
    rec["text"] = " ".join(re.sub(r"<[^>]+>", " ", text).split())[:400]
    return rec


KEEP = ("bulletin", "news", "newsletter", "pdf", "rtf", "doc", "august", "sunday", "upload")
pages = [
    "https://magheraclooneparish.com/bulletins/",
    "https://magheraclooneparish.com/",
    "https://kilmoredrumsnatt.com/past-newsletters/",
    "https://kilmoredrumsnatt.com/parish-news/",
    "https://kilmoredrumsnatt.com/",
    "https://www.truaghparish.com/",
    "https://www.truaghparish.com/parish-newsletter",
    "https://kilmoredrumsnatt.com/wp-json/wp/v2/media?per_page=15&orderby=date&order=desc",
    "https://magheraclooneparish.com/wp-json/wp/v2/media?per_page=15&orderby=date&order=desc",
]
out = []
for u in pages:
    try:
        rec = page(u, KEEP)
        print("OK", u, "hrefs", len(rec.get("hrefs") or []), "dates", rec.get("dates"), flush=True)
    except Exception as e:
        rec = {"url": u, "err": f"{type(e).__name__} {e}"}
        print("ERR", u, rec["err"], flush=True)
    out.append(rec)

files = [
    "https://magheraclooneparish.com/app/uploads/2026/08/23rd-August-2026-.rtf",
]
for u in files:
    try:
        final, status, ct, data = fetch(u)
        rec = {"url": u, "final": final, "status": status, "ct": ct, "len": len(data), "head": data[:20].decode("latin-1", "replace")}
        print("FILE", rec, flush=True)
        out.append(rec)
    except Exception as e:
        print("FILE ERR", u, e, flush=True)
        out.append({"url": u, "err": str(e)})

with open("_tmp_clogher_kitchen.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("WROTE")
