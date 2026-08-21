"""Keep newly generated harvest outputs when git rebase/merge hits conflicts.

Binary mega PDFs cannot be auto-merged. Generated diocese HTML and harvest
JSON often cannot either (content or add/add). This helper prefers the files
this harvest just produced, then continues.

Covered paths (this harvest wins):

* ``mega_pdf/*.pdf`` and ``docs/mega_pdf/*.pdf``
* ``docs/dioceses/**`` (and ``docs/parishes/**`` if harvest wrote them)
* ``docs/index.html``, ``docs/manifest.json``, ``docs/mega_pdf/*.pages.json``
* ``Bulletins/report.json`` (plus report.txt / dashboard / current PDFs)
* ``parishes/parish_status.json`` and the other harvest status JSON files

Source files such as ``parishes/recipes/**`` and ``harvester/*.py`` are never
auto-overwritten.

Rebase vs merge (git's ours/theirs is reversed):

* rebase / pull --rebase: ``--theirs`` is the replayed harvest commit
* merge / pull (merge): ``--ours`` is the current harvest branch
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

MEGA_PDF_DIR_NAMES = ("mega_pdf", "docs/mega_pdf")
MEGA_PDF_PREFIXES = tuple(f"{name}/" for name in MEGA_PDF_DIR_NAMES)

# Exact generated files harvest.yml / main.py write and commit.
GENERATED_HARVEST_FILES = frozenset(
    {
        "Bulletins/report.json",
        "Bulletins/report.txt",
        "Bulletins/dashboard.html",
        "docs/manifest.json",
        "docs/index.html",
        "parish_status.json",
        "parishes/parish_status.json",
        "parishes/consecutive_failures.json",
        "parishes/stale_bulletins.json",
        "parishes/retry_queue.json",
        "parishes/training_backlog.json",
    }
)

# Directory trees harvest (or harvest+OCR site build) regenerates.
GENERATED_HARVEST_PREFIXES = (
    "mega_pdf/",
    "docs/mega_pdf/",
    "docs/dioceses/",
    "docs/parishes/",
    "Bulletins/current/",
)

# Never take harvest's side for these, even if a prefix accidentally matches.
PROTECTED_SOURCE_PREFIXES = (
    "parishes/recipes/",
    "harvester/",
    "tests/",
    "extension/",
    ".github/",
)


def _normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_generated_mega_pdf(path: str) -> bool:
    """True for generated binaries under mega_pdf/ or docs/mega_pdf/."""
    normalized = _normalize_repo_path(path)
    if not normalized.endswith(".pdf"):
        return False
    return any(normalized.startswith(prefix) for prefix in MEGA_PDF_PREFIXES)


def is_protected_source_path(path: str) -> bool:
    """True for recipes, harvester code, tests, extension, and workflows."""
    normalized = _normalize_repo_path(path)
    return any(normalized.startswith(prefix) for prefix in PROTECTED_SOURCE_PREFIXES)


def is_generated_harvest_output(path: str) -> bool:
    """True for files this harvest generated and may safely keep on conflict."""
    normalized = _normalize_repo_path(path)
    if is_protected_source_path(normalized):
        return False
    if normalized in GENERATED_HARVEST_FILES:
        return True
    if is_generated_mega_pdf(normalized):
        return True
    return any(normalized.startswith(prefix) for prefix in GENERATED_HARVEST_PREFIXES)


def _run_git(
    repo: Path,
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=capture,
        text=True,
        env=env,
    )


def git_dir(repo: Path) -> Path:
    raw = _run_git(repo, ["rev-parse", "--git-dir"]).stdout.strip()
    path = Path(raw)
    return path if path.is_absolute() else repo / path


def in_rebase(repo: Path) -> bool:
    gd = git_dir(repo)
    return (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists()


def in_merge(repo: Path) -> bool:
    return (git_dir(repo) / "MERGE_HEAD").exists()


def harvest_side_flag(repo: Path) -> str:
    """Checkout flag that selects the newly generated harvest files."""
    if in_rebase(repo):
        return "--theirs"
    return "--ours"


def unmerged_paths(repo: Path) -> list[str]:
    out = _run_git(repo, ["diff", "--name-only", "--diff-filter=U"]).stdout
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _copy_repo_file(src_root: Path, dest_root: Path, rel: str) -> bool:
    src = src_root / rel
    if not src.is_file():
        return False
    target = dest_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return True


def snapshot_mega_pdfs(repo: Path, dest: Path) -> list[str]:
    """Copy current mega PDFs so a later rebase can restore this harvest's files."""
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for prefix in MEGA_PDF_DIR_NAMES:
        src_dir = repo / prefix
        if not src_dir.is_dir():
            continue
        for pdf in sorted(src_dir.glob("*.pdf")):
            rel = f"{prefix}/{pdf.name}"
            if _copy_repo_file(repo, dest, rel):
                copied.append(rel)
    return copied


def restore_mega_pdfs(repo: Path, snapshot: Path) -> list[str]:
    """Write snapshotted harvest megas back into the worktree."""
    restored: list[str] = []
    for prefix in MEGA_PDF_DIR_NAMES:
        src_dir = snapshot / prefix
        if not src_dir.is_dir():
            continue
        for pdf in sorted(src_dir.glob("*.pdf")):
            rel = f"{prefix}/{pdf.name}"
            if _copy_repo_file(snapshot, repo, rel):
                restored.append(rel)
    return restored


