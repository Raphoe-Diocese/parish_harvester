from pathlib import Path

from harvester.fetcher import _load_recipe_metadata, _trained_recipe_exists
from harvester.replay import load_recipe


def test_kiltubrid_html_capture_is_visible_to_replay_and_fetcher():
    path = Path(__file__).resolve().parents[1] / "parishes/recipes/ardagh/kiltubrid.json"
    recipe = load_recipe(path)
    assert recipe["site_type"] == "html_text_bulletin"
    assert _load_recipe_metadata(path) == recipe
    assert _trained_recipe_exists(path, recipe)
