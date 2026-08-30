"""Live probe for St Teresa's predicted / wp-json bulletin posts. Not committed."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from datetime import date, timedelta
from urllib.parse import quote

from harvester.bulletin_freshness import check_bulletin_freshness, extract_bulletin_date
from harvester.utils import _MONTH_NAMES, _ordinal_suffix

TARGET = date(2026, 8, 16)
ORIGIN = "https://stteresasparish.church"
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
    except Exception as exc:
        print(f"  FETCH FAIL {url}: {exc}")
        return 0, {}, b""


def summarize(url: str) -> None:
    status, headers, body = fetch(url)
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    print(f"  HTTP {status}  {len(body):>8} bytes  {ct.split(';')[0]}  {url}")
    if body[:4] == b"%PDF":
        print("    PDF magic")
    elif body[:3] == b"\xff\xd8\xff":
        print("    JPEG")
    text = body.decode("utf-8", errors="ignore")
    low = text.lower()
    if "not found" in low[:4000] or "page not found" in low[:4000]:
        print("    looks like HTML 404")
    if "the-st-teresas-parish-bulletin-for-sunday" in low:
        print("    contains bulletin slug text")
    if "microsoft-word" in low:
        print("    contains microsoft-word image ref")
    print("    date", extract_bulletin_date(url), "fresh", check_bulletin_freshness(url, TARGET))


def sunday_slug(d: date) -> str:
    return (
        f"the-st-teresas-parish-bulletin-for-sunday-"
        f"{d.day}{_ordinal_suffix(d.day)}-{_MONTH_NAMES[d.month]}-{d.year}"
    )


def main() -> None:
    print("=== wp-json posts search ===")
    search = quote("st-teresas-parish-bulletin-for-sunday")
    api = (
        f"{ORIGIN}/wp-json/wp/v2/posts"
        f"?search={search}&per_page=10&orderby=date&order=desc"
    )
    status, headers, body = fetch(api)
    ct = headers.get("Content-Type") or headers.get("content-type") or ""
    print(f"API HTTP {status} {len(body)} bytes {ct}")
    posts = []
    if body[:1] == b"[":
        posts = json.loads(body.decode("utf-8", errors="replace"))
        for p in posts:
            slug = p.get("slug")
            link = p.get("link")
            pdt = p.get("date")
            title = (p.get("title") or {}).get("rendered")
            content = (p.get("content") or {}).get("rendered") or ""
            print(f"  POST {pdt}  {slug}")
            print(f"       {link}")
            print(f"       title={title}")
            print(f"       content_len={len(content)}  word-imgs={content.lower().count('microsoft-word')}")
            print(f"       slug_date={extract_bulletin_date(link or slug or '')}")
    elif body[:1] == b"{":
        print(body[:400])
    else:
        print(body[:300])

    print("\n=== exact slug 16 Aug ===")
    slug16 = sunday_slug(TARGET)
    api16 = f"{ORIGIN}/wp-json/wp/v2/posts?slug={slug16}"
    status, headers, body = fetch(api16)
    print(f"slug16 API HTTP {status} {len(body)} {body[:120]!r}")

    print("\n=== predicted post-date range for 16 Aug and 9 Aug ===")
    for week in (TARGET, TARGET - timedelta(days=7), date(2026, 8, 2)):
        slug = sunday_slug(week)
        print(f"-- Sunday {week} slug={slug}")
        for offset in (2, 3, 4, 1, 5, 6):
            post = week - timedelta(days=offset)
            url = f"{ORIGIN}/{post.year}/{post.month:02d}/{post.day:02d}/{slug}/"
            summarize(url)

    print("\n=== known live examples ===")
    for url in (
        "https://stteresasparish.church/2026/08/06/the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/",
        "https://stteresasparish.church/2026/07/30/the-st-teresas-parish-bulletin-for-sunday-2nd-august-2026/",
        "https://stteresasparish.church/feed/",
        "https://stteresasparish.church/",
        "https://stteresasparish.church/wp-content/uploads/2026/08/microsoft-word-9-august-2026.docx.jpg",
        "https://stteresasparish.church/wp-content/uploads/2026/08/microsoft-word-9-august-2026.docx-2.jpg",
        "https://stteresasparish.church/wp-content/uploads/2026/08/microsoft-word-16-august-2026.docx.jpg",
        "https://stteresasparish.church/wp-content/uploads/2026/08/microsoft-word-16-august-2026.docx-2.jpg",
    ):
        summarize(url)

    img_url = "https://stteresasparish.church/wp-content/uploads/2026/08/microsoft-word-9-august-2026.docx.jpg"
    print("\n=== freshness of image URL vs post URL ===")
    print("img", extract_bulletin_date(img_url), check_bulletin_freshness(img_url, TARGET))
    post = "https://stteresasparish.church/2026/08/06/the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/"
    print("post", extract_bulletin_date(post), check_bulletin_freshness(post, TARGET))


if __name__ == "__main__":
    main()