def snapshot_harvest_outputs(repo: Path, dest: Path) -> list[str]:
    """Copy generated harvest files so rebase can restore this job's versions."""
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    seen: set[str] = set()

    def _take(rel: str) -> None:
        if rel in seen:
            return
        if _copy_repo_file(repo, dest, rel):
            seen.add(rel)
            copied.append(rel)

    for rel in sorted(GENERATED_HARVEST_FILES):
        _take(rel)
    for rel in snapshot_mega_pdfs(repo, dest):
        if rel not in seen:
            seen.add(rel)
            copied.append(rel)

    extra_dirs = (
        "docs/mega_pdf",
        "docs/dioceses",
        "docs/parishes",
        "Bulletins/current",
    )
    for prefix in extra_dirs:
        src_dir = repo / prefix
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(repo).as_posix()
            if is_generated_harvest_output(rel):
                _take(rel)
    return copied


def _resolve_conflicts_for(
    repo: Path,
    *,
    snapshot: Path | None,
    keep: Callable[[str], bool],
) -> tuple[list[str], list[str]]:
    unresolved = unmerged_paths(repo)
    matched = [path for path in unresolved if keep(path)]
    leftover = [path for path in unresolved if path not in matched]
    if not matched:
        return [], leftover

    flag = harvest_side_flag(repo)
    for path in matched:
        dest = repo / path
        snap_file = (snapshot / path) if snapshot is not None else None
        if snap_file is not None and snap_file.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snap_file, dest)
        else:
            _run_git(repo, ["checkout", flag, "--", path])
        _run_git(repo, ["add", "--", path])
    return matched, leftover


def resolve_mega_pdf_conflicts(
    repo: Path,
    snapshot: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve mega PDF conflicts so this harvest's files win.

    Returns ``(resolved_paths, leftover_unmerged_paths)``.
    """
    return _resolve_conflicts_for(repo, snapshot=snapshot, keep=is_generated_mega_pdf)


def resolve_harvest_output_conflicts(
    repo: Path,
    snapshot: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve generated harvest-output conflicts so this job's files win.

    Recipes, harvester code, and other source files stay in leftover.
    """
    return _resolve_conflicts_for(
        repo, snapshot=snapshot, keep=is_generated_harvest_output
    )


def continue_git_integration(repo: Path) -> None:
    """Finish the in-progress rebase or merge without opening an editor."""
    editor_env = {"GIT_EDITOR": "true", "GIT_SEQUENCE_EDITOR": "true"}
    if in_rebase(repo):
        _run_git(
            repo,
            ["-c", "core.editor=true", "rebase", "--continue"],
            extra_env=editor_env,
        )
        return
    if in_merge(repo):
        _run_git(
            repo,
            ["-c", "core.editor=true", "commit", "--no-edit"],
            extra_env=editor_env,
        )


def abort_git_integration(repo: Path) -> None:
    if in_rebase(repo):
        _run_git(repo, ["rebase", "--abort"], check=False)
    elif in_merge(repo):
        _run_git(repo, ["merge", "--abort"], check=False)


def rebase_keeping_harvest_megas(repo: Path, remote_ref: str = "origin/main") -> None:
    """Rebase onto ``remote_ref``, keeping this harvest's generated outputs."""
    snapshot_dir = Path(tempfile.mkdtemp(prefix="harvest-outputs-"))
    try:
        snapshot_harvest_outputs(repo, snapshot_dir)
        result = _run_git(
            repo,
            ["rebase", "--autostash", remote_ref],
            check=False,
        )
        if result.returncode == 0:
            return
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")
        resolved, leftover = resolve_harvest_output_conflicts(repo, snapshot_dir)
        if leftover:
            abort_git_integration(repo)
            raise RuntimeError(
                "Rebase conflicted on source files that cannot be auto-resolved: "
                + ", ".join(leftover)
            )
        if not resolved:
            abort_git_integration(repo)
            raise RuntimeError(
                "Rebase failed without generated harvest-output conflicts to resolve"
            )
        print(
            "Resolved harvest output conflicts in favor of this harvest: "
            + ", ".join(resolved)
        )
        continue_git_integration(repo)
    finally:
        shutil.rmtree(snapshot_dir, ignore_errors=True)


def push_with_mega_conflict_retry(
    repo: Path,
    *,
    remote: str = "origin",
    branch: str = "main",
    attempts: int = 5,
) -> None:
    """Push HEAD to ``remote/branch``, rebasing and keeping this harvest's files."""
    for attempt in range(1, attempts + 1):
        push = _run_git(repo, ["push", remote, f"HEAD:{branch}"], check=False)
        if push.returncode == 0:
            print(f"✅ Pushed on attempt {attempt}")
            return
        if push.stdout:
            print(push.stdout, end="")
        if push.stderr:
            print(push.stderr, end="")
        print(f"⚠️  Push attempt {attempt} failed; fetching and rebasing…")
        fetch = _run_git(repo, ["fetch", remote, branch], check=False)
        if fetch.returncode != 0:
            print(fetch.stderr or fetch.stdout)
            raise SystemExit(1)
        try:
            rebase_keeping_harvest_megas(repo, f"{remote}/{branch}")
        except Exception as exc:
            print(f"❌ Rebase failed; aborting. {exc}")
            abort_git_integration(repo)
            raise SystemExit(1) from exc
    print(f"❌ Could not push after {attempts} attempts.")
    raise SystemExit(1)
