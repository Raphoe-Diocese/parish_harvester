"""Proof: wp_json_newest_media for Tawnawilly (no GDPR download)."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from harvester.config import target_sunday
from harvester.replay import _try_wp_json_newest_media


async def main() -> None:
    dest = Path("_tmp_proof_tawnawilly.pdf")
    target = target_sunday(date(2026, 8, 21))
    print("harvest Sunday", target)
    found = await _try_wp_json_newest_media(
        "https://tawnawillyparish.ie/",
        dest,
        href_patterns=["sunday"],
        target_date=target,
    )
    print("found", found)
    if dest.exists():
        data = dest.read_bytes()
        print("bytes", len(data), "pdf", data[:5])
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(str(dest))
            print("pages", len(reader.pages))
            text = (reader.pages[0].extract_text() or "")[:400]
            print("page1", " ".join(text.split())[:400])
        except Exception as exc:
            print("pdf text", exc)


if __name__ == "__main__":
    asyncio.run(main())
