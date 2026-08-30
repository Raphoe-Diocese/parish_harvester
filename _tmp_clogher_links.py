"""Fetch the diocese parish-websites page and a few missed bulletin paths."""
from __future__ import annotations

import re
from html import unescape
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def get(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urlopen(req, timeout=25) as resp:
        print("GET", resp.status, resp.geturl(), "len", resp.headers.get("Content-Length"))
        return resp.read().decode("utf-8", errors="ignore")


html = get("https://clogherdiocese.ie/links/clogher-diocese-parish-websites/")
hrefs = re.findall(r"""<a[^>]+href=["']([^"']+)["'][^>]*>(.*?)</a>""", html, flags=re.I | re.S)
print("=== DIOCESE WEBSITE LINKS ===")
for href, text in hrefs:
    href = unescape(href)
    text = re.sub(r"<[^>]+>", "", unescape(text)).strip()
    if any(skip in href.lower() for skip in ("clogherdiocese.ie", "facebook.com/dioceseofclogher", "twitter.com", "idonate", "acnireland", "#", "javascript:", "wp-login", "mailto:")):
        continue
    if href.startswith("/"):
        href = "https://clogherdiocese.ie" + href
    print(f"  {text} -> {href}")

for url in (
    "https://www.killannyparish.ie/parish-bulletin",
    "http://www.tullycorbetparish.com/parishnews.htm",
    "https://www.dromorecatholicparish.com/",
    "https://www.devenishparishirvinestown.com/",
    "https://www.saintmichaels-parish.com/",
    "https://fintonaparish.com/",
    "https://www.pobalparish.com/parishnews.html",
    "http://www.pobalparish.com/parishnews.html",
):
    print("\n===", url, "===")
    try:
        body = get(url)
    except Exception as exc:
        print(" ERR", type(exc).__name__, exc)
        continue
    pdfs = [unescape(h) for h in re.findall(r"""href=["']([^"']+\.pdf[^"']*)["']""", body, flags=re.I)]
    news = [unescape(h) for h in re.findall(r"""href=["']([^"']+)["']""", body, flags=re.I) if any(t in h.lower() for t in ("bulletin", "newsletter", "parishnews", "templates/", "messenger"))]
    print(" pdfs", pdfs[:15])
    print(" news", news[:20])
    if "Sunday" in body and "August" in body:
        print(" contains August Sunday text")
