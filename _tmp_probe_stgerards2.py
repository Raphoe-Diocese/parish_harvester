"""Retry-probe St Gerard via harvester HTTP retries + sitemap/feed."""
from __future__ import annotations

import re
from pathlib import Path

from harvester.replay import _fetch_bytes_with_retries

URLS = [
    "https://stgerardsparish.org/",
    "https://stgerardsparish.org/parish-news-events/",
    "https://stgerardsparish.org/feed/",
    "https://stgerardsparish.org/wp-sitemap.xml",
    "https://stgerardsparish.org/wp-sitemap-posts-post-1.xml",
    "https://stgerardsparish.org/sunday-bulletin-16th-august-2026/",
    "https://stgerardsparish.org/parish-bulletin-16th-august-2026/",
]


def summarize(url: str, body: bytes, headers: dict[str, str]) -> None:
    text = body.decode("utf-8", "ignore")
    print("=" * 72)
    print(url, "len", len(body), "ct", headers.get("content-type"))
    print("captcha", b"sg-captcha" in body.lower() or b"just a moment" in body.lower())
    hrefs = re.findall(r"""href=["']([^"']+)["']""", text, re.I)
    locs = re.findall(r"<loc>([^<]+)</loc>", text, re.I)
    titles = re.findall(r"<title>([^<]+)</title>", text, re.I)
    interesting = [
        h
        for h in hrefs + locs
        if any(x in h.lower() for x in ("bulletin", "sunday", "august", "message", "news"))
    ]
    print("titles", titles[:15])
    print("interesting", len(interesting))
    for h in interesting[:60]:
        print(" ", h)
    if "parish-news" in url or url.rstrip("/").endswith("stgerardsparish.org"):
        imgs = re.findall(
            r"""(?:src|data-src|href)=["']([^"']+\.(?:png|jpe?g|webp)[^"']*)["']""",
            text,
            re.I,
        )
        print("images", len(imgs))
        for img in imgs[:20]:
            print(" ", img)
    snippet = re.sub(r"\s+", " ", text)[:400]
    print("snippet", snippet)
    print()


def main() -> None:
    out = Path("_tmp_probe_stgerards2_out.txt")
    lines: list[str] = []

    def p(*args: object) -> None:
        lines.append(" ".join(str(a) for a in args))
        print(*args)

    for url in URLS:
        hit = _fetch_bytes_with_retries(
            url,
            max_attempts=20,
            per_attempt_timeout_s=5.0,
            total_budget_s=40.0,
        )
        if not hit:
            p("=" * 72)
            p(url, "NO HIT after retries")
            p()
            continue
        body, headers = hit
        text = body.decode("utf-8", "ignore")
        p("=" * 72)
        p(url, "len", len(body), "ct", headers.get("content-type"))
        p("captcha", "sg-captcha" in text.lower() or "just a moment" in text.lower())
        hrefs = re.findall(r"""href=["']([^"']+)["']""", text, re.I)
        locs = re.findall(r"<loc>([^<]+)</loc>", text, re.I)
        titles = re.findall(r"<title>([^<]+)</title>", text, re.I)
        interesting = [
            h
            for h in hrefs + locs
            if any(x in h.lower() for x in ("bulletin", "sunday", "august", "message", "news"))
        ]
        p("titles", titles[:20])
        p("interesting", len(interesting))
        for h in interesting[:80]:
            p(" ", h)
        imgs = re.findall(
            r"""(?:src|data-src|href)=["']([^"']+\.(?:png|jpe?g|webp)[^"']*)["']""",
            text,
            re.I,
        )
        p("images", len(imgs))
        for img in imgs[:25]:
            p(" ", img)
        p("snippet", re.sub(r"\s+", " ", text)[:500])
        p()

    out.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
