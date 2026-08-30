"""Fetch churchmedia channel APIs and hunt a real PDF URL."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SLUG = "st-patricks-church-2"
APIS = [
    f"https://churchmedia.tv/api/getChannelPublic?slug={SLUG}",
    f"https://churchmedia.tv/api/getChannelAbout?slug={SLUG}",
    f"https://churchmedia.tv/api/getSchedule?days=0&timezone=Europe/Dublin&slug={SLUG}",
]


def fetch(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.headers.get("content-type", ""), resp.read()


def main() -> None:
    print("cb_new", datetime.fromtimestamp(1787226064, timezone.utc).isoformat())
    print("cb_old", datetime.fromtimestamp(1786005944, timezone.utc).isoformat())
    for url in APIS:
        print("=" * 80)
        print(url)
        try:
            status, ct, body = fetch(url)
        except Exception as exc:
            print("ERR", exc)
            continue
        print("status", status, "ct", ct, "len", len(body))
        text = body.decode("utf-8", "replace")
        print(text[:8000])
        for key in ("newsletter", "bulletin", "pdf", "s22osz", "ovt7qm"):
            print("count", key, text.lower().count(key.lower()))


if __name__ == "__main__":
    main()
