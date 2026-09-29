"""
picker_challenge.py — Referee Brain slice 1b.

When a recipe pin / predicted dated URL is about to be harvested, compare it
to dated PDFs on the listing page. If the listing has a *newer* dated file,
re-pick that file and log ``picker_wrong`` so the stale pin is not quietly
written into the mega PDF / OCR.

Locked 23/09/2026 (Frank). Slice 1a was stale-harder (masthead dates).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import unquote

from .bulletin_freshness import MAX_STALE_DAYS_FROM_TARGET, WEEK_LOOKBACK_DAYS


@dataclass(frozen=True)
class PickerChallengeVerdict:
    """Result of comparing a pin URL against listing candidates."""

    chosen_url: str
    challenged: bool
    pin_date: date | None
    listing_date: date | None
    reason: str = ""

    @property
    def log_line(self) -> str:
        if not self.challenged:
            return ""
        return self.reason or "picker_wrong"


def _norm_url(url: str) -> str:
    return unquote((url or "").strip()).rstrip("/").lower()


def challenge_pin_against_listing(
    pin_url: str,
    scored_listing: list[tuple[date, str]],
    target_date: date,
) -> PickerChallengeVerdict:
    """Pick pin or a newer listing PDF.

    *scored_listing* is the output of ``_score_http_scrape_pdf_hrefs`` (or any
    ``(date, url)`` list). Equal dates keep the pin (no churn). Listing dates
    outside the harvest week + ahead-grace window never beat the pin.
    """
    pin = (pin_url or "").strip()
    if not pin:
        return PickerChallengeVerdict(
            chosen_url=pin,
            challenged=False,
            pin_date=None,
            listing_date=None,
        )

    # Lazy import avoids a circular import with replay at module load.
    from .replay import _http_scrape_item_date

    pin_date = _http_scrape_item_date(pin, target_date)
    if not scored_listing:
        return PickerChallengeVerdict(
            chosen_url=pin,
            challenged=False,
            pin_date=pin_date,
            listing_date=None,
        )

    week_start = target_date - timedelta(days=WEEK_LOOKBACK_DAYS)
    ahead = target_date + timedelta(days=MAX_STALE_DAYS_FROM_TARGET)
    in_window = [
        (d, u)
        for d, u in scored_listing
        if week_start <= d <= ahead and _norm_url(u) != _norm_url(pin)
    ]
    if not in_window:
        return PickerChallengeVerdict(
            chosen_url=pin,
            challenged=False,
            pin_date=pin_date,
            listing_date=max(scored_listing)[0],
        )

    best_date, best_url = max(in_window, key=lambda item: item[0])

    if pin_date is None:
        reason = (
            f"picker_wrong: undated pin beaten by listing "
            f"{best_date.isoformat()} {best_url}"
        )
        return PickerChallengeVerdict(
            chosen_url=best_url,
            challenged=True,
            pin_date=None,
            listing_date=best_date,
            reason=reason,
        )

    if best_date > pin_date:
        reason = (
            f"picker_wrong: pin {pin_date.isoformat()} beaten by listing "
            f"{best_date.isoformat()} {best_url}"
        )
        return PickerChallengeVerdict(
            chosen_url=best_url,
            challenged=True,
            pin_date=pin_date,
            listing_date=best_date,
            reason=reason,
        )

    return PickerChallengeVerdict(
        chosen_url=pin,
        challenged=False,
        pin_date=pin_date,
        listing_date=best_date,
    )
