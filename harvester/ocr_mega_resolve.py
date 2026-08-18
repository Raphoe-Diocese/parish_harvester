"""Decide how OCR should obtain mega PDFs after a harvest.

Mega PDFs are produced only on full diocese harvests (not ``--target-parish``).
OCR must not fail or wipe prior viewers when a single-parish Send & test finishes.
"""

from __future__ import annotations

from typing import Any


def decide_ocr_mega_source(
    *,
    event_name: str,
    trigger_run_id: str | None = None,
    trigger_has_mega: bool = False,
    trigger_is_full_harvest: bool = False,
    fallback_run_id: str | None = None,
) -> dict[str, Any]:
    """Return OCR mega-PDF source decision.

    Keys:
      - skip (bool): when True, OCR should exit successfully without regenerating
      - run_id (str | None): Actions run to download ``*-mega-bulletin-pdf`` from
      - reason (str): human-readable explanation for logs / step summary
    """
    name = (event_name or "").strip().lower()
    trigger = (trigger_run_id or "").strip() or None
    fallback = (fallback_run_id or "").strip() or None

    if name == "workflow_dispatch":
        if fallback:
            return {
                "skip": False,
                "run_id": fallback,
                "reason": "Manual OCR — using latest harvest run that has mega PDF artifacts",
            }
        return {
            "skip": False,
            "run_id": None,
            "reason": "Manual OCR — no harvest mega artifacts found; will try GitHub Pages / checkout",
        }

    # workflow_run (and any other automatic trigger after harvest)
    if trigger_has_mega and trigger:
        return {
            "skip": False,
            "run_id": trigger,
            "reason": f"Using triggering harvest run {trigger} (has mega PDF artifact)",
        }

    if not trigger_is_full_harvest:
        return {
            "skip": True,
            "run_id": None,
            "reason": (
                "Triggering harvest has no mega PDF artifact "
                "(likely a single-parish Send & test). "
                "Skipping OCR so prior mega PDFs and searchable viewers stay valid."
            ),
        }

    # Full harvest ran but mega upload/stitch is missing — prefer prior mega, else Pages.
    if fallback:
        return {
            "skip": False,
            "run_id": fallback,
            "reason": (
                f"Full harvest run {trigger or 'unknown'} has no mega PDF artifact; "
                f"falling back to earlier harvest run {fallback}"
            ),
        }
    return {
        "skip": False,
        "run_id": None,
        "reason": (
            f"Full harvest run {trigger or 'unknown'} has no mega PDF artifact "
            "and no earlier mega run was found; will try GitHub Pages / checkout"
        ),
    }
