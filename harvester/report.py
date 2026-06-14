"""
report.py — Simple report generator for the Parish Bulletin Harvester.

Moves downloaded PDFs to current/, writes report.json with
downloaded/html_links/failed counts.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetcher import FetchResult

PARISHES_DIR = Path(__file__).resolve().parent.parent / "parishes"


def _recipe_is_inactive(meta: dict | None) -> bool:
    if not isinstance(meta, dict):
        return False
    status = str(meta.get("status", "")).strip().lower()
    return bool(meta.get("skip")) or status in {"dead_url", "inactive"}


def _load_recipe_meta_for_key(parish_key: str, parishes_dir: Path) -> dict:
    from .replay import recipe_path_for

    path = recipe_path_for(parish_key, parishes_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def reconcile_report_with_recipes(report: dict, parishes_dir: Path | None = None) -> dict:
    """
    Drop stale problem rows that recipes or harvest results have already resolved.

    - Parishes in ``downloaded`` are removed from ``failed`` / ``html_links``.
    - Parishes with inactive/dead recipes move from ``failed`` to ``skipped``.
    """
    if not isinstance(report, dict):
        return report

    parishes_dir = parishes_dir or PARISHES_DIR
    downloaded_keys = {
        str(item.get("parish") or "").strip()
        for item in (report.get("downloaded") or [])
        if isinstance(item, dict) and item.get("parish")
    }

    kept_failed: list[dict] = []
    moved_skipped: list[dict] = []
    skipped = [
        item for item in (report.get("skipped") or [])
        if isinstance(item, dict)
    ]
    skipped_keys = {
        str(item.get("parish") or "").strip()
        for item in skipped
        if item.get("parish")
    }

    for item in report.get("failed") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("parish") or "").strip()
        if not key:
            continue
        if key in downloaded_keys:
            continue

        meta = _load_recipe_meta_for_key(key, parishes_dir)
        if _recipe_is_inactive(meta):
            if key not in skipped_keys:
                moved_skipped.append({
                    "parish": key,
                    "display_name": (
                        item.get("display_name")
                        or meta.get("display_name")
                        or key
                    ),
                    "url": item.get("url") or meta.get("start_url") or "",
                    "reason": str(
                        meta.get("reason")
                        or meta.get("dead_reason")
                        or meta.get("inactive_reason")
                        or "Marked inactive"
                    ).strip(),
                })
                skipped_keys.add(key)
            continue

        kept_failed.append(item)

    report["failed"] = kept_failed

    html_links = [
        item for item in (report.get("html_links") or [])
        if isinstance(item, dict)
        and str(item.get("parish") or "").strip() not in downloaded_keys
    ]
    report["html_links"] = html_links
    report["skipped"] = skipped + moved_skipped
    _recompute_summary(report)
    return report


def generate_report(
    results: list["FetchResult"],
    raw_dir: Path,
    current_dir: Path,
    report_json: Path,
    report_txt: Path,
    target: date,
) -> dict:
    """
    Move downloaded PDFs from raw_dir to current_dir, write report files.

    Returns a summary dict with keys: downloaded, html_links, skipped, failed.
    """
    current_dir.mkdir(parents=True, exist_ok=True)

    # Purge stale PDFs from previous runs so the mega PDF only contains
    # this week's bulletins (fixes "mega PDF includes all previous weeks").
    for stale in current_dir.glob("*.pdf"):
        try:
            stale.unlink()
        except OSError:
            pass

    downloaded: list[dict] = []
    html_links: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    stale_rejected: list[dict] = []

    for r in results:
        if r.is_stale:
            stale_rejected.append({
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
                "reason": r.stale_reason,
                "retry_strategy": r.retry_strategy,
                "error": r.error,
            })
            continue
        if r.status == "ok" and r.file_path and r.file_path.exists():
            dest = current_dir / r.file_path.name
            shutil.copy2(r.file_path, dest)
            entry = {
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
                "file": dest.name,
                "file_type": r.file_type,
            }
            downloaded.append(entry)
        elif r.status == "html_link":
            html_links.append({
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
            })
        elif r.status == "skipped":
            skipped.append({
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
                "reason": r.error,
            })
        else:
            failed.append({
                "parish": r.key,
                "display_name": r.display_name,
                "url": r.url,
                "error": r.error,
            })

    report = {
        "target_date": str(target),
        "summary": {
            "downloaded": len(downloaded),
            "html_links": len(html_links),
            "skipped": len(skipped),
            "failed": len(failed),
            "stale_rejected": len(stale_rejected),
        },
        "downloaded": downloaded,
        "html_links": html_links,
        "skipped": skipped,
        "failed": failed,
        "stale_rejected": stale_rejected,
    }

    reconcile_report_with_recipes(report)

    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"Parish Bulletin Harvest Report — {target}",
        "=" * 50,
        f"Downloaded : {len(downloaded)}",
        f"HTML links : {len(html_links)}",
        f"Skipped    : {len(skipped)}",
        f"Failed     : {len(failed)}",
        f"Stale rej. : {len(stale_rejected)}",
        "",
    ]
    if downloaded:
        lines += ["Downloaded bulletins:", ""]
        for d in downloaded:
            lines.append(f"  ✅ {d['display_name']} — {d['file']}")
        lines.append("")
    if html_links:
        lines += ["HTML-only parishes (clickable links in mega PDF):", ""]
        for h in html_links:
            lines.append(f"  🔗 {h['display_name']} — {h['url']}")
        lines.append("")
    if skipped:
        lines += ["Skipped parishes:", ""]
        for s in skipped:
            lines.append(f"  ⏭️  {s['display_name']} — {s['reason']}")
        lines.append("")
    if stale_rejected:
        lines += ["Stale bulletins rejected from mega PDF:", ""]
        for s in stale_rejected:
            lines.append(
                f"  🕐 {s['display_name']} — {s['error']} "
                f"(retry: {s['retry_strategy']})"
            )
        lines.append("")
    if failed:
        lines += ["Failed parishes:", ""]
        for f_item in failed:
            lines.append(f"  ❌ {f_item['display_name']} — {f_item['error']}")
        lines.append("")

    report_txt.write_text("\n".join(lines), encoding="utf-8")

    return report


def _result_to_report_entry(r: "FetchResult", current_dir: Path) -> tuple[str, dict | None]:
    """Map one FetchResult to (bucket, entry) where bucket is a report section key."""
    if r.is_stale:
        return "stale_rejected", {
            "parish": r.key,
            "display_name": r.display_name,
            "url": r.url,
            "reason": r.stale_reason,
            "retry_strategy": r.retry_strategy,
            "error": r.error,
        }
    if r.status == "ok" and r.file_path and r.file_path.exists():
        dest = current_dir / r.file_path.name
        current_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(r.file_path, dest)
        return "downloaded", {
            "parish": r.key,
            "display_name": r.display_name,
            "url": r.url,
            "file": dest.name,
            "file_type": r.file_type,
        }
    if r.status == "html_link":
        return "html_links", {
            "parish": r.key,
            "display_name": r.display_name,
            "url": r.url,
        }
    if r.status == "skipped":
        return "skipped", {
            "parish": r.key,
            "display_name": r.display_name,
            "url": r.url,
            "reason": r.error,
        }
    return "failed", {
        "parish": r.key,
        "display_name": r.display_name,
        "url": r.url,
        "error": r.error,
    }


def _remove_parish_from_sections(report: dict, parish_key: str) -> None:
    key = (parish_key or "").strip()
    if not key:
        return
    for section in ("downloaded", "html_links", "skipped", "failed", "stale_rejected"):
        items = report.get(section)
        if not isinstance(items, list):
            continue
        report[section] = [item for item in items if item.get("parish") != key]


def _recompute_summary(report: dict) -> None:
    report["summary"] = {
        "downloaded": len(report.get("downloaded") or []),
        "html_links": len(report.get("html_links") or []),
        "skipped": len(report.get("skipped") or []),
        "failed": len(report.get("failed") or []),
        "stale_rejected": len(report.get("stale_rejected") or []),
    }


def patch_report_for_parishes(
    results: list["FetchResult"],
    report_json: Path,
    report_txt: Path,
    target: date,
    *,
    current_dir: Path,
) -> dict | None:
    """
    Merge one or more parish results into an existing report.json.

    Used by instant single-parish rebuilds so the Problems tab and GitHub
    report reflect the latest harvest attempt without a full diocese run.
    """
    if not results:
        return None

    if report_json.exists():
        try:
            report = json.loads(report_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            report = None
    else:
        report = None

    if not isinstance(report, dict):
        report = {
            "target_date": str(target),
            "summary": {
                "downloaded": 0,
                "html_links": 0,
                "skipped": 0,
                "failed": 0,
                "stale_rejected": 0,
            },
            "downloaded": [],
            "html_links": [],
            "skipped": [],
            "failed": [],
            "stale_rejected": [],
        }

    report["target_date"] = str(target)

    for r in results:
        _remove_parish_from_sections(report, r.key)
        bucket, entry = _result_to_report_entry(r, current_dir)
        if entry is None:
            continue
        section = report.setdefault(bucket, [])
        if isinstance(section, list):
            section.append(entry)

    _recompute_summary(report)
    reconcile_report_with_recipes(report)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        f"Parish Bulletin Harvest Report — {target}",
        "=" * 50,
        f"Downloaded : {report['summary']['downloaded']}",
        f"HTML links : {report['summary']['html_links']}",
        f"Skipped    : {report['summary']['skipped']}",
        f"Failed     : {report['summary']['failed']}",
        f"Stale rej. : {report['summary']['stale_rejected']}",
        "",
    ]
    for label, key, icon in (
        ("Downloaded bulletins", "downloaded", "✅"),
        ("HTML-only parishes", "html_links", "🔗"),
        ("Skipped parishes", "skipped", "⏭️"),
        ("Failed parishes", "failed", "❌"),
        ("Stale bulletins rejected", "stale_rejected", "🕐"),
    ):
        items = report.get(key) or []
        if not items:
            continue
        lines.append(f"{label}:")
        lines.append("")
        for item in items:
            name = item.get("display_name") or item.get("parish") or "?"
            if key == "downloaded":
                lines.append(f"  {icon} {name} — {item.get('file', '')}")
            elif key == "failed":
                lines.append(f"  {icon} {name} — {item.get('error', '')}")
            else:
                lines.append(f"  {icon} {name} — {item.get('url', item.get('reason', ''))}")
        lines.append("")

    report_txt.write_text("\n".join(lines), encoding="utf-8")
    return report
