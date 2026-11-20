"""Regression: Newtown's fixed bulletin link must not mask a fresh fallback.

A permanent URL can return a valid but old cached PDF. The replay helper
must look at its printed issue date before deciding which source to keep.
"""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from harvester.replay import RecipeReplayError, replay_recipe


RECIPE = Path(__file__).resolve().parents[1] / (
    "parishes/recipes/raphoe/newtownkilleaparish.json"
)
PUBLIC = "https://newtownkilleaparish.ie/bulletin/raphoe/newtown-killea"
FALLBACK = (
    "https://newtownkilleaparish.ie/wp-content/uploads/"
    "parish-bulletins/unassigned/raphoe/newtown-killea/bulletin.pdf"
)
TARGET = date(2026, 11, 15)


def _download(dest: Path, old: bool, *, url: str):
    dest.write_bytes(b"%PDF-1.4 old" if old else b"%PDF-1.4 current")
    return url, "pdf"


def test_old_public_redirect_retries_fresh_upload(tmp_path):
    """A valid old PDF isn't a successful harvest if another route is current."""
    dest = tmp_path / "newtownkilleaparish.pdf"
    seen = []

    async def downloader(url, path):
        seen.append(url)
        return _download(path, old=url == PUBLIC, url=url)

    def printed_date(path, target):
        assert target == TARGET
        return date(2026, 10, 25) if path.read_bytes().endswith(b"old") else None

    with (
        patch("harvester.replay._try_http_document_url", new=downloader),
        patch("harvester.bulletin_freshness.pdf_date_before_harvest_week", side_effect=printed_date),
        patch("harvester.replay._try_http_recipe_document_fallbacks", new_callable=AsyncMock) as extra,
    ):
        result = asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=TARGET))

    assert result == (dest, "pdf", FALLBACK)
    assert seen[0] == PUBLIC
    assert FALLBACK in seen
    assert dest.read_bytes().endswith(b"current")
    extra.assert_not_awaited()


def test_fresh_public_redirect_remains_first_choice(tmp_path):
    dest = tmp_path / "newtownkilleaparish.pdf"
    async def downloader(url, path):
        assert url == PUBLIC
        return _download(path, old=False, url=url)

    with (
        patch("harvester.replay._try_http_document_url", new=downloader),
        patch("harvester.bulletin_freshness.pdf_date_before_harvest_week", return_value=None),
    ):
        assert asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=TARGET)) == (dest, "pdf", PUBLIC)


def test_all_stale_permanent_candidates_fail_without_leaving_pdf(tmp_path):
    dest = tmp_path / "newtownkilleaparish.pdf"

    async def downloader(url, path):
        return _download(path, old=True, url=url)

    with (
        patch("harvester.replay._try_http_document_url", new=downloader),
        patch("harvester.bulletin_freshness.pdf_date_before_harvest_week", return_value=date(2026, 10, 25)),
        patch("harvester.replay._try_http_recipe_document_fallbacks", new_callable=AsyncMock, return_value=None),
        pytest.raises(RecipeReplayError, match="proved stale"),
    ):
        asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=TARGET))
    assert not dest.exists()


def test_stale_predicted_fallback_is_not_published(tmp_path):
    dest = tmp_path / "newtownkilleaparish.pdf"
    async def downloader(url, path):
        return None
    async def fallback(_recipe, path, _target):
        path.write_bytes(b"%PDF-1.4 old")
        return FALLBACK, "pdf"

    with (
        patch("harvester.replay._try_http_document_url", new=downloader),
        patch("harvester.replay._try_http_recipe_document_fallbacks", new=fallback),
        patch("harvester.bulletin_freshness.pdf_date_before_harvest_week", return_value=date(2026, 10, 25)),
        pytest.raises(RecipeReplayError, match="proved stale"),
    ):
        asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=TARGET))
    assert not dest.exists()
