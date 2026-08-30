# -*- coding: utf-8 -*-
import ssl
import urllib.request
from harvester.utils import extract_date_from_string
from harvester.bulletin_freshness import extract_bulletin_date

samples = [
    "23082026.pdf",
    "230826.pdf",
    "Sunday-23rd-August-2026-scaled.jpg",
    "Sunday 23rd August 2026.pdf",
    "S25C-1i26082010590.pdf",
    "Aug 16  2026.pdf",
    "July26DrawResults.pdf",
]
for s in samples:
    print(s, "extract", extract_date_from_string(s), "fresh", extract_bulletin_date(s))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
url = "https://www.galloonparish.com/onewebmedia/S25C-1i26082010590.pdf"
req = urllib.request.Request(url, headers={"User-Agent": UA})
ctx = ssl._create_unverified_context()
with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
    data = r.read()
    print("galloon23", r.status, r.headers.get("content-type"), len(data), data[:5])
