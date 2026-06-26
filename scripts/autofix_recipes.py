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
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

REPO = Path(__file__).resolve().parent.parent
RECIPES = REPO / "parishes" / "recipes"
PARISHES = REPO / "parishes"

PDFEMB_RE = re.compile(r"pdfemb-viewer", re.IGNORECASE)

# Confirmed gone / unreachable — no extension retrain needed.
KNOWN_DEAD_SITES: dict[str, dict[str, str]] = {
    "nativityparish": {
        "display_name": "Nativity",
        "diocese": "down_and_connor",
        "evidence_name": "Nativity",
        "start_url": "https://www.nativityparish.com/news",
        "reason": "Website unreachable — nativityparish.com/news times out (site gone).",
    },
    "stagnesbelfast": {
        "display_name": "St Agnes Belfast",
        "diocese": "down_and_connor",
        "evidence_name": "St Agnes Belfast",
        "start_url": "https://www.stagnesbelfast.com/?p=6069",
        "reason": "Bulletin page gone — no PDF on stagnesbelfast.com (stub since April).",
    },
}

EVIDENCE_BY_DIOCESE = {
    "derry": PARISHES / "derry_diocese_bulletin_urls.txt",
    "down_and_connor": PARISHES / "down_and_connor_bulletin_urls.txt",
    "raphoe": PARISHES / "raphoe_diocese_bulletin_urls.txt",
}

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
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read(500_000).decode("utf-8", errors="replace")
    except ssl.SSLError:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
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


def _mark_dead_url(recipe: dict, reason: str) -> dict:
    recipe["status"] = "dead_url"
    recipe["skip"] = True
    recipe["dead_reason"] = reason
    recipe["reason"] = reason
    recipe["steps"] = []
    recipe["auto_fixed"] = True
    recipe["recorded_date"] = date.today().isoformat()
    for key in ("placeholder", "needs_retraining", "retraining_reason", "captured_url"):
        recipe.pop(key, None)
    return recipe


def _pdfemb_list_recipe(key: str, display: str, diocese: str, page_url: str) -> dict:
    return {
        "parish_key": key,
        "display_name": display,
        "diocese": diocese,
        "recorded_date": date.today().isoformat(),
        "start_url": page_url,
        "site_type": "wp_pdfemb_list",
        "playbook_type": "pdfemb",
        "auto_fixed": True,
        "steps": [
            {"action": "goto", "url": page_url},
            {"action": "download", "url_pattern": "*.pdf"},
        ],
        "version": 2,
        "observed_load_ms": 45000,
        "timeout_ms": 60000,
        "total_timeout_s": 120,
        "navigation_wait_until": "commit",
    }


def _page_has_pdfemb(html: str) -> bool:
    return bool(PDFEMB_RE.search(html))


def _disable_parish_in_evidence(evidence_path: Path, parish_name: str) -> bool:
    if not evidence_path.is_file():
        return False
    lines = evidence_path.read_text(encoding="utf-8").split("\n")
    escaped = re.escape(parish_name)
    header_re = re.compile(rf"^#\s*---\s*{escaped}\s*---", re.IGNORECASE)
    for i, line in enumerate(lines):
        if header_re.match(line.strip()):
            if i + 1 < len(lines) and "DISABLED" in lines[i + 1]:
                return False
            lines.insert(i + 1, "# DISABLED — website gone / removed from harvest via autofix")
            evidence_path.write_text("\n".join(lines), encoding="utf-8")
            return True
    return False


def _apply_known_dead_sites() -> int:
    changed = 0
    evidence_path = EVIDENCE_BY_DIOCESE["down_and_connor"]
    for key, info in KNOWN_DEAD_SITES.items():
        path = RECIPES / info["diocese"] / f"{key}.json"
        if not path.is_file():
            continue
        recipe = _load_json(path)
        recipe.update({
            "parish_key": key,
            "display_name": info["display_name"],
            "diocese": info["diocese"],
            "start_url": info["start_url"],
        })
        _mark_dead_url(recipe, info["reason"])
        _save_json(path, recipe)
        if _disable_parish_in_evidence(evidence_path, info["evidence_name"]):
            print(f"[evidence-disable] {info['evidence_name']}")
        print(f"[dead] {key}")
        changed += 1
    return changed


