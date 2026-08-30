# -*- coding: utf-8 -*-
import json
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


class L(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.hrefs = []
        self.texts = []
        self._t = ""
        self._href = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._href = urljoin(self.base, a["href"].strip())
            self._t = ""

    def handle_data(self, data):
        if self._href is not None:
            self._t += data

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.hrefs.append((self._t.strip()[:80], self._href))
            self._href = None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
        return r.geturl(), r.read()


URLS = [
    "https://www.killannyparish.ie/parish-bulletin",
    "https://www.dromorecatholicparish.com/latest-bulletin/",
    "https://www.devenishparishirvinestown.com/weekly-bulletin",
    "https://fintonaparish.com/services/latest-bulletin/",
    "http://www.patrickkavanaghcountry.com/html/bulletin.htm",
    "http://www.tullycorbetparish.com/parishnews.htm",
    "http://www2.st-michaels.net/",
    "https://culmaine.co.uk/newsletter",
    "http://www.donaghmoyne.com/html/bulletin.html",
    "http://www.aughnamulleneast.com/",
    "http://www.pettigoparish.ie/",
    "http://www.clonesparish.com/",
    "http://www.monaghan-rackwallace.ie/",
    "http://www.donaghparish.com/",
]

out = []
for url in URLS:
    rec = {"url": url}
    try:
        final, data = fetch(url)
        rec["final"] = final
        rec["len"] = len(data)
        rec["pdf"] = data[:5] == b"%PDF-"
        text = data.decode("utf-8", "replace") if not rec["pdf"] else ""
        rec["has_pdf_sig"] = "%PDF" in text[:200]
        p = L(final)
        try:
            p.feed(text)
        except Exception as e:
            rec["parse_err"] = str(e)
        rec["hrefs"] = [
            {"t": t, "h": h}
            for t, h in p.hrefs
            if any(x in h.lower() for x in (".pdf", "bulletin", "news", "newsletter", "upload", "media", "wp-content", "templates"))
            or any(x in t.lower() for x in ("bulletin", "news", "newsletter", "pdf"))
        ][:40]
        low = text.lower()
        rec["has_aug"] = "august" in low or "aug 2026" in low or "23rd" in low or "16th" in low
        rec["snip"] = " ".join(text.replace("\n", " ").split())[:400]
    except Exception as e:
        rec["err"] = f"{type(e).__name__} {e}"
    out.append(rec)
    print(json.dumps({k: rec.get(k) for k in ("url", "final", "len", "err", "pdf")}, ensure_ascii=False), flush=True)

with open("_tmp_clogher_expand.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("WROTE", len(out))
