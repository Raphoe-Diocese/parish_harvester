from __future__ import annotations

"""Retention policy — delete leftover old parish PDFs, never zip-archive them.

Frank does not want archived copies stored in the repo. Current-week parish
PDFs and mega PDFs stay. Any leftover ``Bulletins/archive/*.zip`` is removed.

Configurable via ``parishes/retention_policy.json`` (see defaults below).

Usage::

    from pathlib import Path
    from harvester.retention import apply_retention

    report = apply_retention(Path("."))          # live run
    report = apply_retention(Path("."), dry_run=True)  # preview only
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Default policy — can be overridden by parishes/retention_policy.json
# ---------------------------------------------------------------------------
DEFAULT_POLICY: dict = {
    "create_archives": False,
    "keep_weeks_individual": 8,
    "keep_weeks_mega_pdf": 12,
    "keep_months_archive": 0,
    "hard_size_cap_gb": 4.0,
}

GB = 1024 ** 3


def _load_policy(repo_root: Path) -> dict:
    policy_path = repo_root / "parishes" / "retention_policy.json"
    if not policy_path.exists():
        return dict(DEFAULT_POLICY)
    try:
        loaded = json.loads(policy_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return dict(DEFAULT_POLICY)
        merged = dict(DEFAULT_POLICY)
        merged.update(loaded)
        return merged
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_POLICY)


def _repo_size_bytes(repo_root: Path) -> int:
    """Sum of all non-hidden tracked files on disk (fast approximation)."""
    total = 0
    for p in repo_root.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _week_cutoff(weeks: int) -> datetime:
    """UTC datetime *weeks* weeks before now."""
    from datetime import timedelta

    return datetime.now(timezone.utc) - timedelta(weeks=weeks)


def _collect_old_files(directory: Path, cutoff: datetime, suffixes: set[str]) -> list[Path]:
    """Collect files in *directory* older than *cutoff* with matching suffix."""
    results: list[Path] = []
    if not directory.is_dir():
        return results
    for f in directory.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in suffixes:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            results.append(f)
    return results


def _delete_file(path: Path, root: Path, dry_run: bool, deleted_files: list[str], warnings: list[str]) -> None:
    rel = str(path.relative_to(root))
    if dry_run:
        deleted_files.append(rel)
        return
    try:
        path.unlink()
        deleted_files.append(rel)
    except OSError as exc:
        warnings.append(f"Could not delete {path}: {exc}")


def apply_retention(root: Path, dry_run: bool = False) -> dict:
    """Apply retention rules to the repository at *root*.

    Archives are disabled: leftover old individual PDFs are deleted, not
    zipped. Mega PDFs are never deleted here (OCR / viewer still need them).

    Parameters
    ----------
    root:
        Repository root directory.
    dry_run:
        If True, compute what *would* be done but make no changes to disk.

    Returns
    -------
    dict
        Report with keys: ``before_bytes``, ``after_bytes``,
        ``zipped_files``, ``deleted_files``, ``warnings``.
        ``zipped_files`` is always empty (zip archives are not created).
    """
    policy = _load_policy(root)
    keep_weeks_individual = int(policy.get("keep_weeks_individual", DEFAULT_POLICY["keep_weeks_individual"]))
    hard_cap_bytes = float(policy.get("hard_size_cap_gb", DEFAULT_POLICY["hard_size_cap_gb"])) * GB

    archive_dir = root / "Bulletins" / "archive"

    before_bytes = _repo_size_bytes(root)
    zipped_files: list[str] = []
    deleted_files: list[str] = []
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Step 1 — Delete leftover old individual parish PDFs (never zip)
    # -----------------------------------------------------------------------
    individual_cutoff = _week_cutoff(keep_weeks_individual)
    bulletins_current = root / "Bulletins" / "current"
    if bulletins_current.is_dir():
        for old_pdf in _collect_old_files(bulletins_current, individual_cutoff, {".pdf"}):
            _delete_file(old_pdf, root, dry_run, deleted_files, warnings)

    # -----------------------------------------------------------------------
    # Step 2 — Mega PDFs stay (current week + live site / OCR)
    # -----------------------------------------------------------------------
    # Intentionally not deleted or zipped.

    # -----------------------------------------------------------------------
    # Step 3 — Remove any leftover archive zips
    # -----------------------------------------------------------------------
    if archive_dir.is_dir():
        for f in archive_dir.iterdir():
            if not f.is_file() or f.suffix.lower() != ".zip":
                continue
            _delete_file(f, root, dry_run, deleted_files, warnings)

    after_bytes = _repo_size_bytes(root)
    if after_bytes > hard_cap_bytes:
        pct = after_bytes / hard_cap_bytes * 100
        msg = (
            f"Repository size {after_bytes / GB:.2f} GB exceeds hard cap "
            f"{hard_cap_bytes / GB:.2f} GB ({pct:.0f}%). "
            "Zip archives are disabled — deleting files from the tree does not "
            "shrink GitHub quota until git history is rewritten (do not force-push "
            "unless asked)."
        )
        warnings.append(msg)
        print(f"[retention] {msg}")

    return {
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "zipped_files": zipped_files,
        "deleted_files": deleted_files,
        "warnings": warnings,
    }
