"""Probe St Gerard listing/post pages without relying on PowerShell quoting."""
from __future__ import annotations

import re
import ssl
import urllib.request

ctx = ssl.create_default_context()
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

URLS = [
    "https://stgerardsparish.org/",
    "https://stgerardsparish.org/parish-news-events/",
    "https://stgerardsparish.org/sunday-bulletin-16th-august-2026/",
    "https://stgerardsparish.org/parish-bulletin-16th-august-2026/",
    "https://stgerardsparish.org/parish-bulletin-9th-august-2026/",
    "https://stgerardsparish.org/sunday-bulletin-9th-august-2026/",
]


def fetch(url: str) -> tuple[int | None, str, str, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as resp:
            body = resp.read()
            text = body.decode("utf-8", "ignore")
            return resp.status, resp.geturl(), resp.headers.get("content-type", ""), text
    except Exception as exc:  # noqa: BLE001
        return None, url, "", f"ERR {type(exc).__name__}: {exc}"


def main() -> None:
    for url in URLS:
        status, final, ctype, text = fetch(url)
        print("=" * 72)
        print(url, "status", status, "len", len(text), "final", final)
        print("ct", ctype)
        if text.startswith("ERR"):
            print(text)
            continue
        low = text.lower()
        print("captcha", "sg-captcha" in low or "just a moment" in low)
        hrefs = re.findall(r"""href=["']([^"']+)["']""", text, re.I)
        interesting = [
            h
            for h in hrefs
            if any(x in h.lower() for x in ("bulletin", "sunday", "august", "message", "news"))
        ]
        print("interesting hrefs", len(interesting))
        for h in interesting[:50]:
            print(" ", h)
        titles = re.findall(
            r"(Sunday Bulletin[^<]{0,90}|Sunday Message[^<]{0,90}|Parish Bulletin[^<]{0,90})",
            text,
            re.I,
        )
        print("titles", titles[:20])
        imgs = re.findall(r"""(?:src|data-src|href)=["']([^"']+\.(?:png|jpe?g|webp)[^"']*)["']""", text, re.I)
        print("images", len(imgs))
        for img in imgs[:25]:
            print(" ", img)
        print()


if __name__ == "__main__":
    main()
