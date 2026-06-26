#!/usr/bin/env python3
"""Build a training backlog from harvest report + recipes + learned patterns.

Preserves operator/training metadata already in the repo and adds actionable
next steps so retraining time is spent only where needed.

Usage:
  py -3 scripts/build_training_backlog.py
  py -3 scripts/build_training_backlog.py --json
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECIPES = REPO / "parishes" / "recipes"
REPORT = REPO / "Bulletins" / "report.json"
PATTERNS = REPO / "parishes" / "site_patterns.json"
HOSTS = REPO / "parishes" / "host_profiles.json"
TRAINING_DIAG = REPO / "parishes" / "training_diagnosis"
OUTPUT = REPO / "parishes" / "training_backlog.json"

TERMINAL = {"download", "image", "image_stack", "print_to_pdf", "html", "crop_screenshot"}


def _load(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_recipes() -> list[tuple[str, Path, dict]]:
    out: list[tuple[str, Path, dict]] = []
    for dio_dir in sorted(RECIPES.iterdir()):
        if not dio_dir.is_dir():
            continue
        for path in sorted(dio_dir.glob("*.json")):
            data = _load(path)
            if isinstance(data, dict):
                out.append((path.stem.lower(), path, data))
    return out


def _recipe_summary(recipe: dict) -> dict:
    steps = recipe.get("steps") if isinstance(recipe.get("steps"), list) else []
    actions = [str(s.get("action", "")).lower() for s in steps if isinstance(s, dict)]
    return {
        "start_url": recipe.get("start_url") or "",
        "site_type": recipe.get("site_type") or "",
        "playbook_type": recipe.get("playbook_type") or "",
        "status": recipe.get("status") or "",
        "skip": bool(recipe.get("skip")),
        "placeholder": bool(recipe.get("placeholder")),
        "step_count": len(steps),
        "click_count": sum(1 for a in actions if a == "click"),
        "has_terminal": any(a in TERMINAL for a in actions),
        "operator_notes": recipe.get("operator_notes") or [],
        "do_not": recipe.get("do_not") or [],
        "recorded_date": recipe.get("recorded_date") or "",
    }


def _suggest_action(key: str, recipe: dict, fail_row: dict | None) -> tuple[str, str]:
    if recipe.get("skip") or recipe.get("status") in ("dead_url", "inactive"):
        return "skip", recipe.get("dead_reason") or recipe.get("reason") or "marked skip"
    if recipe.get("placeholder"):
        return "retrain", recipe.get("retraining_reason") or "placeholder recipe"
    err = (fail_row or {}).get("error") or ""
    low = err.lower()
    if "outdated" in low or "selectors failed" in low:
        return "retrain", "outdated selectors"
    if "stub recipe" in low:
        return "retrain", "stub from April"
    if "facebook" in low or "admin/non-bulletin" in low:
        return "mark_inactive", "non-automatable source"
    if "google drive" in low or "drive.usercontent" in low:
        return "autofix_drive", "needs direct Drive file URL"
    if "image_stack" in low or "mcn.live" in low:
        return "retrain_image", "image capture recipe"
    if "timeout" in low and recipe.get("auto_fixed"):
        return "verify_autofix", "retry after recipe autofix"
    if fail_row:
        return "investigate", err[:160]
    return "ok", "downloaded or not in failure list"


def _pattern_for_key(patterns: dict, key: str) -> dict | None:
    for _pid, pdata in (patterns.get("patterns") or {}).items():
        examples = [str(x).lower() for x in pdata.get("example_parishes") or []]
        if key in examples:
            return pdata
    return None


def _infer_bulletin_format(recipe: dict, pattern: dict | None) -> str:
    site = str(recipe.get("site_type") or "").lower()
    playbook = str(recipe.get("playbook_type") or "").lower()
    if "image_stack" in site or "stacked_image" in playbook:
        return "image_stack"
    if "html" in site or "html_capture" in playbook:
        return "html"
    if "docx" in site or "dropfiles" in playbook:
        return "word"
    if pattern:
        flow = str(pattern.get("recipe_flow") or "")
        if "html" in flow:
            return "html"
        if "image" in flow:
            return "image"
    steps = recipe.get("steps") or []
    for step in steps:
        if isinstance(step, dict):
            action = str(step.get("action") or "").lower()
            if action in TERMINAL:
                return action
    return "pdf_download"


def build_backlog() -> dict:
    report = _load(REPORT) if REPORT.is_file() else {}
    patterns_lib = _load(PATTERNS) if PATTERNS.is_file() else {}
    hosts = _load(HOSTS) if HOSTS.is_file() else {}

    failed = {
        row["parish"]: row
        for row in (report.get("failed") or [])
        if isinstance(row, dict) and row.get("parish")
    }
    skipped = {
        row["parish"]: row
        for row in (report.get("skipped") or [])
        if isinstance(row, dict) and row.get("parish")
    }

    parishes: list[dict] = []
    counts: dict[str, int] = {}

    for key, path, recipe in _iter_recipes():
        rel = str(path.relative_to(REPO)).replace("\\", "/")
        pattern = _pattern_for_key(patterns_lib, key) if isinstance(patterns_lib, dict) else None
        fail_row = failed.get(key)
        skip_row = skipped.get(key)
        action, reason = _suggest_action(key, recipe, fail_row or skip_row)

        host = ""
        start = str(recipe.get("start_url") or "")
        if start.startswith("http"):
            host = re.sub(r"^www\.", "", start.split("/")[2].lower())

        diag_path = TRAINING_DIAG / f"{key}.json"
        has_training_diag = diag_path.is_file()

        entry = {
            "parish_key": key,
            "display_name": recipe.get("display_name") or key,
            "diocese": recipe.get("diocese") or path.parent.name,
            "recipe_file": rel,
            "recipe": _recipe_summary(recipe),
            "bulletin_format": _infer_bulletin_format(recipe, pattern),
            "learned_pattern": pattern.get("label") if pattern else "",
            "host_profile": (hosts.get("hosts") or {}).get(host) if isinstance(hosts, dict) else None,
            "has_extension_diagnosis": has_training_diag,
            "harvest_status": (
                "failed" if fail_row else "skipped" if skip_row else "unknown"
            ),
            "last_error": (fail_row or skip_row or {}).get("error", "")[:240],
            "suggested_action": action,
            "suggested_reason": reason,
        }
        parishes.append(entry)
        counts[action] = counts.get(action, 0) + 1

    parishes.sort(key=lambda r: (r["suggested_action"] != "retrain", r["display_name"].lower()))

    return {
        "generated_at": date.today().isoformat(),
        "target_date": report.get("target_date") if isinstance(report, dict) else "",
        "summary": report.get("summary") if isinstance(report, dict) else {},
        "action_counts": counts,
        "parishes": parishes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout only")
    args = parser.parse_args()

    backlog = build_backlog()
    OUTPUT.write_text(json.dumps(backlog, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(backlog, indent=2))
    else:
        counts = backlog.get("action_counts") or {}
        print(f"Wrote {OUTPUT.relative_to(REPO)}")
        for action, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {action:18s} {n}")
        retrain = [p for p in backlog["parishes"] if p["suggested_action"] == "retrain"]
        if retrain:
            print("\nRetrain priority:")
            for row in retrain[:15]:
                print(f"  - {row['display_name']} ({row['bulletin_format']}) — {row['suggested_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
