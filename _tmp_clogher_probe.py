# -*- coding: utf-8 -*-
import json
import re
import ssl
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        data = r.read()
        return r.geturl(), r.status, r.headers.get("content-type", ""), data


urls = [
    "https://www.lisnaskeamaguiresbridgeparish.com/bulletin.html",
    "https://www.galloonparish.com/bulletin-1.html",
    "https://monaghan-rackwallace.com/parish-news/",
    "https://monaghan-rackwallace.com/past-newsletters/",
    "https://www.saintmichaels-parish.com/news.asp",
    "http://www.pobalparish.com/news.html",
    "https://monaghan-rackwallace.com/wp-json/wp/v2/media?per_page=15&orderby=date&order=desc",
]
for url in urls:
    rec = {"url": url}
    try:
        final, status, ct, data = fetch(url)
        rec.update({"final": final, "status": status, "ct": ct, "len": len(data)})
        if data[:5] == b"%PDF-":
            rec["pdf"] = True
        else:
            text = data.decode("utf-8", "replace")
            rec["pdfs"] = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)', text, re.I)[:15]
            rec["imgs"] = [m for m in re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png)', text, re.I) if any(x in m.lower() for x in ("bulletin", "news", "sunday", "upload"))][:12]
            rec["dates"] = sorted(set(re.findall(r"(?:sunday\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}", text.lower())))[:20]
            rec["text"] = " ".join(re.sub(r"<[^>]+>", " ", text).split())[:450]
            if "wp-json" in url:
                items = json.loads(text)
                rec["media"] = []
                if isinstance(items, list):
                    for it in items[:12]:
                        rec["media"].append({
                            "t": (it.get("title") or {}).get("rendered") if isinstance(it.get("title"), dict) else it.get("title"),
                            "src": it.get("source_url"),
                        })
        print(json.dumps({k: rec.get(k) for k in ("url", "final", "len", "pdfs", "dates", "media")}, ensure_ascii=False)[:1200], flush=True)
    except Exception as e:
        print(json.dumps({"url": url, "err": f"{type(e).__name__} {e}"}), flush=True)

with open("_tmp_clogher_probe.json", "w", encoding="utf-8") as f:
    json.dump(rec, f)  # last only; rewrite below
