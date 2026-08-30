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
        return r.geturl(), r.status, r.headers.get("content-type", ""), r.read()


urls = [
    "https://www.lisnaskeamaguiresbridgeparish.com/bulletin",
    "https://www.lisnaskeamaguiresbridgeparish.com/bulletin/",
    "https://www.galloonparish.com/bulletin",
    "https://www.galloonparish.com/bulletin/",
    "https://www.saintmichaels-parish.com/the-parish-messenger",
    "https://www.saintmichaels-parish.com/the-parish-messenger/",
    "https://fintonaparish.com/wp-content/uploads/2026/01/Sunday-23rd-August-2026-scaled.jpg",
    "https://fintonaparish.com/wp-content/uploads/2026/01/Sunday-23rd-August-2026.jpg",
    "http://www.pobalparish.com/",
    "https://www.monaghan-rackwallace.ie/",
    "https://monaghan-rackwallace.com/",
    "https://www.monaghan-rackwallace.com/",
]

for url in urls:
    try:
        final, status, ct, data = fetch(url)
        text = data.decode("utf-8", "replace") if not data[:5] == b"%PDF-" and data[:3] != b"\xff\xd8" else ""
        pdfs = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)', text, re.I)[:8]
        dates = re.findall(r"23rd\s+August\s+2026|16th\s+August\s+2026|Sunday\s+\d+", text)[:6]
        print(json.dumps({
            "url": url, "final": final, "status": status, "ct": ct, "len": len(data),
            "pdf": data[:5] == b"%PDF-", "jpg": data[:3] == b"\xff\xd8",
            "pdfs": pdfs, "dates": dates,
        }, ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps({"url": url, "err": f"{type(e).__name__} {e}"}), flush=True)
