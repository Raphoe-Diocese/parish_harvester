"""Follow-up: WP.com public API, RSS, rest_route, post images. Not committed."""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import quote

from harvester.replay import _WP_UPLOAD_IMAGE_RE, _RESIZED_IMAGE_SUFFIX_RE

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
        print(f"FAIL {url}: {exc}")
        return 0, {}, b""


def dump_posts(label: str, url: str) -> None:
    status, headers, body = fetch(url)
    ct = headers.get("Content-Type") or ""
    print(f"\n=== {label} ===")
    print(f"HTTP {status} {len(body)} {ct.split(';')[0]} {url}")
    if body[:1] in (b"[", b"{"):
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            print(body[:300])
            return
        items = data if isinstance(data, list) else data.get("posts") or data.get("items") or [data]
        if isinstance(items, dict):
            items = [items]
        print(f"items={len(items)}")
        for p in items[:8]:
            if not isinstance(p, dict):
                print(" ", p)
                continue
            slug = p.get("slug") or p.get("name")
            link = p.get("link") or p.get("URL")
            print(f"  {p.get('date')} {slug} {link}")
    else:
        print(body[:200].decode("utf-8", errors="replace"))


def main() -> None:
    search = quote("st-teresas-parish-bulletin-for-sunday")
    dump_posts(
        "public-api search",
        f"https://public-api.wordpress.com/wp/v2/sites/stteresasparish.church/posts?search={search}&per_page=10&orderby=date&order=desc",
    )
    dump_posts(
        "public-api recent",
        "https://public-api.wordpress.com/wp/v2/sites/stteresasparish.church/posts?per_page=8&orderby=date&order=desc",
    )
    dump_posts(
        "rest_route",
        f"{ORIGIN}/?rest_route=/wp/v2/posts&search={search}&per_page=10",
    )
    dump_posts(
        "wp-json posts no search",
        f"{ORIGIN}/wp-json/wp/v2/posts?per_page=5",
    )

    print("\n=== RSS links ===")
    status, headers, body = fetch(f"{ORIGIN}/feed/")
    print(f"HTTP {status} {len(body)} {headers.get('Content-Type')}")
    xml = body.decode("utf-8", errors="ignore")
    links = re.findall(r"<link>([^<]+)</link>", xml)
    titles = re.findall(r"<title>([^<]+)</title>", xml)
    print("titles:", titles[:8])
    print("links:")
    for link in links[:12]:
        print(" ", link)

    print("\n=== 9 Aug post images ===")
    post = f"{ORIGIN}/2026/08/06/the-st-teresas-parish-bulletin-for-sunday-9th-august-2026/"
    status, headers, body = fetch(post)
    html = body.decode("utf-8", errors="ignore")
    print(f"HTTP {status} {len(body)} error404={'error404' in html.lower()}")
    for m in _WP_UPLOAD_IMAGE_RE.finditer(html):
        name = m.group(3)
        resized = bool(_RESIZED_IMAGE_SUFFIX_RE.search(name))
        print(f"  {'SKIP' if resized else 'KEEP'} {m.group(1)}/{m.group(2)}/{name}")

    print("\n=== homepage bulletin hrefs ===")
    status, headers, body = fetch(f"{ORIGIN}/")
    html = body.decode("utf-8", errors="ignore")
    hrefs = re.findall(r'href=["\']([^"\']*the-st-teresas-parish-bulletin-for-sunday[^"\']*)["\']', html, re.I)
    print("count", len(hrefs))
    for h in dict.fromkeys(hrefs):
        print(" ", h)


if __name__ == "__main__":
    main()
