"""Build a reproducible, evidence-labelled queue from parish discovery seeds.

No seed URL is treated as a verified current bulletin. MCN and Drive sources
are matched by stable identifiers rather than ephemeral PDF UUID filenames.
Run: python scripts/build_bulletin_discovery_queue.py
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
WEBSITES = ROOT / "docs/discovery/seeds-websites-2026-10-29.txt"
SPECIALISED = ROOT / "docs/discovery/seeds-specialised-2026-10-29.txt"
REPORT = ROOT / "Bulletins/report.json"
STATUS_FIELDS = (
    ("stale_rejected", "stale"),
    ("failed", "failed"),
    ("skipped", "skipped"),
    ("downloaded", "downloaded"),
)
PRIORITY = {"stale": 1, "failed": 1, "unmatched": 2, "skipped": 2, "downloaded": 4}
STATUS_ORDER = {"stale": 0, "failed": 1, "skipped": 2, "downloaded": 3}


def normalise_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\([^)]*\)", "", value)
    return re.sub(r"[^a-z0-9]", "", value.lower())


def church_id(value: str) -> str | None:
    match = re.search(r"/Uploads/(\d+)/NewsLetter/", value or "", re.I)
    return match.group(1) if match else None


def drive_id(value: str) -> str | None:
    url = value or ""
    parts = urlsplit(url.replace(" ", "%20"))
    for key in ("id",):
        values = parse_qs(parts.query).get(key)
        if values and re.fullmatch(r"[\w-]{12,}", values[0]):
            return values[0]
    match = re.search(r"/(?:file/d|folders)/([\w-]{12,})", url, re.I)
    return match.group(1) if match else None


def canonical_url(value: str) -> str:
    try:
        parts = urlsplit((value or "").strip().replace(" ", "%20"))
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            return ""
        query = parse_qs(parts.query, keep_blank_values=True)
        query.pop("bulletin_date", None)
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"),
             urlencode(query, doseq=True), "")
        )
    except ValueError:
        return ""


def source_type(value: str, fallback: str = "website") -> str:
    lower = value.lower()
    if "/newsletter/" in lower and "cloudfront.net" in lower:
        return "mcn_live"
    if "drive.google.com/" in lower or "drive.usercontent.google.com/" in lower:
        return "google_drive"
    if "churchmedia.tv/" in lower:
        return "churchmedia"
    if "/onewebmedia/" in lower:
        return "onewebmedia"
    if "parishpress.net/" in lower:
        return "parishpress"
    if "churchtv.ie/" in lower:
        return "churchtv"
    return fallback


def load_seeds(path: Path, *, fallback_type: str = "website") -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.search(r"https?://", line, re.I)
        if not match:
            continue  # category heading / blank / explanation
        name = re.split(r"\s{2,}", line[: match.start()].strip(), maxsplit=1)[0]
        url = line[match.start() :].strip()
        if not name or not url:
            continue
        rows.append({
            "name": name,
            "url": url,
            "source_type": source_type(url, fallback_type),
            "source_file": path.name,
        })
    return rows


def build_queue(website_rows: list[dict], specialised_rows: list[dict], report: dict) -> dict:
    by_name = defaultdict(list)
    by_church = defaultdict(list)
    by_drive = defaultdict(list)
    by_url = defaultdict(list)
    for field, status in STATUS_FIELDS:
        for item in report.get(field) or []:
            hit = {"status": status, "parish": item.get("parish") or ""}
            for text in (item.get("display_name"), item.get("parish"), item.get("name")):
                key = normalise_name(text or "")
                if key:
                    by_name[key].append(hit)
            for index, key in (
                (by_church, church_id(item.get("url") or "")),
                (by_drive, drive_id(item.get("url") or "")),
                (by_url, canonical_url(item.get("url") or "")),
            ):
                if key:
                    index[key].append(hit)

    rows = []
    seen = set()
    for seed in [*website_rows, *specialised_rows]:
        key = (normalise_name(seed["name"]), seed["url"].rstrip("/"))
        if key in seen:
            continue
        seen.add(key)

        url = seed["url"]
        methods = (
            ("mcn_church_id", by_church, church_id(url)),
            ("drive_file_id", by_drive, drive_id(url)),
            ("exact_url", by_url, canonical_url(url)),
            ("parish_name", by_name, normalise_name(seed["name"])),
        )
        matching = []
        method = None
        for candidate_method, index, identifier in methods:
            if identifier and index.get(identifier):
                matching = index[identifier]
                method = candidate_method
                break
        found = min(matching, key=lambda item: STATUS_ORDER[item["status"]]) if matching else None
        status = found["status"] if found else "unmatched"
        rows.append({
            **seed,
            "status_hint": status,
            "matched_parish": found["parish"] if found else None,
            "priority": PRIORITY[status],
            "match_method": method,
            "validation": "unverified_seed",
        })
    rows.sort(key=lambda x: (x["priority"], normalise_name(x["name"]), x["url"]))
    counts = Counter(row["status_hint"] for row in rows)
    return {
        "schema_version": 1,
        "generated_from_harvest_date": report.get("target_date"),
        "description": (
            "Unverified source leads. Matches use MCN/Drive IDs, exact URL or parish "
            "name and never establish a current issue or successful download."
        ),
        "stats": {
            "raw_leads": len(website_rows) + len(specialised_rows),
            "deduplicated_leads": len(rows),
            "by_hint": dict(sorted(counts.items())),
            "id_matched_leads": sum(
                x["match_method"] in {"mcn_church_id", "drive_file_id"} for x in rows
            ),
        },
        "leads": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--websites", type=Path, default=WEBSITES)
    parser.add_argument("--specialised", type=Path, default=SPECIALISED)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    data = build_queue(load_seeds(args.websites), load_seeds(args.specialised, fallback_type="specialised"), report)
    output = args.output or ROOT / "docs/discovery" / (
        f"research-queue-{report['target_date']}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Discovery leads: {data['stats']}; wrote {output}")


if __name__ == "__main__":
    main()
