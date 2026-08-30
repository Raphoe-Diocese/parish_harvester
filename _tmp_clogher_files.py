# -*- coding: utf-8 -*-
import ssl, urllib.request
from harvester.utils import extract_date_from_string

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()
urls = [
    "https://kilmoredrumsnatt.com/wp-content/uploads/2026/08/Newsletter-23.08.2026.pdf",
    "https://www.truaghparish.com/_files/ugd/663a37_c41f6f1e28c547ce95e9d28405887faf.pdf",
]
print("23rd-August-2026-.rtf", extract_date_from_string("23rd-August-2026-.rtf"))
print("Newsletter-23.08.2026.pdf", extract_date_from_string("Newsletter-23.08.2026.pdf"))
for url in urls:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
        data = r.read()
        print(url, r.status, r.headers.get("content-type"), len(data), data[:5])
