"""OCR page counter for the S3 quota dashboard.

Records billed vision pages (Mistral / Gemini / OpenAI) into
``Bulletins/ocr_quota.json``. Tesseract is not a reader and is never
counted. Ceilings are never invented: print ``unknown`` unless
``OCR_CEILING_<PROVIDER>`` is set as a positive int.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROVIDERS = ("mistral", "gemini", "openai")
PROVIDER_LABELS = {
    "mistral": "Mistral",
    "gemini": "Gemini",
    "openai": "OpenAI",
}
TARGET_DIOCESES = 26
# Free plan $10 API credits / $4 per 1,000 OCR pages (mistral.ai/pricing, 15/09/2026).
MISTRAL_FREE_PAGES = 2500
STATE_REL = Path("Bulletins") / "ocr_quota.json"


def repo_root() -> Path:
    env = (os.environ.get("GITHUB_WORKSPACE") or os.environ.get("OCR_REPO_ROOT") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1]


def provider_key(provider_used: str | None) -> str | None:
    raw = (provider_used or "").strip().lower()
    if not raw:
        return None
    if "tesseract" in raw:
        return None
    if "mistral" in raw:
        return "mistral"
    if "gemini" in raw:
        return "gemini"
    if "openai" in raw:
        return "openai"
    return None


def billed_pages(
    provider_used: str | None,
    pages_text: list | None,
    vision_indexes: list | None,
) -> tuple[str | None, int]:
    key = provider_key(provider_used)
    if not key:
        return None, 0
    if vision_indexes:
        return key, len(vision_indexes)
    return key, len(pages_text or [])


def _month_utc(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.strftime("%Y-%m")


def current_diocese_count(root: Path) -> int:
    path = root / "parishes" / "dioceses.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("dioceses") or []
        return len(rows) if isinstance(rows, list) else 0
    except Exception:  # noqa: BLE001
        return 0


def ceiling_for(provider: str) -> int | None:
    env_name = f"OCR_CEILING_{provider.upper()}"
    raw = (os.environ.get(env_name) or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = None
        else:
            return value if value > 0 else None
    if provider == "mistral":
        return MISTRAL_FREE_PAGES
    return None


def empty_state(root: Path, *, now: datetime | None = None) -> dict:
    return {
        "month": _month_utc(now),
        "current_dioceses": current_diocese_count(root),
        "target_dioceses": TARGET_DIOCESES,
        "pages": {name: 0 for name in PROVIDERS},
        "updated_at": None,
    }


def load_state(root: Path | None = None, *, now: datetime | None = None) -> dict:
    root = root or repo_root()
    path = root / STATE_REL
    month = _month_utc(now)
    blank = empty_state(root, now=now)
    if not path.exists():
        return blank
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return blank
    if not isinstance(data, dict) or data.get("month") != month:
        return blank
    pages = data.get("pages") if isinstance(data.get("pages"), dict) else {}
    blank["pages"] = {name: int(pages.get(name) or 0) for name in PROVIDERS}
    blank["updated_at"] = data.get("updated_at")
    return blank


def save_state(state: dict, root: Path | None = None) -> Path:
    root = root or repo_root()
    path = root / STATE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path


def record_pages(
    provider: str,
    pages: int,
    root: Path | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    root = root or repo_root()
    key = provider_key(provider)
    count = int(pages or 0)
    state = load_state(root, now=now)
    if key and count > 0:
        state["pages"][key] = int(state["pages"].get(key) or 0) + count
        stamp = now or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        state["updated_at"] = stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        save_state(state, root)
    return state


def record_convert_run(
    provider_used: str | None,
    pages_text: list | None,
    vision_indexes: list | None,
    root: Path | None = None,
) -> dict:
    key, pages = billed_pages(provider_used, pages_text, vision_indexes)
    if not key or pages <= 0:
        return load_state(root)
    return record_pages(key, pages, root=root)


def project_to_26(pages: int, current_dioceses: int) -> int | None:
    if current_dioceses <= 0:
        return None
    return int(round(pages * TARGET_DIOCESES / current_dioceses))


def month_rows(root: Path | None = None, *, now: datetime | None = None) -> list[dict]:
    root = root or repo_root()
    state = load_state(root, now=now)
    current = int(state.get("current_dioceses") or 0)
    rows = []
    for key in PROVIDERS:
        pages = int(state["pages"].get(key) or 0)
        ceiling = ceiling_for(key)
        projection = project_to_26(pages, current)
        used_pct: float | None = None
        if ceiling is not None:
            used_pct = pages / ceiling * 100
        over = ceiling is not None and projection is not None and projection > ceiling
        rows.append(
            {
                "provider": key,
                "label": PROVIDER_LABELS[key],
                "pages": pages,
                "ceiling": ceiling,
                "used_pct": used_pct,
                "projection_26": projection,
                "over": over,
            }
        )
    return rows


def markdown_section(root: Path | None = None, *, now: datetime | None = None) -> str:
    root = root or repo_root()
    state = load_state(root, now=now)
    rows = month_rows(root, now=now)
    current = int(state.get("current_dioceses") or 0)
    any_red = any(row["over"] for row in rows)
    light = "🔴" if any_red else "🟢"
    lines = [
        f"## {light} OCR pages this month",
        "",
        f"_Month {state['month']}. Counted from billed Mistral / Gemini / OpenAI pages only. "
        "Tesseract is not a bulletin reader and is not counted. "
        f"Today {current} diocese(s); projection scales that to {TARGET_DIOCESES}. "
        "Mistral ceiling is 2,500 pages from Free **$10** credits at **$4 / 1,000 pages** "
        "(mistral.ai/pricing, 15/09/2026). Gemini and OpenAI stay **unknown** unless "
        "`OCR_CEILING_GEMINI` / `OCR_CEILING_OPENAI` is set._",
        "",
        "| Provider | Pages this month | Free ceiling | % used | At 26 dioceses |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        ceiling = "unknown" if row["ceiling"] is None else str(row["ceiling"])
        pct = "unknown" if row["used_pct"] is None else f"{row['used_pct']:.1f}%"
        proj = "unknown" if row["projection_26"] is None else str(row["projection_26"])
        flag = " 🔴 over ceiling" if row["over"] else ""
        lines.append(
            f"| {row['label']} | {row['pages']} | {ceiling} | {pct} | {proj}{flag} |"
        )
    lines += [
        "",
        "Read the three **Pages this month** numbers. Red only if a known ceiling is set and the 26-diocese projection is over it.",
        "",
    ]
    return "\n".join(lines)
