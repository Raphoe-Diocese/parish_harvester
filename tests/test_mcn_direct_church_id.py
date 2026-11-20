"""MCN newsletter retrieval must work when camera HTML is inaccessible."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from harvester.replay import _mcn_fetch_newsletter_url, replay_recipe


CAMERA = "https://mcn.live/Camera/our-lady-of-perpetual-succour-glenfinn"
RECIPE = Path(__file__).resolve().parents[1] / "parishes/recipes/raphoe/glenfin-parish.json"
TARGET = date(2026, 11, 15)


def _api_response():
    response = Mock()
    response.read.return_value = b'{"newsletter":{}}'
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=None)
    return context


def test_known_mcn_church_id_uses_api_without_fetching_camera_html():
    pdf = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/NewsLetter/current.pdf"
    with (
        patch("harvester.replay._fetch_bytes_with_retries", side_effect=AssertionError("No camera fetch expected")),
        patch("harvester.replay.urlopen", return_value=_api_response()) as open_api,
        patch("harvester.replay.mcn_newsletter_url_from_profile", return_value=pdf),
        patch("harvester.replay.mcn_newsletter_stated_date", return_value=TARGET),
    ):
        result = _mcn_fetch_newsletter_url(CAMERA, 164)
    assert result == (pdf, TARGET)
    req = open_api.call_args.args[0]
    assert req.full_url.endswith("/Website/ProfileDataByJson/164")
    assert req.get_method() == "POST"


def test_unknown_id_still_uses_camera_html_discovery():
    with patch("harvester.replay._fetch_bytes_with_retries", return_value=None) as cam:
        assert _mcn_fetch_newsletter_url(CAMERA) is None
    cam.assert_called_once()


def test_mcn_hint_disallowed_on_untrusted_hosts():
    with (
        patch("harvester.replay._fetch_bytes_with_retries", side_effect=AssertionError("Must not fetch")),
        patch("harvester.replay.urlopen", side_effect=AssertionError("Must not post")),
    ):
        assert _mcn_fetch_newsletter_url("https://example.org/Camera/glencolmcille", 164) is None
        assert _mcn_fetch_newsletter_url("https://mcn.live.evil.example/Camera/x", 164) is None
        assert _mcn_fetch_newsletter_url("http://mcn.live/Camera/x", 164) is None


def test_invalid_id_is_never_sent_to_api_without_camera_proof():
    with patch("harvester.replay._fetch_bytes_with_retries", return_value=None) as camera:
        assert _mcn_fetch_newsletter_url(CAMERA, -3) is None
    camera.assert_called_once()


def test_glenfin_replay_passes_recipe_mcn_id_to_fetcher(tmp_path):
    dest = tmp_path / "glenfin-parish.pdf"
    url = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/164/NewsLetter/new.pdf?bulletin_date=2026-11-15"
    with patch("harvester.replay._try_mcn_live_newsletter", new_callable=AsyncMock, return_value=(url, "pdf")) as fetch:
        result = asyncio.run(replay_recipe(RECIPE, dest, object(), target_date=TARGET))
    assert result == (dest, "pdf", url)
    fetch.assert_awaited_once_with(CAMERA, dest, church_id_hint=164)
