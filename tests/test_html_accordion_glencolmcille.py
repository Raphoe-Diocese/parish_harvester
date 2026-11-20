"""Fail-closed regression checks for Glencolmcille HTML accordion capture."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from harvester.html_accordion import (
    _ISOLATE_CURRENT_ACCORDION_JS,
    isolate_current_accordion_bulletin,
)


REPO = Path(__file__).resolve().parents[1]
RECIPE = REPO / "parishes/recipes/raphoe/glencolmcille.json"
EVIDENCE = REPO / "parishes/raphoe_diocese_bulletin_urls.txt"
CONTACTS = REPO / "parishes/raphoe_diocese_contacts.json"


def test_source_and_recipe_are_registered_once():
    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
    source = "https://carrickonline.net/links/st-columbas-church-newsletter"
    assert recipe["parish_key"] == "glencolmcille"
    assert recipe["start_url"] == source
    assert recipe["steps"][-1]["action"] == "html"
    assert recipe["steps"][-1]["only_current_accordion"] is True
    assert source in EVIDENCE.read_text(encoding="utf-8")
    assert CONTACTS.is_file()
    assert json.loads(CONTACTS.read_text(encoding="utf-8"))["glencolmcille"]["website"] == source


def test_browser_script_isolates_one_panel_and_has_no_archive_print_fallback():
    script = _ISOLATE_CURRENT_ACCORDION_JS
    assert "replaceChildren(body)" in script
    assert "data-ph-bulletin-root" in script
    assert "innerText" in script
    assert "getAttribute('aria-controls')" in script
    assert "No isolated current-week accordion bulletin" in script


def test_current_sunday_passes_exact_date_to_browser():
    page = type("FakePage", (), {})()
    page.evaluate = AsyncMock(return_value={"ok": True, "chars": 580, "heading": "14 / 15 November 2026"})
    found = asyncio.run(isolate_current_accordion_bulletin(page, date(2026, 11, 15)))
    assert found["heading"] == "14 / 15 November 2026"
    script, args = page.evaluate.await_args.args
    assert script == _ISOLATE_CURRENT_ACCORDION_JS
    assert args == {"sunday": 15, "month": "november", "monthAbbr": "nov", "year": 2026}


def test_no_current_panel_fails_without_ever_printing_archive():
    page = type("FakePage", (), {})()
    page.evaluate = AsyncMock(return_value={"ok": False, "reason": "No current Sunday found"})
    with pytest.raises(ValueError, match="No current Sunday"):
        asyncio.run(isolate_current_accordion_bulletin(page, date(2026, 11, 15)))


def test_short_or_invalid_browser_result_fails_closed():
    page = type("FakePage", (), {})()
    page.evaluate = AsyncMock(return_value={"ok": True, "chars": 74})
    with pytest.raises(ValueError, match="too short"):
        asyncio.run(isolate_current_accordion_bulletin(page, date(2026, 11, 15)))
    page.evaluate = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="Invalid browser result"):
        asyncio.run(isolate_current_accordion_bulletin(page, date(2026, 11, 15)))


def test_wrong_day_cannot_get_printed_as_current():
    page = type("FakePage", (), {})()
    page.evaluate = AsyncMock()
    with pytest.raises(ValueError, match="Sunday"):
        asyncio.run(isolate_current_accordion_bulletin(page, date(2026, 11, 16)))
    page.evaluate.assert_not_awaited()
