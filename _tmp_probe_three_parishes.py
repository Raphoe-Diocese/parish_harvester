"""Live proof probe for iskaheen, errigal, limavady. Not committed."""
from __future__ import annotations

import re
import ssl
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from harvester.bulletin_freshness import check_bulletin_freshness, extract_bulletin_date
from harvester.replay import (
    _extract_matching_hrefs,
    _extract_scored_upload_images,
    _score_http_scrape_pdf_hrefs,
)
from harvester.utils import predicted_dated_upload_urls, rewrite_date_url

TARGET = date(2026, 8, 16)
CTX = ssl.create_default_context()
UA = "Mozilla/5.0 (compatible; ParishHarvester/1.0; +https://github.com/Raphoe-Diocese/parish_harvester)"


def fetch(url: str, timeout: int = 25) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return exc.code, dict(exc.headers or {}), body


def summarize(url: str) -> None:
    status, headers, body = fetch(url)
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    print(f"  HTTP {status}  {len(body):>8} bytes  {ct.split(';')[0]}  {url}")
    if body[:4] == b"%PDF":
        print("    PDF magic OK")
    elif body[:3] in (b"\xff\xd8\xff",) or body[:8] == b"\x89PNG\r\n\x1a\n":
        print("    image magic OK")
    elif body[:15].lower().startswith(b"<!doctype") or body[:6].lower().startswith(b"<html"):
        print("    HTML page")


def main() -> None:
    print("=== ISKAHEEN listing ===")
    listing = "https://www.iskaheenparish.com/bulletin"
    status, headers, body = fetch(listing)
    html = body.decode("utf-8", errors="ignore")
    print(f"listing HTTP {status} {len(body)} bytes {headers.get('Content-Type')}")
    imgs = re.findall(r"wp-content/uploads/20\d{2}/\d{2}/[A-Za-z0-9_.%-]+\.(?:png|jpe?g)", html, re.I)
    print("upload image refs:", len(imgs))
    for u in dict.fromkeys(imgs):
        print(" ", u)
    scored = _extract_scored_upload_images(html, listing, href_patterns=[], target_date=TARGET)
    print("scored:", scored)
    if scored:
        best = max(item[0] for item in scored)
        week = [u for d, u in scored if d == best]
        print("week urls:", week)
        for u in week[:2]:
            summarize(u)
            print("   freshness", check_bulletin_freshness(u, TARGET))

    print("\n=== ERRIGAL listing + predicted ===")
    news = "https://www.errigalparish.com/news.html"
    status, headers, body = fetch(news)
    html = body.decode("utf-8", errors="ignore")
    print(f"listing HTTP {status} {len(body)} bytes")
    hrefs = _extract_matching_hrefs(html, news, [".pdf"])
    print("pdf hrefs:")
    for h in hrefs:
        print(" ", h)
    for guess in (
        "https://www.errigalparish.com/pdf/160826.pdf",
        "https://www.errigalparish.com/pdf/090826.pdf",
        "https://www.errigalparish.com/pdf/230826.pdf",
        "https://www.errigalparish.com/pdf/020826.pdf",
    ):
        summarize(guess)
        print("   date", extract_bulletin_date(guess), "fresh", check_bulletin_freshness(guess, TARGET))
    example = "https://www.errigalparish.com/pdf/160826.pdf"
    preds = predicted_dated_upload_urls(example, TARGET, weeks_back=3)
    print("predicted:", preds[:6])
    print("rewrite 090826 ->", rewrite_date_url("https://www.errigalparish.com/pdf/090826.pdf", TARGET))

    print("\n=== LIMAVADY listing + predicted ===")
    listing = "https://www.limavadyparish.org/parish%20bulletins.html"
    status, headers, body = fetch(listing)
    html = body.decode("utf-8", errors="ignore")
    print(f"listing HTTP {status} {len(body)} bytes {headers.get('Content-Type')}")
    Path("_tmp_limavady.html").write_text(html, encoding="utf-8")
    hrefs = _extract_matching_hrefs(html, listing, [".pdf", "onewebmedia"])
    print("hrefs:", hrefs)
    scored = _score_http_scrape_pdf_hrefs(hrefs, TARGET)
    print("scored:", scored)
    # also dump button-like bits
    for pat in ("16-8-26", "9-8-26", "2-8-26", "onewebmedia", "August", "button"):
        print(f"  contains {pat!r}:", pat.lower() in html.lower())
    for guess in (
        "https://www.limavadyparish.org/onewebmedia/16-8-26.pdf",
        "https://www.limavadyparish.org/onewebmedia/9-8-26.pdf",
        "https://www.limavadyparish.org/onewebmedia/09-8-26.pdf",
        "https://www.limavadyparish.org/onewebmedia/2-8-26.pdf",
        "https://www.limavadyparish.org/onewebmedia/26-7-26.pdf",
        "https://www.limavadyparish.org/onewebmedia/19-7-26.pdf",
        "https://www.limavadyparish.org/onewebmedia/28-6-26.pdf",
    ):
        summarize(guess)
        print("   date", extract_bulletin_date(guess), "fresh", check_bulletin_freshness(guess, TARGET))
    example = "https://www.limavadyparish.org/onewebmedia/16-8-26.pdf"
    print("predicted:", predicted_dated_upload_urls(example, TARGET, weeks_back=4)[:8])
    print("rewrite 28-6-26 ->", rewrite_date_url("https://www.limavadyparish.org/onewebmedia/28-6-26.pdf", TARGET))


if __name__ == "__main__":
    main()
