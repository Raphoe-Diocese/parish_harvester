#!/usr/bin/env python3
"""Probe parish URLs for DNS health (NXDOMAIN only — never marks slow sites dead)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from harvester.site_health import (
    DEFAULT_HEALTH_PATH,
    hostname_from_url,
    probe_dns,
    record_probe,
    should_mark_inactive,
)

HEADER_PATTERN = re.compile(r"^#\s*---\s*(.*?)\s*---\s*$")


def _parish_keys_from_evidence(path: Path) -> list[tuple[str, str]]:
    """Return (parish_key, url) from a bulletin_urls evidence file."""
    entries: list[tuple[str, str]] = []
    current_name: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        header = HEADER_PATTERN.match(line)
        if header:
            current_name = header.group(1).strip()
            continue
        if not line or line.startswith("#") or not current_name:
            continue
        key = re.sub(r"[^a-z0-9]+", "", current_name.lower())
        entries.append((key or current_name.lower(), line))
        current_name = None
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="DNS health probe for parish bulletin URLs")
    parser.add_argument(
        "--evidence",
        type=Path,
        action="append",
        help="Path to parishes/*_bulletin_urls.txt (repeatable)",
    )
    parser.add_argument("--health-file", type=Path, default=DEFAULT_HEALTH_PATH)
    args = parser.parse_args()

    evidence_paths = args.evidence or list(Path("parishes").glob("*_diocese_bulletin_urls.txt"))
    if not evidence_paths:
        print("No evidence files found.")
        return

    inactive_candidates: list[str] = []
    for evidence in evidence_paths:
        if not evidence.exists():
            print(f"Skip missing: {evidence}")
            continue
        for parish_key, url in _parish_keys_from_evidence(evidence):
            host = hostname_from_url(url)
            if not host:
                continue
            result = probe_dns(host)
            entry = record_probe(parish_key, url, result, path=args.health_file)
            status = entry.get("status", result)
            print(f"{parish_key}: {host} -> {status}")
            if should_mark_inactive(entry):
                inactive_candidates.append(parish_key)

    if inactive_candidates:
        print("\nInactive candidates (2+ NXDOMAIN strikes):")
        for key in inactive_candidates:
            print(f"  - {key}")
        print("Review recipes and mark inactive manually or via a future auto-recipe updater.")
    else:
        print("\nNo parishes ready for automatic inactive marking.")


if __name__ == "__main__":
    main()
