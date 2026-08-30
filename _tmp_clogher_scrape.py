# -*- coding: utf-8 -*-
import re
import ssl
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


pages = [
    "https://www.lisnaskeamaguiresbridgeparish.com/",
    "https://www.galloonparish.com/",
    "https://monaghan-rackwallace.com/",
    "https://www.saintmichaels-parish.com/",
    "http://www.pobalparish.com/",
    "https://fintonaparish.com/services/latest-bulletin/",
]
for url in pages:
    print("====", url)
    try:
        final, text = fetch(url)
        hrefs = re.findall(r'href=["\']([^"\']+)', text, re.I)
        interesting = [h for h in hrefs if any(x in h.lower() for x in ("bulletin", "news", "newsletter", "messenger", "pdf", "sunday"))]
        print(" final", final)
        print(" interesting", interesting[:25])
        if "fintona" in url:
            imgs = re.findall(r"Sunday-[^\"'\s]+", text)
            print(" sunday files", sorted(set(imgs))[:20])
        if "monaghan" in url:
            print(" text", " ".join(re.sub(r"<[^>]+>", " ", text).split())[:500])
    except Exception as e:
        print(" ERR", type(e).__name__, e)
