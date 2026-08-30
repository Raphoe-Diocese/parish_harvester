# -*- coding: utf-8 -*-
import ssl, urllib.request
from io import BytesIO

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()
url = "https://www.truaghparish.com/_files/ugd/663a37_c41f6f1e28c547ce95e9d28405887faf.pdf"
req = urllib.request.Request(url, headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
    data = r.read()
try:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages[:2])
    print("pages", len(reader.pages))
    print(text[:800])
except Exception as e:
    print("ERR", type(e).__name__, e)
