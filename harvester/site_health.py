from __future__ import annotations

"""DNS-only parish site health probes — never mark slow or HTTP-only sites dead."""

import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_HEALTH_PATH = Path("parishes/site_health.json")
NXDOMAIN_STRIKES_FOR_INACTIVE = 2


def hostname_from_url(url: str) -> str | None:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    return host or None


def probe_dns(hostname: str) -> str:
    """Return ``ok``, ``nxdomain``, or ``error`` (transient — do not mark dead)."""
    host = (hostname or "").strip().lower()
    if not host:
        return "error"
    try:
        socket.getaddrinfo(host, None)
        return "ok"
    except socket.gaierror as exc:
        # Windows/Linux: [Errno 11001] getaddrinfo failed
        message = str(exc).lower()
        if "name or service not known" in message or "nodename nor servname" in message:
            return "nxdomain"
        if getattr(exc, "errno", None) in {8, -2, 11001}:
            return "nxdomain"
        return "error"
    except Exception:
        return "error"


def load_health(path: Path = DEFAULT_HEALTH_PATH) -> dict:
    if not path.exists():
        return {"updated_at": None, "parishes": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": None, "parishes": {}}
    if not isinstance(payload, dict):
        return {"updated_at": None, "parishes": {}}
    parishes = payload.get("parishes")
    if not isinstance(parishes, dict):
        parishes = {}
    return {"updated_at": payload.get("updated_at"), "parishes": parishes}


def _write_health(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def record_probe(
    parish_key: str,
    url: str,
    result: str,
    *,
    path: Path = DEFAULT_HEALTH_PATH,
) -> dict:
    """Update health record for one parish. Returns the parish entry."""
    data = load_health(path)
    parishes: dict = data["parishes"]
    entry = parishes.get(parish_key) if isinstance(parishes.get(parish_key), dict) else {}
    entry = dict(entry)

    if result == "ok":
        entry["nxdomain_strikes"] = 0
        entry["status"] = "ok"
        entry["last_result"] = "ok"
    elif result == "nxdomain":
        strikes = int(entry.get("nxdomain_strikes") or 0) + 1
        entry["nxdomain_strikes"] = strikes
        entry["last_result"] = "nxdomain"
        if strikes >= NXDOMAIN_STRIKES_FOR_INACTIVE:
            entry["status"] = "inactive_candidate"
        else:
            entry["status"] = "nxdomain_watch"
    else:
        # Timeout, refused, etc. — never escalate to dead automatically.
        entry["last_result"] = result
        if entry.get("status") not in {"inactive_candidate", "inactive"}:
            entry["status"] = entry.get("status") or "unknown"

    entry["url"] = url
    entry["hostname"] = hostname_from_url(url)
    entry["last_checked"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    parishes[parish_key] = entry
    data["parishes"] = parishes
    _write_health(path, data)
    return entry


def should_mark_inactive(entry: dict) -> bool:
    """True only after consecutive NXDOMAIN strikes (DNS truly dead)."""
    if not isinstance(entry, dict):
        return False
    strikes = int(entry.get("nxdomain_strikes") or 0)
    return strikes >= NXDOMAIN_STRIKES_FOR_INACTIVE and entry.get("last_result") == "nxdomain"
