"""Check that Glencolmcille's MCN backup never publishes an old issue."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from harvester.bulletin_freshness import FreshnessVerdict
from harvester.replay import replay_recipe


REPO = Path(__file__).resolve().parents[1]
RECIPE = REPO / "parishes/recipes/raphoe/glencolmcille.json"


def _camera():
    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
    assert recipe["site_type"] == "html_current_accordion"
    assert recipe["mcn_church_id"] == 661
    return recipe["alternative_mcn_camera_url"]


def test_current_mcn_newsletter_is_accepted_without_browser(tmp_path):
    camera = _camera()
    dest = tmp_path / "glencolmcille.pdf"
    url = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/661/NewsLetter/new.pdf?bulletin_date=2026-11-15"
    with (
        patch("harvester.replay._try_mcn_live_newsletter", new_callable=AsyncMock, return_value=(url, "pdf")) as fetch,
        patch("harvester.bulletin_freshness.pdf_body_heading_verdict", return_value=None),
    ):
        result = asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=date(2026, 11, 15)))
    assert result == (dest, "pdf", url)
    fetch.assert_awaited_once_with(camera, dest, church_id_hint=661)


@pytest.mark.parametrize("date_suffix", ["2026-11-08", "2026-10-25", "2026-11-01"])
def test_old_mcn_card_is_not_accepted_and_html_is_attempted(tmp_path, date_suffix):
    _camera()
    dest = tmp_path / "glencolmcille.pdf"
    dest.write_bytes(b"stale simulated PDF")
    url = f"https://d3gxiup807zlof.cloudfront.net/live/Uploads/661/NewsLetter/old.pdf?bulletin_date={date_suffix}"
    browser = type("Browser", (), {})()
    browser.new_context = AsyncMock(side_effect=RuntimeError("HTML accordion fallback was reached"))
    with (
        patch("harvester.replay._try_mcn_live_newsletter", new_callable=AsyncMock, return_value=(url, "pdf")),
        patch("harvester.bulletin_freshness.pdf_body_heading_verdict", return_value=None),
        pytest.raises(RuntimeError, match="HTML accordion fallback was reached"),
    ):
        asyncio.run(replay_recipe(RECIPE, dest, browser, target_date=date(2026, 11, 15)))
    assert not dest.exists(), "Old MCN PDF must be removed before the HTML fallback"


def test_new_mcn_card_does_not_overrule_stale_printed_heading(tmp_path):
    _camera()
    dest = tmp_path / "glencolmcille.pdf"
    dest.write_bytes(b"PDF with stale masthead")
    url = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/661/NewsLetter/new.pdf?bulletin_date=2026-11-15"
    browser = type("Browser", (), {})()
    browser.new_context = AsyncMock(side_effect=RuntimeError("HTML accordion fallback was reached"))
    with (
        patch("harvester.replay._try_mcn_live_newsletter", new_callable=AsyncMock, return_value=(url, "pdf")),
        patch("harvester.bulletin_freshness.pdf_body_heading_verdict", return_value=FreshnessVerdict(status="stale", reason="printed_old")),
        pytest.raises(RuntimeError, match="HTML accordion fallback was reached"),
    ):
        asyncio.run(replay_recipe(RECIPE, dest, browser, target_date=date(2026, 11, 15)))
    assert not dest.exists()


def test_undated_mcn_pdf_needs_fresh_printed_issue(tmp_path):
    _camera()
    dest = tmp_path / "glencolmcille.pdf"
    url = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/661/NewsLetter/opaque.pdf"
    with (
        patch("harvester.replay._try_mcn_live_newsletter", new_callable=AsyncMock, return_value=(url, "pdf")),
        patch("harvester.bulletin_freshness.pdf_body_heading_verdict", return_value=FreshnessVerdict(status="fresh", extracted_date=date(2026, 11, 15))),
    ):
        result = asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=date(2026, 11, 15)))
    assert result == (dest, "pdf", url)
