# -*- coding: utf-8 -*-
import ssl
import urllib.request

urls = [
    "https://www.clonesparish.com/",
    "https://www.lisnaskeamaguiresbridgeparish.com/bulletin.html",
    "https://www.galloonparish.com/bulletin-1.html",
    "https://www.saintmichaels-parish.com/news.asp",
    "https://monaghan-rackwallace.com/",
    "https://fintonaparish.com/services/latest-bulletin/",
    "https://culmaine.co.uk/newsletter",
    "https://donaghparish.com/parish-news/",
    "https://www.devenishparishirvinestown.com/weekly-bulletin",
]
ctx = ssl.create_default_context()
for url in urls:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            print("OK", r.status, url)
    except Exception as e:
        print("FAIL", type(e).__name__, e, url)
