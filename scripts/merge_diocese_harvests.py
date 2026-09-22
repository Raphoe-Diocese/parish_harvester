"""S1 stitch: merge per-diocese harvest slices into one report + parish_status."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from datetime import date

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from harvester.fetcher import FetchResult  # noqa: E402
from harvester.parish_status import write_parish_status  # noqa: E402
from harvester.report import merge_diocese_reports  # noqa: E402
from harvester.stitcher import stitch_mega_pdf  # noqa: E402


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _find_slice_reports(slices_dir: Path) -> list[Path]:
    return sorted(slices_dir.rglob("report.json"))


def _copy_current_pdfs(report_path: Path, dest_current: Path) -> int:
    copied = 0
    current = report_path.parent / "current"
    if not current.is_dir():
        current = report_path.parent
    dest_current.mkdir(parents=True, exist_ok=True)
    for pdf in current.glob("*.pdf"):
        shutil.copy2(pdf, dest_current / pdf.name)
        copied += 1
    return copied


def _merge_consecutive(base: dict, slice_counts: dict, parish_keys: set[str]) -> dict:
    out = {str(k): int(v) for k, v in base.items() if str(k).strip()}
    for key in parish_keys:
        if key in slice_counts:
            try:
                out[key] = int(slice_counts[key])
            except (TypeError, ValueError):
                out[key] = 0
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slices-dir", default="_slices", type=Path)
    parser.add_argument("--report-json", default="Bulletins/report.json", type=Path)
    parser.add_argument("--report-txt", default="Bulletins/report.txt", type=Path)
    parser.add_argument("--current-dir", default="Bulletins/current", type=Path)
    parser.add_argument(
        "--consecutive",
        default="parishes/consecutive_failures.json",
        type=Path,
    )
    parser.add_argument("--mega", action="store_true")
    args = parser.parse_args()

    reports: list[dict] = []
    consecutive = _load_json(args.consecutive)
    copied = 0
    for path in _find_slice_reports(args.slices_dir):
        src = _load_json(path)
        if not src:
            continue
        reports.append(src)
        copied += _copy_current_pdfs(path, args.current_dir)
        keys = set()
        for section in ("downloaded", "html_links", "skipped", "failed", "stale_rejected"):
            for item in src.get(section) or []:
                if isinstance(item, dict) and item.get("parish"):
                    keys.add(str(item["parish"]))
        slice_counts = _load_json(path.parent / "consecutive_failures.json")
        if not slice_counts:
            slice_counts = _load_json(path.parent.parent / "parishes" / "consecutive_failures.json")
        consecutive = _merge_consecutive(consecutive, slice_counts, keys)

    if not reports:
        raise SystemExit(f"No report.json files under {args.slices_dir}")

    merged = merge_diocese_reports(reports)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    summary = merged.get("summary") or {}
    args.report_txt.write_text(
        "Merged diocese harvest\n"
        f"target_date: {merged.get('target_date')}\n"
        f"downloaded: {summary.get('downloaded', 0)}\n"
        f"failed: {summary.get('failed', 0)}\n"
        f"pdfs_copied: {copied}\n",
        encoding="utf-8",
    )
    args.consecutive.parent.mkdir(parents=True, exist_ok=True)
    args.consecutive.write_text(json.dumps(consecutive, indent=2), encoding="utf-8")
    write_parish_status(report_path=args.report_json)
    if args.mega:
        parts = str(merged.get("target_date") or "").split("-")
        target = (
            date(int(parts[0]), int(parts[1]), int(parts[2]))
            if len(parts) == 3
            else date.today()
        )
        stubs = []
        for pdf in sorted(args.current_dir.glob("*.pdf")):
            stubs.append(
                FetchResult(
                    key=pdf.stem,
                    display_name=pdf.stem.replace("_", " ").title(),
                    status="ok",
                    url="",
                    file_path=pdf,
                )
            )
        stitch_mega_pdf(
            stubs,
            current_dir=args.current_dir,
            bulletins_dir=args.report_json.parent,
            target=target,
            mega_excludes_path=Path("parishes/mega_excludes.json"),
        )
    print(f"Merged {len(reports)} diocese reports → {args.report_json} ({copied} PDFs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
