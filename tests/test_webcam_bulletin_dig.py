"""Unit tests for the webcam bulletin digger (no live network)."""

from __future__ import annotations

import json
from pathlib import Path

from harvester.webcam_bulletin_dig import (
    churchmedia_slugs_from_recipes,
    dig_churchmedia_slug,
    parse_churchservices_player_urls,
    parse_mcn_camera_paths,
)


def test_parse_mcn_camera_paths_unique() -> None:
    html = """
    <a href="/Camera/holy-cross-church">Dunfanaghy</a>
    <a href='/Camera/holy-cross-church'>again</a>
    <a href="/Camera/iskaheen-parish?x=1">Iskaheen</a>
    """
    paths = parse_mcn_camera_paths(html)
    assert paths == ["/Camera/holy-cross-church", "/Camera/iskaheen-parish"]


def test_parse_churchservices_skips_wp_noise() -> None:
    html = """
    <a href="https://www.churchservices.tv/letterkenny">LK</a>
    <a href="https://www.churchservices.tv/wp-content/uploads/x.pdf">no</a>
    <a href="https://www.churchservices.tv/timetable">no</a>
    <a href="http://www.churchservices.tv/milford/">Milford</a>
    """
    urls = parse_churchservices_player_urls(html)
    assert urls == [
        "https://www.churchservices.tv/letterkenny",
        "http://www.churchservices.tv/milford",
    ]


def test_churchmedia_slugs_from_recipes(tmp_path: Path) -> None:
    diocese = tmp_path / "down_and_connor"
    diocese.mkdir()
    (diocese / "portaferryparish.json").write_text(
        json.dumps(
            {
                "start_url": "https://churchmedia.tv/st-patricks-church-2",
                "churchmedia_slug": "st-patricks-church-2",
            }
        ),
        encoding="utf-8",
    )
    slugs = churchmedia_slugs_from_recipes(tmp_path)
    assert slugs == ["st-patricks-church-2"]


def test_dig_churchmedia_bad_slug_no_network() -> None:
    hit = dig_churchmedia_slug("not a slug!!")
    assert hit.host == "churchmedia"
    assert hit.newsletter_url is None
    assert "bad slug" in hit.note
