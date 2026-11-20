"""Ensure weekly harvest cannot silently mutate trained bulletin recipes.

The recipe health checker is deliberately read-only; the bulk autofixer is
a manual, reviewed repair tool and must not run in the harvest process.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARVEST_WORKFLOW = REPO / ".github" / "workflows" / "harvest.yml"


def test_harvest_keeps_reviewed_recipes_untouched():
    workflow = HARVEST_WORKFLOW.read_text(encoding="utf-8")
    assert "python scripts/autofix_recipes.py" not in workflow
    assert "python scripts/diagnose_recipe_health.py --json" in workflow
    assert workflow.index("Audit recipes without changing them") < workflow.index(
        "Run Bulletin Harvester"
    )


def test_harvest_keeps_failure_findings_in_a_retrievable_artifact():
    workflow = HARVEST_WORKFLOW.read_text(encoding="utf-8")
    assert "recipe-health.json" in workflow
    assert "recipe-audit-${{ github.run_id }}" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "Full findings are attached as a workflow artefact." in workflow


def test_recipe_audit_is_read_only():
    from scripts import diagnose_recipe_health

    text = Path(diagnose_recipe_health.__file__).read_text(encoding="utf-8")
    assert "write_text(" not in text
    assert ".unlink(" not in text
    assert "json.dumps(" in text
