"""Tests for harvester.recipe_health — recipes live under diocese subfolders."""
from __future__ import annotations

import json

from harvester.recipe_health import _recipe_paths, apply_dns_inactive_flags


def _write_recipe(path, **fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")


def test_recipe_paths_finds_recipes_in_diocese_subfolders(tmp_path):
    parishes_dir = tmp_path / "parishes"
    _write_recipe(parishes_dir / "recipes" / "raphoe" / "ardara.json", parish_key="ardara")
    _write_recipe(parishes_dir / "recipes" / "derry" / "banagherparish.json", parish_key="banagherparish")

    found = _recipe_paths(parishes_dir)

    assert len(found) == 2
    assert {p.name for p in found} == {"ardara.json", "banagherparish.json"}


def test_apply_dns_inactive_flags_checks_nested_recipes(tmp_path):
    parishes_dir = tmp_path / "parishes"
    recipe_path = parishes_dir / "recipes" / "derry" / "deadparish.json"
    _write_recipe(recipe_path, parish_key="deadparish", start_url="https://deadparish.example/")

    health_path = tmp_path / "site_health.json"
    health_path.write_text(
        json.dumps(
            {
                "parishes": {
                    "deadparish": {"nxdomain_strikes": 2, "last_result": "nxdomain"},
                }
            }
        ),
        encoding="utf-8",
    )

    summary = apply_dns_inactive_flags(parishes_dir=parishes_dir, health_path=health_path)

    assert summary["checked"] == 1
    assert summary["flagged"] == ["deadparish"]

    updated = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert updated["status"] == "inactive"
    assert updated["inactive_reason"] == "dns_nxdomain_2_strike"
