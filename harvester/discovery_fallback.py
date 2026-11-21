"""Conservative, current-week recovery from the saved batch discovery ledger.

A failed trained recipe must not hide a PDF that the independent parallel
scanner already found. This fallback re-downloads and verifies the PDF itself;
it does not treat a ledger row, changed URL, or HTTP 200 as proof of freshness.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

_LEDGER = Path(__file__).resolve().parent.parent / "docs" / "discovery" / "batch-bulletin-probes.json"
_SHARED_HOSTS = {
    "churchtv.ie",
    "parishestogether.ie",
    "bantryfamilyofparishes.ie",
    "sma.ie",
}


def _host(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return parsed.hostname.lower().removeprefix("www.")


def eligible_discovery_url(
    parish_key: str,
    target: date,
    origins: list[str],
    *,
    ledger_path: Path = _LEDGER,
) -> str | None:
    """Only exact, masthead-proved PDF matches on the parish's own host."""
    try:
        ledger = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(ledger, dict) or ledger.get("target_date") != target.isoformat():
        return None
    origin_hosts = {_host(source) for source in origins if source}
    origin_hosts.discard("")
    if not origin_hosts:
        return None
    for row in reversed(ledger.get("rows") or []):
        if not isinstance(row, dict):
            continue
        if (
            str(row.get("parish") or "") != parish_key
            or row.get("verdict") != "candidate_verified_masthead"
            or row.get("masthead_verified") is not True
            or row.get("issue_date") != target.isoformat()
            or row.get("file_kind") != "pdf"
        ):
            continue
        url = str(row.get("document_url") or "").strip()
        parsed = urlparse(url)
        host = _host(url)
        if (
            parsed.scheme != "https"
            or not parsed.path.lower().endswith(".pdf")
            or host not in origin_hosts
            or host in _SHARED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
        ):
            continue
        return url
    return None


def fetch_verified_discovery_pdf(
    parish_key: str,
    target: date,
    origins: list[str],
    dest: Path,
    *,
    ledger_path: Path = _LEDGER,
) -> str | None:
    """Download current-week bytes and re-check the printed PDF masthead.

    Caller runs this via asyncio.to_thread on a failed recipe, and then uses
    the ordinary PDF/size/page/staleness referee before accepting the result.
    """
    url = eligible_discovery_url(
        parish_key, target, origins, ledger_path=ledger_path
    )
    if not url:
        return None
    from .replay import _fetch_bytes_with_retries
    from .bulletin_freshness import heading_date_in_pdf_bytes

    hit = _fetch_bytes_with_retries(
        url, max_attempts=4, per_attempt_timeout_s=8.0,
        total_budget_s=25.0, want_file=True,
    )
    if not hit:
        return None
    body, _headers = hit
    if not body.startswith(b"%PDF-") or len(body) < 4096:
        return None
    if heading_date_in_pdf_bytes(body, target=target) != target:
        return None
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(body)
    return url
