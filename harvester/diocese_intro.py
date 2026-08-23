"""Honest diocese-page intro: welcome, this-week counts, never-publish, stale.

Counts come from recipes + parish_status. Never invent N of M, bishop
details, phones, or emails. Alias keys (Ballintra, Kilmacrenan) are
folded into their canonical parish.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from harvester.parish_aliases import (
    combined_display_name,
    is_alias_key,
    name_lookup_keys,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class NamedLink:
    name: str
    url: str = ""


@dataclass
class DioceseWeekSummary:
    diocese_display_name: str
    found: int = 0
    total: int = 0
    never_publish: list[NamedLink] = field(default_factory=list)
    stale: list[NamedLink] = field(default_factory=list)


def recipe_folder_name(diocese_key: str) -> str:
    return (diocese_key or "").strip().replace("-", "_")


def welcome_line(diocese_display_name: str) -> str:
    display = (diocese_display_name or "").strip() or "this diocese"
    short = display.removesuffix(" Diocese").strip() or display
    if short.lower() == "down and connor":
        short = "Down & Connor"
    return f"Welcome to the Diocese of {short}."


def _parishes_map(payload: object) -> dict[str, dict]:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("parishes")
    if isinstance(nested, dict):
        return {
            str(key): value
            for key, value in nested.items()
            if isinstance(value, dict)
        }
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(value, dict) and "outcome" in value
    }


def _load_json(path: Path | None) -> object:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _http_url(value: str) -> str:
    text = (value or "").strip()
    if text.startswith(("http://", "https://")):
        return text
    return ""


# Official diocese parish pages already stored on recipes. Do not invent hosts.
_DIOCESE_PAGE_HOSTS = (
    "raphoediocese.ie",
    "clogherdiocese.ie",
    "downandconnordiocese.com",
    "derrydiocese.org",
)

NEVER_PUBLISH_HEADING = (
    "Parishes that share news on Facebook or their website"
)
NEVER_PUBLISH_NOTE = (
    "We just have no downloadable PDF to stitch this week."
)
STALE_HEADING = "Parishes whose bulletin is from last week or older"
STALE_NOTE = (
    "They share news on Facebook or their website — we just have no "
    "downloadable PDF to stitch this week."
)


def _host(url: str) -> str:
    text = (url or "").lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.split("/", 1)[0].removeprefix("www.")


def _candidate_urls(row: dict, recipe: dict, extra: list[str] | None = None) -> list[str]:
    found: list[str] = []
    for raw in list(extra or []) + [
        recipe.get("start_url"),
        (row or {}).get("url"),
        recipe.get("facebook"),
        (row or {}).get("facebook"),
    ]:
        href = _http_url(str(raw or ""))
        if href and href not in found:
            found.append(href)
    for step in recipe.get("steps") or []:
        if not isinstance(step, dict):
            continue
        href = _http_url(str(step.get("url") or step.get("href") or ""))
        if href and href not in found:
            found.append(href)
    return found


def share_url(
    row: dict,
    recipe: dict,
    *,
    contact_facebook: str = "",
    contact_website: str = "",
) -> str:
    """Reader link: proven Facebook, else parish website, else official diocese page."""
    candidates = _candidate_urls(
        row,
        recipe,
        extra=[contact_facebook, contact_website],
    )
    for href in candidates:
        if "facebook.com" in _host(href):
            return href
    for href in candidates:
        if _host(href) and _host(href) not in _DIOCESE_PAGE_HOSTS:
            return href
    for href in candidates:
        if _host(href) in _DIOCESE_PAGE_HOSTS:
            return href
    return candidates[0] if candidates else ""


def _contacts_for_diocese(diocese_key: str) -> dict[str, dict]:
    folder = recipe_folder_name(diocese_key)
    path = REPO_ROOT / "parishes" / f"{folder}_diocese_contacts.json"
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _recipe_display(payload: dict, key: str) -> str:
    return (
        combined_display_name(key)
        or str(payload.get("display_name") or payload.get("parish_name") or "").strip()
        or key.replace("-", " ").replace("_", " ").title()
    )


def _iter_recipes(recipe_dir: Path) -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    if not recipe_dir.is_dir():
        return rows
    for path in sorted(recipe_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        key = str(payload.get("parish_key") or path.stem).strip() or path.stem
        rows.append((key, payload))
    return rows


def build_diocese_week_summary(
    diocese_key: str,
    *,
    diocese_display_name: str = "",
    recipes_root: Path | None = None,
    parish_status: dict | None = None,
    parish_status_path: Path | None = None,
) -> DioceseWeekSummary:
    """Count this week's bulletins from recipes + parish_status.

    *total* is distinct parishes after alias collapse. *found* is
    ``outcome == ok`` only — never a made-up fraction.
    """
    display = (diocese_display_name or "").strip() or (
        diocese_key.replace("_", " ").replace("-", " ").title() + " Diocese"
    )
    summary = DioceseWeekSummary(diocese_display_name=display)
    repo_recipes = REPO_ROOT / "parishes" / "recipes"
    root = recipes_root or repo_recipes
    using_repo_recipes = (
        recipes_root is None or Path(root).resolve() == repo_recipes.resolve()
    )
    recipe_dir = Path(root) / recipe_folder_name(diocese_key)
    status_map = parish_status if parish_status is not None else _parishes_map(
        _load_json(parish_status_path or (REPO_ROOT / "parishes" / "parish_status.json"))
    )
    contacts = _contacts_for_diocese(diocese_key) if using_repo_recipes else {}

    for key, recipe in _iter_recipes(recipe_dir):
        if is_alias_key(key):
            continue
        row = status_map.get(key) if isinstance(status_map.get(key), dict) else {}
        name = _recipe_display(recipe, key)
        if not name and isinstance(row, dict):
            name = str(row.get("display_name") or key)
        url = _http_url(str((row or {}).get("url") or recipe.get("start_url") or ""))
        outcome = str((row or {}).get("outcome") or "").strip().lower()
        skipped = bool(recipe.get("skip")) or outcome == "skipped"
        summary.total += 1
        if outcome == "ok":
            summary.found += 1
            continue
        if outcome == "stale":
            contact = contacts.get(key) if isinstance(contacts.get(key), dict) else {}
            summary.stale.append(
                NamedLink(
                    name=name,
                    url=share_url(
                        row or {},
                        recipe,
                        contact_facebook=str((contact or {}).get("facebook") or ""),
                        contact_website=str((contact or {}).get("website") or ""),
                    )
                    or url,
                )
            )
            continue
        if skipped:
            contact = contacts.get(key) if isinstance(contacts.get(key), dict) else {}
            summary.never_publish.append(
                NamedLink(
                    name=name,
                    url=share_url(
                        row or {},
                        recipe,
                        contact_facebook=str((contact or {}).get("facebook") or ""),
                        contact_website=str((contact or {}).get("website") or ""),
                    ),
                )
            )

    summary.never_publish.sort(key=lambda item: item.name.lower())
    summary.stale.sort(key=lambda item: item.name.lower())
    return summary


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _name_list_html(items: list[NamedLink], *, with_late_link: bool) -> str:
    bits: list[str] = []
    for item in items:
        name = _esc(item.name)
        href = _http_url(item.url)
        if with_late_link and href:
            bits.append(
                f"<li>{name} — <a href=\"{_esc(href)}\" target=\"_blank\" "
                f'rel="noopener noreferrer">last known link</a></li>'
            )
        elif href:
            bits.append(
                f"<li><a href=\"{_esc(href)}\" target=\"_blank\" "
                f'rel="noopener noreferrer">{name}</a></li>'
            )
        else:
            bits.append(f"<li>{name}</li>")
    return f'<ul class="intro-names">{"".join(bits)}</ul>'


def render_diocese_intro_html(summary: DioceseWeekSummary) -> str:
    """Short professional intro. No bishop, phone, or email unless already supplied."""
    welcome = _esc(welcome_line(summary.diocese_display_name))
    if summary.total > 0:
        count = (
            f"This week's collated bulletin: {summary.found} of {summary.total} "
            "parish bulletins were found."
        )
    else:
        count = "This week's collated bulletin will show how many parish files were found once this week's harvest is in."
    parts = [
        '<section class="diocese-intro" aria-label="This week\'s bulletin">',
        f"<p class=\"intro-welcome\">{welcome}</p>",
        f"<p class=\"intro-count\">{_esc(count)}</p>",
    ]
    if summary.never_publish:
        parts.append(
            "<div class=\"intro-never\">"
            f"<h3>{_esc(NEVER_PUBLISH_HEADING)}</h3>"
            f"<p class=\"intro-never-note\">{_esc(NEVER_PUBLISH_NOTE)}</p>"
            f"{_name_list_html(summary.never_publish, with_late_link=False)}"
            "</div>"
        )
    if summary.stale:
        parts.append(
            "<div class=\"intro-stale\">"
            f"<h3>{_esc(STALE_HEADING)}</h3>"
            f"<p class=\"intro-stale-note\">{_esc(STALE_NOTE)}</p>"
            f"{_name_list_html(summary.stale, with_late_link=False)}"
            "</div>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def load_mega_page_index(docs_dir: Path, diocese_key: str) -> dict[str, int]:
    """Map parish display names (and keys) to 1-based mega-PDF start pages."""
    stem = recipe_folder_name(diocese_key)
    path = Path(docs_dir) / "mega_pdf" / f"{stem}_mega_bulletin.pages.json"
    payload = _load_json(path)
    parishes = payload.get("parishes") if isinstance(payload, dict) else None
    if not isinstance(parishes, dict):
        return {}
    out: dict[str, int] = {}
    for key, row in parishes.items():
        if not isinstance(row, dict):
            continue
        try:
            start = int(row.get("start_page"))
        except (TypeError, ValueError):
            continue
        if start < 1:
            continue
        raw_name = str(row.get("display_name") or "").strip()
        label = combined_display_name(str(key)) or raw_name
        if label:
            out[label] = start
        if raw_name and raw_name not in out:
            out[raw_name] = start
        out[str(key)] = start
    return out


def lookup_internal_href(name: str, internal_hrefs: dict[str, str] | None) -> str | None:
    """Match a grid name (including combined alias names) to a parish page."""
    if not internal_hrefs:
        return None
    for token in name_lookup_keys(name):
        href = internal_hrefs.get(token)
        if href:
            return href
    return None
