"""Keep newly generated mega PDFs when harvest git rebase/merge hits conflicts.

Binary ``*_mega_bulletin.pdf`` files cannot be auto-merged. Tonight's full
harvest failed on push with ``CONFLICT (add/add)`` for each diocese mega.
This helper prefers the files this harvest just produced, then continues.

Rebase vs merge (git's ours/theirs is reversed):

* rebase / pull --rebase: ``--theirs`` is the replayed harvest commit
* merge / pull (merge): ``--ours`` is the current harvest branch
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

MEGA_PDF_DIR_NAMES = ("mega_pdf", "docs/mega_pdf")
MEGA_PDF_PREFIXES = tuple(f"{name}/" for name in MEGA_PDF_DIR_NAMES)


def is_generated_mega_pdf(path: str) -> bool:
    """True for generated binaries under mega_pdf/ or docs/mega_pdf/."""
    normalized = path.replace("\\", "/").lstrip("./")
    if not normalized.endswith(".pdf"):
        return False
    return any(normalized.startswith(prefix) for prefix in MEGA_PDF_PREFIXES)


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


def snapshot_mega_pdfs(repo: Path, dest: Path) -> list[str]:
    """Copy current mega PDFs so a later rebase can restore this harvest's files."""
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for prefix in MEGA_PDF_DIR_NAMES:
        src_dir = repo / prefix
        if not src_dir.is_dir():
            continue
        for pdf in sorted(src_dir.glob("*.pdf")):
            target = dest / prefix / pdf.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, target)
            copied.append(f"{prefix}/{pdf.name}")
    return copied


def restore_mega_pdfs(repo: Path, snapshot: Path) -> list[str]:
    """Write snapshotted harvest megas back into the worktree."""
    restored: list[str] = []
    for prefix in MEGA_PDF_DIR_NAMES:
        src_dir = snapshot / prefix
        if not src_dir.is_dir():
            continue
        for pdf in sorted(src_dir.glob("*.pdf")):
            target = repo / prefix / pdf.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf, target)
            restored.append(f"{prefix}/{pdf.name}")
    return restored


def resolve_mega_pdf_conflicts(
    repo: Path,
    snapshot: Path | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve mega PDF conflicts so this harvest's files win.

    Returns ``(resolved_paths, leftover_unmerged_paths)``.
    """
    unresolved = unmerged_paths(repo)
    mega_conflicts = [path for path in unresolved if is_generated_mega_pdf(path)]
    leftover = [path for path in unresolved if path not in mega_conflicts]
    if not mega_conflicts:
        return [], leftover

    flag = harvest_side_flag(repo)
    for path in mega_conflicts:
        dest = repo / path
        snap_file = (snapshot / path) if snapshot is not None else None
        if snap_file is not None and snap_file.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snap_file, dest)
        else:
            _run_git(repo, ["checkout", flag, "--", path])
        _run_git(repo, ["add", "--", path])
    return mega_conflicts, leftover


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
    """Rebase onto ``remote_ref``, keeping this harvest's mega PDFs on conflict."""
    snapshot_dir = Path(tempfile.mkdtemp(prefix="harvest-megas-"))
    try:
        snapshot_mega_pdfs(repo, snapshot_dir)
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
        resolved, leftover = resolve_mega_pdf_conflicts(repo, snapshot_dir)
        if leftover:
            abort_git_integration(repo)
            raise RuntimeError(
                "Rebase conflicted on non-mega files that cannot be auto-resolved: "
                + ", ".join(leftover)
            )
        if not resolved:
            abort_git_integration(repo)
            raise RuntimeError("Rebase failed without mega PDF conflicts to resolve")
        print(
            "Resolved mega PDF conflicts in favor of this harvest: "
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
    """Push HEAD to ``remote/branch``, rebasing and keeping new megas on conflict."""
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
