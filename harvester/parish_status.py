"""
parish_status.py — Single source of truth for parish harvest health.

Builds parishes/parish_status.json from report.json, evidence files,
consecutive failures, and recipe metadata. The extension Problems tab reads
this file instead of merging report + localStorage.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PARISHES_DIR, REPORT_JSON
from .fetcher import parse_evidence_file
from .report import _load_recipe_meta_for_key, _recipe_is_inactive

SCHEMA_VERSION = 1
PARISH_STATUS_PATH = PARISHES_DIR / "parish_status.json"

_DIOCESE_LABELS: dict[str, str] = {
    "clogher_diocese": "Clogher Diocese",
    "derry_diocese": "Derry Diocese",
    "down_and_connor": "Down & Connor Diocese",
    "raphoe_diocese": "Raphoe Diocese",
}

_HEADER_RE = re.compile(r"^#\s*-{2,}\s*(.+?)\s*-{2,}\s*$", re.IGNORECASE)


def _diocese_label(stem: str) -> str:
    key = stem.removesuffix("_bulletin_urls")
    return _DIOCESE_LABELS.get(key, key.replace("_", " ").title())


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _parse_disabled_keys(parishes_dir: Path) -> set[str]:
    """Return parish keys marked DISABLED in evidence files."""
    disabled: set[str] = set()
    for path in sorted(parishes_dir.glob("*_bulletin_urls.txt")):
        diocese_stem = path.stem.replace("_bulletin_urls", "")
        cur_name: str | None = None
        cur_key: str | None = None
        is_disabled = False

        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            header = _HEADER_RE.match(line)
            if header:
                if cur_name and is_disabled and cur_key:
                    disabled.add(cur_key)
                cur_name = header.group(1).strip()
                cur_key = None
                is_disabled = False
                continue
            if not cur_name:
                continue
            if line.startswith("#"):
                ll = line.lower()
                if ll.startswith("# key:"):
                    cur_key = line.split(":", 1)[1].strip()
                elif re.match(r"^#\s*disabled", ll):
                    is_disabled = True
                continue
            if line.startswith("http") and not cur_key:
                from .fetcher import _url_to_key

                cur_key = _url_to_key(line, cur_name)

        if cur_name and is_disabled and cur_key:
            disabled.add(cur_key)
    return disabled


def _failure_category(error_text: str, diagnosis: dict | None = None) -> str:
    text = str(error_text or "")
    diag = diagnosis if isinstance(diagnosis, dict) else {}
    if re.search(r"Stale bulletin rejected", text, re.I):
        return "bulletin too old (recipe worked)"
    if re.search(r"blocking automated access", text, re.I):
        return "site blocking automated access"
    if re.search(r"Recipe for .* is outdated", text, re.I):
        return "recipe outdated"
    if re.search(r"admin/non-bulletin|not a weekly bulletin", text, re.I):
        return "no recipe — wrong scrape" if diag.get("step_count") == 0 else "wrong file scraped"
    if re.search(r"Recipe replay failed", text, re.I):
        return "recipe replay failed"
    if re.search(r"needs_retraining|marked for manual|recipe_blocked", text, re.I):
        return "recipe blocked"
    if diag.get("step_count") == 0:
        return "no recipe on GitHub"
    if re.search(r"getaddrinfo|Name or service not known|ENOTFOUND|Could not resolve host", text, re.I):
        return "dns"
    if re.search(r"SSL|certificate", text, re.I):
        return "ssl"
    if re.search(r"timeout|Timeout|TimeoutError", text, re.I):
        return "timeout"
    if re.search(r"Recipe download step did not find|Recipe finished without downloading", text, re.I):
        return "recipe_drift"
    if re.search(r"no PDF|html_link", text, re.I):
        return "no_pdf"
    return "other"


def _row_last_tested_at(
    item: dict,
    *,
    generated_at: str,
    previous_row: dict | None = None,
) -> str:
    """Stamp this harvest (or this parish's Send & test), never another parish's patch.

    ``report.last_patched_at`` is one parish's rebuild time. Using it as a
    fallback made 158 rows share Castleblayney's stamp (GAMEPLAN H4) so the
    Trainer treated a neighbour's finish as this parish's result.
    """
    item_ts = str(item.get("last_tested_at") or "").strip()
    if item_ts:
        return item_ts
    prev_ts = str((previous_row or {}).get("last_tested_at") or "").strip()
    if prev_ts:
        return prev_ts
    return generated_at


_BULLETIN_DATE_IN_ERROR_RE = re.compile(r"bulletin date (\d{4}-\d{2}-\d{2})")


def _row_bulletin_dates(item: dict) -> tuple[str | None, str | None]:
    """Record a proved bulletin date. Return (ISO, DD/MM/YYYY) or (None, None).

    Never invent a Sunday. Read the report field, diagnosis, stale-error text,
    then the URL — in that order.
    """
    iso = str(item.get("bulletin_date") or "").strip()
    if iso == "unknown":
        iso = ""
    if not iso:
        diagnosis = item.get("diagnosis")
        if isinstance(diagnosis, dict):
            iso = str(diagnosis.get("bulletin_date") or "").strip()
            if iso == "unknown":
                iso = ""
    if not iso:
        blob = " ".join(
            str(item.get(k) or "") for k in ("error", "reason")
        )
        match = _BULLETIN_DATE_IN_ERROR_RE.search(blob)
        if match:
            iso = match.group(1)
    if not iso:
        url = str(item.get("url") or item.get("start_url") or "")
        if url:
            from .bulletin_freshness import extract_bulletin_date

            extracted = extract_bulletin_date(url)
            if extracted is not None:
                iso = extracted.isoformat()
    if not iso:
        return None, None
    from .utils import format_uk_date

    return iso, format_uk_date(iso)


def _outcome_from_report_item(section: str, item: dict) -> str:
    if section == "downloaded":
        return "ok"
    if section == "stale_rejected":
        return "stale"
    if section == "html_links":
        return "html_only"
    if section == "skipped":
        return "skipped"
    error = str(item.get("error") or "")
    if re.search(r"Stale bulletin rejected", error, re.I):
        return "stale"
    return "failed"


def _build_parish_index(parishes_dir: Path) -> dict[str, dict[str, str]]:
    """Map parish key → {display_name, diocese}."""
    index: dict[str, dict[str, str]] = {}
    for path in sorted(parishes_dir.glob("*_bulletin_urls.txt")):
        diocese_stem = path.stem.replace("_bulletin_urls", "")
        label = _diocese_label(path.stem)
        try:
            entries = parse_evidence_file(diocese_stem, parishes_dir)
        except FileNotFoundError:
            continue
        for entry in entries:
            index[entry.key] = {
                "display_name": entry.display_name,
                "diocese": label,
            }
    return index


def build_parish_status(
    report: dict,
    *,
    parishes_dir: Path | None = None,
    consecutive_failures: dict | None = None,
    disabled_keys: set[str] | None = None,
    previous_status: dict | None = None,
) -> dict:
    """
    Merge report buckets into one parish_status.json document.
    """
    parishes_dir = parishes_dir or PARISHES_DIR
    consecutive_failures = consecutive_failures or _load_json(
        parishes_dir / "consecutive_failures.json", {}
    )
    disabled_keys = disabled_keys if disabled_keys is not None else _parse_disabled_keys(parishes_dir)
    parish_index = _build_parish_index(parishes_dir)
    previous_parishes = (
        previous_status.get("parishes")
        if isinstance(previous_status, dict) and isinstance(previous_status.get("parishes"), dict)
        else {}
    )

    target_date = str(report.get("target_date") or "")
    generated_at = str(report.get("generated_at") or "").strip() or (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    parishes: dict[str, dict] = {}

    def _upsert(key: str, payload: dict) -> None:
        key = key.strip()
        if not key:
            return
        meta = parish_index.get(key, {})
        existing = parishes.get(key, {})
        merged = {
            **existing,
            **payload,
            "display_name": payload.get("display_name") or meta.get("display_name") or key,
            "diocese": payload.get("diocese") or meta.get("diocese") or "",
        }
        parishes[key] = merged

    downloaded_keys = {
        str(item.get("parish") or "").strip()
        for item in (report.get("downloaded") or [])
        if isinstance(item, dict) and item.get("parish")
    }

    for section in ("downloaded", "stale_rejected", "failed", "html_links", "skipped"):
        for item in report.get(section) or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("parish") or "").strip()
            if not key:
                continue
            outcome = _outcome_from_report_item(section, item)
            error_text = str(item.get("error") or item.get("reason") or "")
            diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else None
            category = _failure_category(error_text, diagnosis)
            if outcome == "html_only":
                category = "no_pdf"
            elif outcome == "ok":
                category = "ok"

            actionable = (
                key not in downloaded_keys
                and key not in disabled_keys
                and outcome in {"failed", "stale", "html_only"}
            )
            recipe_meta = _load_recipe_meta_for_key(key, parishes_dir)
            if _recipe_is_inactive(recipe_meta):
                actionable = False
                if outcome == "failed":
                    outcome = "skipped"

            bulletin_date, bulletin_date_uk = _row_bulletin_dates(item)
            _upsert(
                key,
                {
                    "outcome": outcome,
                    "category": category,
                    "error": error_text or None,
                    "url": str(item.get("url") or item.get("start_url") or ""),
                    "bulletin_date": bulletin_date,
                    "bulletin_date_uk": bulletin_date_uk,
                    "last_tested_at": _row_last_tested_at(
                        item,
                        generated_at=generated_at,
                        previous_row=previous_parishes.get(key),
                    ),
                    "consecutive_failures": int(consecutive_failures.get(key) or 0),
                    "diagnosis": diagnosis,
                    "actionable": actionable,
                    "display_name": str(
                        item.get("display_name")
                        or parish_index.get(key, {}).get("display_name")
                        or key
                    ),
                    "diocese": parish_index.get(key, {}).get("diocese") or "",
                    "recipe_steps": (
                        diagnosis.get("step_count")
                        if isinstance(diagnosis, dict) and diagnosis.get("step_count") is not None
                        else (len(recipe_meta.get("steps") or []) if recipe_meta else None)
                    ),
                },
            )

    for key in disabled_keys:
        meta = parish_index.get(key, {})
        _upsert(
            key,
            {
                "outcome": "disabled",
                "category": "disabled",
                "actionable": False,
                "consecutive_failures": int(consecutive_failures.get(key) or 0),
                "display_name": meta.get("display_name") or key,
                "diocese": meta.get("diocese") or "",
                "last_tested_at": _row_last_tested_at(
                    {},
                    generated_at=generated_at,
                    previous_row=previous_parishes.get(key),
                ),
            },
        )

    actionable_keys = sorted(
        key for key, row in parishes.items() if row.get("actionable") is True
    )
    summary = {
        "total": len(parishes),
        "ok": sum(1 for row in parishes.values() if row.get("outcome") == "ok"),
        "actionable": len(actionable_keys),
        "disabled": sum(1 for row in parishes.values() if row.get("outcome") == "disabled"),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "target_date": target_date,
        "generated_at": generated_at,
        "last_patched_at": report.get("last_patched_at"),
        "summary": summary,
        "parishes": parishes,
        "actionable_keys": actionable_keys,
    }


def write_parish_status(
    report_path: Path | None = None,
    output_path: Path | None = None,
    *,
    parishes_dir: Path | None = None,
) -> dict:
    """Load report.json, build status, write parishes/parish_status.json."""
    report_path = report_path or REPORT_JSON
    output_path = output_path or PARISH_STATUS_PATH
    parishes_dir = parishes_dir or PARISHES_DIR

    report = _load_json(report_path, {})
    if not isinstance(report, dict):
        report = {}

    consecutive = _load_json(parishes_dir / "consecutive_failures.json", {})
    previous = _load_json(output_path, {}) if output_path.exists() else {}
    status = build_parish_status(
        report,
        parishes_dir=parishes_dir,
        consecutive_failures=consecutive,
        previous_status=previous if isinstance(previous, dict) else {},
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status
