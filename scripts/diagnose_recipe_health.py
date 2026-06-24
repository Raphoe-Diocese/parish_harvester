#!/usr/bin/env python3
"""Audit parish recipes and harvest health — run without the browser extension.

Usage:
  py -3 scripts/diagnose_recipe_health.py
  py -3 scripts/diagnose_recipe_health.py threepatrons clonmanyparish
  py -3 scripts/diagnose_recipe_health.py --json > diag.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECIPES_ROOT = REPO / "parishes" / "recipes"
FAILURES_PATH = REPO / "parishes" / "consecutive_failures.json"
REPORT_PATH = REPO / "Bulletins" / "report.json"

TERMINAL = {"download", "image", "image_stack", "print_to_pdf", "html", "crop_screenshot"}
BAD_DL = re.compile(
    r"privacy|gdpr|gift.?aid|dataentry|financial|safeguarding|standingorder|donation|downandconnor",
    re.I,
)
DATED_SELECTOR = re.compile(
    r"\d{4}[-_]\d{2}[-_]\d{2}|june|january|february|march|april|may|july|august|september|october|november|december",
    re.I,
)


def _load_json(path: Path) -> dict | list | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (OSError, json.JSONDecodeError):
        return None


def _iter_recipes(keys: list[str] | None = None):
    if not RECIPES_ROOT.is_dir():
        return
    for dio_dir in sorted(RECIPES_ROOT.iterdir()):
        if not dio_dir.is_dir():
            continue
        for path in sorted(dio_dir.glob("*.json")):
            key = path.stem.lower()
            if keys and key not in keys:
                continue
            recipe = _load_json(path)
            if isinstance(recipe, dict):
                yield key, path, recipe


def _analyze_recipe(key: str, path: Path, recipe: dict) -> list[dict]:
    issues: list[dict] = []
    steps = recipe.get("steps") if isinstance(recipe.get("steps"), list) else []
    actions = [str(s.get("action", "")).strip().lower() for s in steps if isinstance(s, dict)]
    start_url = str(recipe.get("start_url") or "").strip()
    site_type = str(recipe.get("site_type") or "")
    playbook = str(recipe.get("playbook_type") or "")

    if not steps:
        issues.append(
            {
                "severity": "error",
                "code": "empty_recipe",
                "parish": key,
                "file": str(path.relative_to(REPO)),
                "message": "Recipe has no steps",
                "fix": "Train with the Parish Trainer extension and push.",
            }
        )
        return issues

    clicks = sum(1 for a in actions if a == "click")
    has_terminal = any(a in TERMINAL for a in actions)

    if clicks and not has_terminal:
        issues.append(
            {
                "severity": "error",
                "code": "click_only",
                "parish": key,
                "file": str(path.relative_to(REPO)),
                "message": f"{clicks} click step(s) but no download/print/image terminal step",
                "fix": "Add download or print_to_pdf after the bulletin link.",
            }
        )

    if "mdocs" in site_type or "mdocs" in playbook:
        if "print_to_pdf" in actions:
            issues.append(
                {
                    "severity": "error",
                    "code": "mdocs_print",
                    "parish": key,
                    "file": str(path.relative_to(REPO)),
                    "message": "mDocs recipe uses print_to_pdf — must use real PDF download",
                    "fix": "Re-train: click Download on mDocs row, capture PDF download.",
                }
            )

    if site_type in ("sequential_bulletin_number", "joomla_dropfiles") and "download" not in actions:
        issues.append(
            {
                "severity": "warn",
                "code": "weekly_no_download",
                "parish": key,
                "file": str(path.relative_to(REPO)),
                "message": "Weekly/Joomla Dropfiles recipe missing download step",
                "fix": "Record cloud ↓ download on this Sunday's row.",
            }
        )

    if "portstewartparish.website" in start_url and start_url.startswith("https://"):
        issues.append(
            {
                "severity": "warn",
                "code": "portstewart_https",
                "parish": key,
                "file": str(path.relative_to(REPO)),
                "message": "Portstewart start_url uses HTTPS — certificate expired",
                "fix": "Use http://portstewartparish.website",
            }
        )

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action", "")).lower()
        url = str(step.get("url") or step.get("href") or step.get("captured_url") or "")
        selector = str(step.get("selector") or "")

        if action == "download" and url and BAD_DL.search(url):
            issues.append(
                {
                    "severity": "error",
                    "code": "bad_download_url",
                    "parish": key,
                    "file": str(path.relative_to(REPO)),
                    "message": f"Download URL looks like admin/GDPR PDF: {url[:90]}",
                    "fix": "Re-train on parish bulletin row only.",
                }
            )

        if action == "click" and DATED_SELECTOR.search(selector):
            issues.append(
                {
                    "severity": "warn",
                    "code": "dated_selector",
                    "parish": key,
                    "file": str(path.relative_to(REPO)),
                    "message": f"Click selector may pin a dated filename: {selector[:80]}",
                    "fix": "Use newest-dated link pick, not a hardcoded June-2026 filename.",
                }
            )

        if i > 0 and action == "click":
            prev = steps[i - 1]
            if (
                isinstance(prev, dict)
                and str(prev.get("action", "")).lower() == "click"
                and str(prev.get("text", "")).strip() == str(step.get("text", "")).strip()
                and str(prev.get("text", "")).strip()
            ):
                issues.append(
                    {
                        "severity": "warn",
                        "code": "duplicate_click",
                        "parish": key,
                        "file": str(path.relative_to(REPO)),
                        "message": f'Duplicate click steps for "{str(step.get("text", ""))[:50]}"',
                        "fix": "Remove duplicate click in extension or edit recipe JSON.",
                    }
                )
                break

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose parish recipe health in this repo.")
    parser.add_argument("parishes", nargs="*", help="Parish keys to check (default: all)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()
    keys = [k.lower().replace(" ", "_") for k in args.parishes] if args.parishes else None

    failures = _load_json(FAILURES_PATH)
    failures = failures if isinstance(failures, dict) else {}
    report = _load_json(REPORT_PATH)
    report = report if isinstance(report, dict) else {}

    all_issues: list[dict] = []
    checked = 0

    for key, path, recipe in _iter_recipes(keys):
        checked += 1
        all_issues.extend(_analyze_recipe(key, path, recipe))

        streak = int(failures.get(key, 0) or 0)
        if streak >= 3:
            all_issues.append(
                {
                    "severity": "error",
                    "code": "harvest_streak",
                    "parish": key,
                    "file": str(FAILURES_PATH.relative_to(REPO)),
                    "message": f"{streak} consecutive harvest failures",
                    "fix": "Retrain recipe on live site, then Send & test.",
                }
            )
        elif streak >= 1:
            all_issues.append(
                {
                    "severity": "warn",
                    "code": "harvest_fail",
                    "parish": key,
                    "file": str(FAILURES_PATH.relative_to(REPO)),
                    "message": f"{streak} consecutive failure(s) on record",
                    "fix": "Check Bulletins/report.json and retrain if layout changed.",
                }
            )

        failed_row = next((r for r in report.get("failed", []) if r.get("parish") == key), None)
        if failed_row:
            reason = str(failed_row.get("reason") or failed_row.get("error") or "")[:160]
            if reason:
                all_issues.append(
                    {
                        "severity": "warn",
                        "code": "last_harvest_failed",
                        "parish": key,
                        "file": str(REPORT_PATH.relative_to(REPO)),
                        "message": f"Last harvest failed: {reason}",
                        "fix": "Open parish in trainer and run diagnosis kit.",
                    }
                )

    if args.json:
        print(
            json.dumps(
                {
                    "checked_recipes": checked,
                    "issue_count": len(all_issues),
                    "issues": all_issues,
                },
                indent=2,
            )
        )
        return 1 if any(i["severity"] == "error" for i in all_issues) else 0

    print("Parish harvester — recipe health diagnosis")
    print("=========================================")
    print(f"Recipes checked: {checked}")
    print(f"Issues found: {len(all_issues)}")
    print()

    if not all_issues:
        print("No issues detected.")
        return 0

    by_sev = {"error": 0, "warn": 0}
    for item in all_issues:
        by_sev[item["severity"]] = by_sev.get(item["severity"], 0) + 1
    print(f"Errors: {by_sev.get('error', 0)} · Warnings: {by_sev.get('warn', 0)}")
    print()

    for item in all_issues:
        icon = "ERROR" if item["severity"] == "error" else "WARN "
        print(f"[{icon}] {item['parish']}: {item['message']}")
        print(f"        file: {item['file']}")
        print(f"        fix:  {item['fix']}")
        print()

    return 1 if by_sev.get("error", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
