#!/usr/bin/env python3
"""Repair placeholder/stub recipes using evidence files and light HTTP probing.

Does not replace full extension training for complex sites, but fixes:
- Seeded goto-only Raphoe recipes (mark placeholder or add direct download)
- Google Drive view/folder URLs -> usercontent download URLs from evidence
- April stub recipes with captured_url=no_bulletin
- Hardcoded dated PDF selectors on Dungiven/Kilrea/Clonmany
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

REPO = Path(__file__).resolve().parent.parent
RECIPES = REPO / "parishes" / "recipes"
PARISHES = REPO / "parishes"

PDF_HREF_RE = re.compile(
    r"""href\s*=\s*["']([^"']+\.pdf[^"']*)["']""",
    re.IGNORECASE,
)
DOCX_HREF_RE = re.compile(
    r"""href\s*=\s*["']([^"']+\.docx[^"']*)["']""",
    re.IGNORECASE,
)

SKIP_HOSTS = ("facebook.com", "fbcdn.net", "instagram.com")
INACTIVE_REASONS = {
    "facebook": "Facebook bulletin — cannot automate weekly harvest",
    "mcn.live": "MCN.live camera stream — needs image capture training",
    "folder": "Google Drive folder — needs direct file link",
}


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _fetch_html(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ParishHarvester/1.0 (bulletin archive; +https://github.com/Raphoe-Diocese/parish_harvester)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(500_000).decode("utf-8", errors="replace")


def _probe_pdf_links(page_url: str) -> list[str]:
    try:
        html = _fetch_html(page_url)
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    base = page_url
    found: list[str] = []
    for pattern in (PDF_HREF_RE, DOCX_HREF_RE):
        for match in pattern.finditer(html):
            href = match.group(1).strip()
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = urljoin(base, href)
            elif not href.startswith("http"):
                href = urljoin(base, href)
            low = href.lower()
            if any(bad in low for bad in ("gdpr", "giftaid", "privacy", "prayer")):
                continue
            found.append(href)
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _direct_download_recipe(key: str, display: str, diocese: str, url: str) -> dict:
    """Download-only recipe — avoids Playwright goto abort on Drive/PDF URLs."""
    return {
        "parish_key": key,
        "display_name": display,
        "diocese": diocese,
        "recorded_date": "2026-06-17",
        "start_url": url,
        "auto_fixed": True,
        "steps": [
            {"action": "download", "url": url, "use_captured_url": True},
        ],
        "version": 1,
    }


def _mark_inactive(recipe: dict, reason: str) -> dict:
    recipe["placeholder"] = True
    recipe["status"] = "inactive"
    recipe["skip"] = True
    recipe["reason"] = reason
    recipe["auto_fixed"] = True
    return recipe


def _mark_placeholder(recipe: dict) -> dict:
    recipe["placeholder"] = True
    recipe["auto_generated"] = True
    recipe["auto_fixed"] = True
    return recipe


def _fix_stub_no_bulletin(path: Path, recipe: dict) -> bool:
    steps = recipe.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        if isinstance(step, dict) and step.get("captured_url") == "no_bulletin":
            _mark_placeholder(recipe)
            recipe["needs_retraining"] = True
            recipe["retraining_reason"] = "Stub recipe from April — no bulletin was captured"
            _save_json(path, recipe)
            return True
    return False


def _fix_hardcoded_pdf_recipe(path: Path, recipe: dict) -> bool:
    """Replace stale direct-PDF recipes with newsletter-page newest_dated flow."""
    steps = recipe.get("steps")
    if not isinstance(steps, list):
        return False
    download_urls = [
        str(step.get("url") or "")
        for step in steps
        if isinstance(step, dict) and step.get("action") == "download" and step.get("url")
    ]
    if not download_urls:
        return False
    if any(isinstance(s, dict) and s.get("action") == "click" for s in steps):
        return False
    dated = any(
        re.search(r"20\d{2}[-/]\d{2}|[-/]\d{1,2}-[A-Za-z]+-20\d{2}\.pdf", u, re.I)
        for u in download_urls
    )
    if not dated:
        return False
    host = urlparse(download_urls[0]).netloc
    if not host:
        return False
    news_url = f"https://{host}/news/"
    recipe["start_url"] = news_url
    recipe["steps"] = [
        {"action": "goto", "url": news_url},
        {
            "action": "click",
            "selector": 'a[href$=".pdf"], a[href*=".pdf"]',
            "pick_strategy": "newest_dated",
        },
        {"action": "download", "use_captured_url": True},
    ]
    recipe["auto_fixed"] = True
    _save_json(path, recipe)
    return True


def _fix_dated_selectors(path: Path, recipe: dict) -> bool:
    key = recipe.get("parish_key", path.stem)
    changed = False
    steps = recipe.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("action") == "click" and step.get("href") and re.search(r"\d{6}\.pdf", str(step.get("href"))):
            step.pop("href", None)
            step["selector"] = 'a[href*="/pdf/"]'
            step["pick_strategy"] = "newest_dated"
            changed = True
        if step.get("action") == "download" and step.get("url") and re.search(r"/\d{6}\.pdf|20\d{2}-\d{2}-\d{2}\.pdf", str(step.get("url"))):
            step["use_captured_url"] = True
            step.pop("url", None)
            changed = True
    if key == "threepatrons" and steps and not any(
        isinstance(s, dict) and s.get("action") == "download" for s in steps
    ):
        steps.append({"action": "download", "url_pattern": "*.pdf"})
        changed = True
    if changed:
        recipe["auto_fixed"] = True
        _save_json(path, recipe)
    return changed


def _fix_raphoe_recipe(path: Path, recipe: dict, evidence_url: str, ev_notes: str) -> bool:
    key = recipe.get("parish_key", path.stem)
    display = recipe.get("display_name", key)
    diocese = recipe.get("diocese", "raphoe")
    url = evidence_url or recipe.get("start_url", "")
    low = url.lower()
    notes_low = ev_notes.lower()

    if any(h in low for h in SKIP_HOSTS) or "facebook" in notes_low:
        _mark_inactive(recipe, INACTIVE_REASONS["facebook"])
        _save_json(path, recipe)
        return True

    if "mcn.live" in low or "cannot automate" in notes_low and "mcn" in notes_low:
        _mark_inactive(recipe, INACTIVE_REASONS["mcn.live"])
        _save_json(path, recipe)
        return True

    if "drive.google.com/drive/folders" in low:
        _mark_inactive(recipe, INACTIVE_REASONS["folder"])
        _save_json(path, recipe)
        return True

    if "drive.usercontent.google.com" in low or low.split("?")[0].endswith(".pdf"):
        fixed = _direct_download_recipe(key, display, diocese, url)
        _save_json(path, fixed)
        return True

    if "parishpress.net" in low and ".pdf" in low:
        fixed = _direct_download_recipe(key, display, diocese, url)
        _save_json(path, fixed)
        return True

    # WordPress / bulletin listing pages — probe for PDF
    page = recipe.get("start_url") or url
    if page and not low.split("?")[0].endswith(".pdf"):
        pdfs = _probe_pdf_links(page)
        if pdfs:
            best = pdfs[0]
            fixed = {
                "parish_key": key,
                "display_name": display,
                "diocese": diocese,
                "recorded_date": "2026-06-17",
                "start_url": page,
                "auto_fixed": True,
                "steps": [
                    {"action": "goto", "url": page},
                    {
                        "action": "click",
                        "selector": 'a[href$=".pdf"], a[href*=".pdf"]',
                        "pick_strategy": "newest_dated",
                    },
                    {"action": "download", "url": best, "use_captured_url": True},
                ],
                "version": 1,
            }
            _save_json(path, fixed)
            return True

    _mark_placeholder(recipe)
    _save_json(path, recipe)
    return True


def _parse_raphoe_evidence() -> dict[str, dict]:
    path = PARISHES / "raphoe_diocese_bulletin_urls.txt"
    out: dict[str, dict] = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("# --- ") and s.endswith(" ---"):
            current = s[6:-4].strip()
            out[current.lower()] = {"name": current, "key": None, "notes": [], "urls": []}
        elif current and s.startswith("# key:"):
            out[current.lower()]["key"] = s.split(":", 1)[1].strip().lower()
        elif current and s.startswith("#"):
            out[current.lower()]["notes"].append(s.lstrip("# ").strip())
        elif current and s.startswith("http"):
            out[current.lower()]["urls"].append(s)
    return out


def _drive_id(url: str) -> str | None:
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def _match_evidence(recipe: dict, evidence: dict[str, dict]) -> dict | None:
    disp = str(recipe.get("display_name", "")).lower()
    key = str(recipe.get("parish_key", "")).lower()
    start = str(recipe.get("start_url", ""))
    file_id = _drive_id(start)

    for v in evidence.values():
        ev_key = str(v.get("key") or "").lower()
        if ev_key and ev_key == key:
            return v
        for u in v.get("urls", []):
            if file_id and file_id in u:
                return v

    for k, v in evidence.items():
        if k in disp or disp in k:
            return v
        if key and (key in k.replace(" ", "") or k.replace(" ", "") in key):
            return v
    return None


def main() -> int:
    changed = 0
    evidence = _parse_raphoe_evidence()

    for path in sorted((RECIPES / "raphoe").glob("*.json")):
        recipe = _load_json(path)
        if not recipe:
            continue
        ev = _match_evidence(recipe, evidence)
        ev_url = ev["urls"][0] if ev and ev.get("urls") else ""
        ev_notes = " | ".join(ev.get("notes", [])) if ev else ""
        steps = recipe.get("steps") or []
        is_goto_only = len(steps) == 1 and steps[0].get("action") == "goto"
        needs_fix = (
            is_goto_only
            or recipe.get("recorded_date") == "2026-05-22"
            or recipe.get("placeholder")
        )
        if needs_fix:
            if _fix_raphoe_recipe(path, recipe, ev_url, ev_notes):
                changed += 1
                print(f"[raphoe] {path.name}")

    for sub in ("down_and_connor", "derry", "unknown"):
        subdir = RECIPES / sub
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.glob("*.json")):
            recipe = _load_json(path)
            if _fix_stub_no_bulletin(path, recipe):
                changed += 1
                print(f"[stub] {path.name}")
            elif _fix_hardcoded_pdf_recipe(path, recipe):
                changed += 1
                print(f"[hardcoded] {path.name}")
            elif _fix_dated_selectors(path, recipe):
                changed += 1
                print(f"[dated] {path.name}")

    # Remove duplicate junk recipe
    junk = RECIPES / "derry" / "2026-06-07-pdf.json"
    if junk.exists():
        junk.unlink()
        print("[delete] derry/2026-06-07-pdf.json")
        changed += 1

    print(f"done: {changed} file(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