def _recipe_needs_pdfemb_fix(recipe: dict) -> bool:
    steps = recipe.get("steps")
    if not isinstance(steps, list):
        return False
    site_type = str(recipe.get("site_type") or "").lower()
    if site_type == "wp_pdfemb_list" and recipe.get("version", 0) >= 2:
        for step in steps:
            if not isinstance(step, dict) or step.get("action") != "download":
                continue
            if step.get("url") or step.get("captured_url"):
                return True
            pattern = str(step.get("url_pattern") or "")
            if "bulletin" in pattern.lower():
                return True
        if recipe.get("navigation_wait_until") != "commit":
            return True
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("action") == "download" and step.get("url"):
            url = str(step.get("url"))
            if re.search(r"20\d{2}.*\.pdf", url, re.I):
                return True
        if step.get("action") == "click" and step.get("selector") == "div#content":
            return True
    return False


def _apply_pdfemb_probes() -> int:
    changed = 0
    for sub in ("down_and_connor", "derry"):
        subdir = RECIPES / sub
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.glob("*.json")):
            recipe = _load_json(path)
            if recipe.get("skip") or recipe.get("status") in ("dead_url", "inactive"):
                continue
            page = str(recipe.get("start_url") or "").strip()
            if not page or page.lower().endswith(".pdf"):
                continue
            needs = _recipe_needs_pdfemb_fix(recipe)
            if not needs:
                continue
            try:
                html = _fetch_html(page, timeout=30)
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
            if not _page_has_pdfemb(html):
                continue
            key = recipe.get("parish_key", path.stem)
            display = recipe.get("display_name", key)
            diocese = recipe.get("diocese", sub)
            fixed = _pdfemb_list_recipe(key, display, diocese, page)
            _save_json(path, fixed)
            print(f"[pdfemb] {path.name}")
            changed += 1
    return changed



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


def _fix_mcn_live_recipe(path: Path, recipe: dict) -> bool:
    """MCN.live parish pages — PDF bulletin link on same page as camera feed."""
    page = str(recipe.get("start_url") or "").strip()
    if "mcn.live" not in page.lower():
        return False
    key = recipe.get("parish_key", path.stem)
    display = recipe.get("display_name", key)
    diocese = recipe.get("diocese", "raphoe")
    fixed = {
        "version": 2,
        "parish_key": key,
        "display_name": display,
        "diocese": diocese,
        "recorded_date": date.today().isoformat(),
        "start_url": page,
        "site_type": "mcn_live_parish_page",
        "playbook_type": "mcn_pdf_near_camera",
        "auto_fixed": True,
        "operator_notes": [
            "MCN.live — bulletin PDF link on the same page as the camera panel.",
            "Harvester uses goto + download *.pdf after JavaScript renders.",
        ],
        "do_not": ["Do not mark inactive or screenshot the camera stream."],
        "steps": [
            {"action": "goto", "url": page},
            {"action": "download", "url_pattern": "*.pdf"},
        ],
        "timeout_ms": 90000,
        "total_timeout_s": 180,
        "navigation_wait_until": "commit",
    }
    _save_json(path, fixed)
    return True


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

    if "drive.google.com/drive/folders" in low:
        _mark_inactive(recipe, INACTIVE_REASONS["folder"])
        _save_json(path, recipe)
        return True

    if "mcn.live" in low:
        return _fix_mcn_live_recipe(path, recipe)

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


def _fix_archive_pdf_listing(path: Path, recipe: dict) -> bool:
    """Replace brittle click chains on PDF archive pages with DOM scrape download."""
    steps = recipe.get("steps")
    if not isinstance(steps, list):
        return False
    if not any(isinstance(s, dict) and s.get("action") == "click" for s in steps):
        return False
    if not any(isinstance(s, dict) and s.get("action") == "download" for s in steps):
        return False
    page = str(recipe.get("start_url") or "").strip()
    if not page or page.lower().endswith(".pdf"):
        return False
    pdfs = _probe_pdf_links(page)
    if len(pdfs) < 3:
        return False
    recipe["steps"] = [
        {"action": "goto", "url": page},
        {"action": "download", "url_pattern": "*.pdf"},
    ]
    recipe["auto_fixed"] = True
    recipe["recorded_date"] = date.today().isoformat()
    recipe.pop("placeholder", None)
    recipe.pop("needs_retraining", None)
    _save_json(path, recipe)
    return True


def main() -> int:
    changed = 0
    changed += _apply_known_dead_sites()
    changed += _apply_pdfemb_probes()
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
            elif _fix_archive_pdf_listing(path, recipe):
                changed += 1
                print(f"[archive] {path.name}")

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
