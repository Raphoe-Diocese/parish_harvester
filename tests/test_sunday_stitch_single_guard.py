"""Guard against double-running Sunday harvest safety checks.

The stitch job should snapshot status once before merging, then check the
post-merge count once. Repeating either step cannot provide extra coverage.
"""
from pathlib import Path


def test_sunday_stitch_uses_one_snapshot_and_one_guard():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/harvest.yml").read_text(
        encoding="utf-8"
    )
    stitch = workflow.split("\n  stitch:", 1)[1]

    snapshot = "- name: Snapshot parish_status before merge"
    guard = "- name: Guard ok count (block big drop)"
    merge = "- name: Merge slices, status, mega PDFs"

    assert stitch.count(snapshot) == 1
    assert stitch.count(merge) == 1
    assert stitch.count(guard) == 1
    assert stitch.index(snapshot) < stitch.index(merge) < stitch.index(guard)
    assert "--max-drop-ratio 0.10" in stitch
    assert "scripts/guard_ok_count.py" in stitch
