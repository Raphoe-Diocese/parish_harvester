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


def test_blocked_stitch_preserves_candidate_without_approving_it_for_ocr():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/harvest.yml").read_text(encoding="utf-8")
    ocr = (root / ".github/workflows/ocr-bulletin.yml").read_text(encoding="utf-8")
    stitch = workflow.split("\\n  stitch:", 1)[1]

    candidate = "- name: Preserve unapproved stitch candidate"
    guard = "- name: Guard ok count (block big drop)"
    candidate_name = "harvest-diagnostic-candidate-${{ github.run_id }}"

    assert stitch.count(candidate) == 1
    assert stitch.index("- name: Merge slices, status, mega PDFs") < stitch.index(candidate)
    assert stitch.index(candidate) < stitch.index(guard)
    assert candidate_name in stitch
    assert "Bulletins/all_bulletins_*.pdf" in stitch
    assert "mega_pdf/*_mega_bulletin.pdf" in stitch
    assert "Bulletins/report.json" in stitch
    assert "parishes/parish_status.json" in stitch
    assert "retention-days: 14" in stitch[stitch.index(candidate) : stitch.index(guard)]
    assert 'test("mega-bulletin-pdf"; "i")' in ocr
    assert "mega-bulletin-pdf" not in candidate_name
