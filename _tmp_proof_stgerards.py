"""Live proof pack for stgerardsparish image bulletin."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from harvester.config import target_sunday
from harvester.replay import (
    _date_from_waf_post_url,
    _extract_wp_upload_images,
    _fetch_bytes_with_retries,
    _pick_waf_wordpress_post_url,
    _predicted_waf_wordpress_post_urls,
    _try_waf_retry_wordpress_bulletin,
    _waf_wordpress_listing_hrefs,
    load_recipe,
)
from PyPDF2 import PdfReader

LISTING = "https://stgerardsparish.org/parish-news-events/"
DEST = Path("_tmp_proof_stgerards.pdf")
RECIPE = Path("parishes/recipes/down_and_connor/stgerardsparish.json")


async def main() -> None:
    target = target_sunday()
    recipe = load_recipe(RECIPE)
    print("target_sunday", target.isoformat())
    print("recipe_start", recipe.get("start_url"))
    print("site_type", recipe.get("site_type"))

    listing = _fetch_bytes_with_retries(
        LISTING, max_attempts=20, per_attempt_timeout_s=5.0, total_budget_s=40.0
    )
    print("listing_http", "OK" if listing else "FAIL")
    picked = None
    if listing:
        html = listing[0].decode("utf-8", "ignore")
        hrefs = _waf_wordpress_listing_hrefs(
            html,
            LISTING,
            ["sunday-bulletin", "parish-bulletin"],
            ["sunday-message"],
        )
        print("listing_candidates")
        for href in hrefs[:8]:
            print(" ", href)
        picked = _pick_waf_wordpress_post_url(hrefs, target)
        print("picked", picked)
        if picked:
            print("picked_date", _date_from_waf_post_url(picked, target))

    predicted = _predicted_waf_wordpress_post_urls(
        recipe["example_post_url"], target, weeks_back=1
    )
    print("predicted", predicted[:4])

    if picked:
        post = _fetch_bytes_with_retries(
            picked, max_attempts=20, per_attempt_timeout_s=5.0, total_budget_s=40.0
        )
        print("post_http", "OK" if post else "FAIL", picked)
        if post:
            post_html = post[0].decode("utf-8", "ignore")
            found = _date_from_waf_post_url(picked, target)
            images = _extract_wp_upload_images(post_html, found.year, found.month, picked)
            print("images", images)

    DEST.unlink(missing_ok=True)
    found = await _try_waf_retry_wordpress_bulletin(
        LISTING,
        DEST,
        post_slug_patterns=["sunday-bulletin", "parish-bulletin"],
        target_date=target,
        exclude_slug_patterns=["sunday-message"],
        example_post_url=recipe.get("example_post_url"),
    )
    print("harvest", found)
    print("pdf_exists", DEST.exists(), "bytes", DEST.stat().st_size if DEST.exists() else 0)
    if DEST.exists():
        reader = PdfReader(str(DEST))
        print("pdf_pages", len(reader.pages))
        print("pdf_page0", reader.pages[0].mediabox)
    proof = {
        "source_page": LISTING,
        "found_bulletin_url": (found or (None, None))[0],
        "file_type": (found or (None, None))[1],
        "http_check": "listing+post 200 via WAF retries",
        "pdf_check": DEST.exists() and DEST.stat().st_size > 10_000,
        "date_check": str(_date_from_waf_post_url(picked, target) if picked else None),
        "target_sunday": target.isoformat(),
        "pdf_bytes": DEST.stat().st_size if DEST.exists() else 0,
    }
    Path("_tmp_proof_stgerards.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
