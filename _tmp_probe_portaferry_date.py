"""Date the live Portaferry PDF and see how harvester fetches it."""
from __future__ import annotations

import asyncio
import re
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from PyPDF2 import PdfReader

LIVE = "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf?cb=1787226064"
OUT = Path("_tmp_probe_portaferry.pdf")


def main() -> None:
    req = Request(
        LIVE,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf",
        },
    )
    with urlopen(req, timeout=30) as resp:
        body = resp.read()
        print("http", resp.status, resp.headers.get("content-type"), len(body), body[:8])
    OUT.write_bytes(body)
    reader = PdfReader(str(OUT))
    print("pages", len(reader.pages))
    print("meta", reader.metadata)
    text = ""
    for i, page in enumerate(reader.pages[:4]):
        chunk = page.extract_text() or ""
        text += chunk + "\n"
        print(f"===== PAGE {i+1} =====")
        print(chunk[:2000])
        print()
    dates = re.findall(
        r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+20\d{2}|20\d{2}-\d{2}-\d{2})",
        text,
        re.I,
    )
    print("DATES", dates[:40])
    for word in ("June", "July", "August", "Sunday", "16th", "17th", "23rd", "Portaferry", "Ballyphilip", "Ordinary"):
        print(f"has {word}={word.lower() in text.lower()}")

    from harvester.bulletin_freshness import classify_bulletin_date, extract_date_from_string
    from harvester.utils import extract_date_from_slug

    print("slug_date", extract_date_from_slug(LIVE))
    print("string_date", extract_date_from_string(text[:2000]))
    print("target_this_sun", date(2026, 8, 23))
    print("target_last_sun", date(2026, 8, 16))


if __name__ == "__main__":
    main()
