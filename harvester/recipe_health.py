"""
recipe_health.py — Auto-flag recipes inactive from DNS site health (Phase 2).

Only marks recipes when site_health.json shows 2+ consecutive NXDOMAIN strikes.
Slow sites, HTTP-only sites, and transient errors are never auto-inactivated.
Manual ``skip`` / ``inactive`` flags on recipes are preserved.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .site_health import DEFAULT_HEALTH_PATH, load_health, should_mark_inactive

PARISHES_DIR = Path(__file__).resolve().parent.parent / "parishes"


def _recipe_paths(parishes_dir: Path) -> list[Path]:
    recipes_dir = parishes_dir / "recipes"
    if not recipes_dir.is_dir():
        return []
    return sorted(recipes_dir.glob("*.json"))


def apply_dns_inactive_flags(
    *,
    parishes_dir: Path | None = None,
    health_path: Path = DEFAULT_HEALTH_PATH,
) -> dict[str, object]:
    """
    Set ``status: inactive`` on recipes whose parish has DNS-dead health.

    Returns summary with keys: checked, flagged, skipped_manual.
    """
    parishes_dir = parishes_dir or PARISHES_DIR
    health = load_health(health_path)
    parishes_health: dict = health.get("parishes") or {}

    checked = 0
    flagged: list[str] = []
    skipped_manual: list[str] = []

    for recipe_path in _recipe_paths(parishes_dir):
        try:
            meta = json.loads(recipe_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue

        key = str(meta.get("parish_key") or recipe_path.stem).strip()
        if not key:
            continue
        checked += 1

        if meta.get("skip") or str(meta.get("status", "")).lower() in {
            "inactive",
            "dead_url",
            "needs_retraining",
        }:
            skipped_manual.append(key)
            continue

        health_entry = parishes_health.get(key)
        if not isinstance(health_entry, dict) or not should_mark_inactive(health_entry):
            continue

        meta["status"] = "inactive"
        meta["inactive_reason"] = "dns_nxdomain_2_strike"
        meta["inactive_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
        recipe_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        flagged.append(key)

    return {
        "checked": checked,
        "flagged": flagged,
        "skipped_manual": skipped_manual,
    }
