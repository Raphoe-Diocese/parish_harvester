#!/usr/bin/env python3
"""Sync parish display names in evidence files, recipes, and contacts from # page: URLs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harvester.display_names import official_display_name_from_url  # noqa: E402

HEADER_RE = re.compile(r"^#\s*---\s*(.+?)\s*---\s*$", re.I)
PAGE_RE = re.compile(r"^#\s*page:\s*(.+)$", re.I)
KEY_RE = re.compile(r"^#\s*key:\s*(.+)$", re.I)


def _parse_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        hm = HEADER_RE.match(line.strip())
        if hm:
            if cur:
                blocks.append(cur)
            cur = {"name": hm.group(1).strip(), "lines": [line], "page_url": "", "key": ""}
            continue
        if cur is None:
            continue
        cur["lines"].append(line)
        stripped = line.strip()
        pm = PAGE_RE.match(stripped)
        if pm:
            cur["page_url"] = pm.group(1).strip()
        km = KEY_RE.match(stripped)
        if km:
            cur["key"] = km.group(1).strip()
    if cur:
        blocks.append(cur)
    return blocks


def _rewrite_block(block: dict, new_name: str) -> list[str]:
    out: list[str] = []
    for line in block["lines"]:
        if HEADER_RE.match(line.strip()):
            out.append(f"# --- {new_name} ---")
        else:
            out.append(line)
    return out


def sync_evidence(path: Path) -> dict[str, str]:
    """Return key -> new display_name for updated parishes."""
    text = path.read_text(encoding="utf-8-sig")
    blocks = _parse_blocks(text)
    changes: dict[str, str] = {}

    match = HEADER_RE.search(text)
    preamble = text[: match.start()].rstrip() if match else ""
    rebuilt: list[str] = [preamble] if preamble else []

    for block in blocks:
        page_url = block.get("page_url") or ""
        if not page_url:
            for line in block["lines"]:
                stripped = line.strip()
                if stripped.startswith("http") and official_display_name_from_url(stripped):
                    page_url = stripped
                    break

        official = official_display_name_from_url(page_url) if page_url else None
        name = block["name"]
        if official and official != name:
            key = block.get("key") or name
            changes[key] = official
            name = official
        rebuilt.extend(_rewrite_block(block, name))
        rebuilt.append("")

    path.write_text("\n".join(rebuilt).rstrip() + "\n", encoding="utf-8")
    return changes


def sync_recipes(recipes_dir: Path, changes: dict[str, str]) -> int:
    if not recipes_dir.exists():
        return 0
    count = 0
    for recipe_path in recipes_dir.rglob("*.json"):
        try:
            data = json.loads(recipe_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        key = str(data.get("parish_key") or recipe_path.stem)
        new_name = changes.get(key)
        if not new_name:
            continue
        if data.get("display_name") == new_name:
            continue
        data["display_name"] = new_name
        recipe_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


def sync_contacts(path: Path, changes: dict[str, str]) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for key, new_name in changes.items():
        if key in data and data[key].get("display_name") != new_name:
            data[key]["display_name"] = new_name
            count += 1
    if count:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return count


def main() -> None:
    parishes_dir = REPO_ROOT / "parishes"
    all_changes: dict[str, str] = {}
    for evidence in sorted(parishes_dir.glob("*_bulletin_urls.txt")):
        diocese = evidence.stem.replace("_bulletin_urls", "")
        changes = sync_evidence(evidence)
        all_changes.update(changes)
        print(f"{evidence.name}: {len(changes)} name(s) updated")

    recipe_count = sync_recipes(parishes_dir / "recipes", all_changes)
    print(f"recipes: {recipe_count} updated")

    for contacts in sorted(parishes_dir.glob("*_contacts.json")):
        n = sync_contacts(contacts, all_changes)
        print(f"{contacts.name}: {n} updated")

    if all_changes:
        print("Changes:")
        for key, name in sorted(all_changes.items()):
            print(f"  {key} -> {name}")
    else:
        print("No display name changes needed.")


if __name__ == "__main__":
    main()
