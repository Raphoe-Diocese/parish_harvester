# -*- coding: utf-8 -*-
import json
import re
import ssl
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.geturl(), r.status, r.headers.get("content-type", ""), r.read()


def headish(url):
    try:
        final, status, ct, data = fetch(url)
        return {
            "url": url,
            "final": final,
            "status": status,
            "ct": ct,
            "len": len(data),
            "pdf": data[:5] == b"%PDF-",
            "img": data[:3] in (b"\xff\xd8\xff", b"\x89PN"),
        }
    except Exception as e:
        return {"url": url, "err": f"{type(e).__name__} {e}"}


class AllHrefs(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.items = []
        self._href = None
        self._t = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self._href = urljoin(self.base, a["href"].strip())
            self._t = ""
        if tag == "img" and a.get("src"):
            src = urljoin(self.base, a["src"].strip())
            self.items.append({"tag": "img", "h": src, "t": a.get("alt", "")[:80]})

    def handle_data(self, data):
        if self._href is not None:
            self._t += data

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.items.append({"tag": "a", "h": self._href, "t": " ".join(self._t.split())[:120]})
            self._href = None


def parse_page(url):
    final, status, ct, data = fetch(url)
    text = data.decode("utf-8", "replace")
    p = AllHrefs(final)
    try:
        p.feed(text)
    except Exception:
        pass
    low = text.lower()
    dates = sorted(set(re.findall(
        r"(?:sunday\s+)?(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}|\d{1,2}[./-]\d{1,2}[./-]20\d{2}|20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
        low,
    )))
    return {
        "url": url,
        "final": final,
        "status": status,
        "len": len(data),
        "dates": dates[:30],
        "pdfs": [i for i in p.items if ".pdf" in i["h"].lower()],
        "imgs": [i for i in p.items if any(x in i["h"].lower() for x in ("bulletin", "news", "gallery", "newsletter", "upload"))],
        "news": [i for i in p.items if any(x in (i["h"] + i["t"]).lower() for x in ("bulletin", "news", "newsletter", "messenger", "templates"))],
        "iframe": re.findall(r'<iframe[^>]+src=["\']([^"\']+)', text, re.I)[:10],
        "embed": re.findall(r'<embed[^>]+src=["\']([^"\']+)', text, re.I)[:10],
        "snip_body": re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text, flags=re.I),
    }


pages = [
    "https://www.clonesparish.com/",
    "https://www.devenishparishirvinestown.com/weekly-bulletin",
    "https://www.dromorecatholicparish.com/latest-bulletin/",
    "https://fintonaparish.com/services/latest-bulletin/",
    "https://culmaine.co.uk/newsletter",
    "https://www.killannyparish.ie/parish-bulletin",
    "http://www.tullycorbetparish.com/parishnews.htm",
    "http://www.tullycorbetparish.com/pastnews.htm",
    "https://donaghparish.com/parish-news/",
    "https://www.saintmichaels-parish.com/",
    "https://www.lisnaskeamaguiresbridgeparish.com/",
    "https://www.galloonparish.com/",
    "https://www.pobalparish.com/",
    "https://www.clonesparish.com/news/",
    "https://donaghparish.com/wp-json/wp/v2/media?per_page=10&orderby=date&order=desc",
    "https://www.dromorecatholicparish.com/wp-json/wp/v2/media?per_page=15&orderby=date&order=desc",
    "https://fintonaparish.com/wp-json/wp/v2/media?per_page=15&orderby=date&order=desc",
    "https://www.clonesparish.com/wp-json/wp/v2/media?per_page=10&orderby=date&order=desc",
]

out = {"pages": [], "files": []}
for url in pages:
    rec = {"url": url}
    try:
        parsed = parse_page(url)
        body = parsed.pop("snip_body")
        # keep a short text-only snippet
        parsed["text"] = " ".join(re.sub(r"<[^>]+>", " ", body).split())[:600]
        if "wp-json" in url:
            try:
                _, _, _, raw = fetch(url)
                parsed["json_titles"] = []
                items = json.loads(raw.decode("utf-8", "replace"))
                if isinstance(items, list):
                    for it in items[:12]:
                        src = it.get("source_url")
                        title = (it.get("title") or {}).get("rendered") if isinstance(it.get("title"), dict) else it.get("title")
                        parsed["json_titles"].append({"t": title, "src": src})
            except Exception as e:
                parsed["json_err"] = str(e)
        rec.update(parsed)
        print("OK", url, "pdfs", len(rec.get("pdfs") or []), "dates", rec.get("dates"), flush=True)
    except Exception as e:
        rec["err"] = f"{type(e).__name__} {e}"
        print("ERR", url, rec["err"], flush=True)
    out["pages"].append(rec)

pdfs = [
    "https://www.clonesparish.com/uploads/downloads/Sunday 23rd August 2026.pdf",
    "https://www.devenishparishirvinestown.com/_files/ugd/dae26f_bc96e058a7d049b8a6f9bd2ee3ca2109.pdf",
]
# encode spaces
pdfs[0] = "https://www.clonesparish.com/uploads/downloads/Sunday%2023rd%20August%202026.pdf"

for u in pdfs:
    info = headish(u)
    out["files"].append(info)
    print("FILE", info, flush=True)

with open("_tmp_clogher_verify.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("WROTE")
