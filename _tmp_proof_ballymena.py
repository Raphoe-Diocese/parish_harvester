"""Proof pack: Ballymena wp-json newest Sunday PDF (never Wedding-Parish.pdf)."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from harvester.bulletin_freshness import check_bulletin_freshness, extract_bulletin_date
from harvester.config import target_sunday
from harvester.replay import _is_non_bulletin_url, _try_wp_json_newest_media
from harvester.utils import format_uk_date

UA = "Mozilla/5.0 (compatible; ParishHarvester/1.0)"
API = (
    "https://ballymenaparish.org/wp-json/wp/v2/media"
    "?per_page=20&orderby=date&order=desc"
)
LISTING = "https://ballymenaparish.org/bulletin-and-parish-documents/"
WEDDING = "https://ballymenaparish.org/wp-content/uploads/2025/01/Wedding-Parish.pdf"
START = "https://ballymenaparish.org/"


def get(url: str):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=30) as resp:
        return resp.status, dict(resp.headers), resp.read()


def main() -> None:
    target = target_sunday()
    print("TODAY target_sunday", target.isoformat(), format_uk_date(target))

    status, headers, body = get(API)
    print("WPJSON status", status, "ct", headers.get("Content-Type"), "bytes", len(body))
    items = json.loads(body.decode("utf-8", errors="replace"))
    print("media items", len(items))
    for item in items:
        src = str(item.get("source_url") or "")
        slug = str(item.get("slug") or "")
        raw = item.get("title")
        title = str(raw.get("rendered") or "") if isinstance(raw, dict) else ""
        blob = f"{src} {slug} {title}".lower()
        if any(token in blob for token in (".pdf", "sunday", "wedding", "bulletin")):
            print(" -", src)
            print(
                "   slug=",
                slug,
                "title=",
                title,
                "non_bulletin=",
                _is_non_bulletin_url(src),
                "date=",
                extract_bulletin_date(src),
            )

    status, _headers, listing = get(LISTING)
    html = listing.decode("utf-8", errors="ignore")
    print(
        "LISTING status",
        status,
        "wedding in html",
        "Wedding-Parish" in html,
        "23.8.26 in html",
        "23.8.26" in html,
        "16.8.26 in html",
        "16.8.26" in html,
    )

    async def run():
        dest = Path(tempfile.gettempdir()) / "ballymena_proof.pdf"
        if dest.exists():
            dest.unlink()
        found = await _try_wp_json_newest_media(
            START,
            dest,
            href_patterns=["sunday"],
            target_date=target,
        )
        print("FOUND", found)
        if found and dest.exists():
            data = dest.read_bytes()
            print(
                "PDF magic",
                data[:5],
                "bytes",
                len(data),
                "page markers",
                data.count(b"/Type /Page"),
            )
            print("freshness", check_bulletin_freshness(found[0], target))
            dest.replace(Path("_tmp_proof_ballymena.pdf"))
            print("saved _tmp_proof_ballymena.pdf")

    asyncio.run(run())
    print("wedding non_bulletin", _is_non_bulletin_url(WEDDING))


if __name__ == "__main__":
    main()
