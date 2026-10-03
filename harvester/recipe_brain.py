"""Recipe Brain — remember which hub trick won, reuse it on the next parish.

This is not a 24/7 crawler. Harvest still runs on GitHub Actions.
hint_for_url() is the click-memory slice: one proved host must suggest
the same recipe shape for the next similar URL.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class HubHint:
    """A remembered trick for a bulletin host."""

    key: str
    site_type: str
    label: str
    confidence: str
    notes: tuple[str, ...]
    do_not: tuple[str, ...]


def _host(url: str) -> str:
    host = urlparse((url or "").strip()).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def hint_for_url(url: str) -> HubHint | None:
    """Return the remembered hub trick for *url*, or None."""
    raw = (url or "").strip()
    if not raw:
        return None
    host = _host(raw)
    path = urlparse(raw).path.lower()

    if host in {"mcn.live", "www.mcn.live"} or "mcn.live" in host:
        return HubHint(
            key="mcn_live",
            site_type="mcn_live_parish_page",
            label="MCN camera page newsletter (JSON, not the webcam)",
            confidence="high",
            notes=(
                "Newsletter sits on the MCN camera page. Harvest uses the profile JSON, not the stream.",
                "Start at the /Camera/ URL Frank trained. Do not pin a dated PDF.",
            ),
            do_not=(
                "Do not harvest the webcam video.",
                "Do not pin a dated newsletter filename.",
            ),
        )

    if host == "churchmedia.tv":
        return HubHint(
            key="churchmedia",
            site_type="churchmedia_newsletter",
            label="churchmedia.tv latest newsletter button",
            confidence="high",
            notes=(
                "Use getChannelAbout for this week's PDF. Portaferry proved this.",
                "The public /newsletter/<token> path dies on the next upload.",
            ),
            do_not=(
                "Do not pin churchmedia /newsletter/<token>.….pdf.",
            ),
        )

    if host == "mayo.ie" or path.startswith("/getmedia/"):
        return HubHint(
            key="mayo_ie",
            site_type="http_scrape_newest_pdf",
            label="Mayo County Council parish-newsletters listing",
            confidence="high",
            notes=(
                "Belmullet proved GET 200 on mayo.ie parish-newsletters. Date is in the link text and filename.",
                "Scrape the listing each week. The getmedia GUID changes.",
            ),
            do_not=(
                "Do not pin the getmedia GUID.",
                "Do not treat a PNG as a PDF recipe.",
            ),
        )

    if host in {"churchservices.tv", "www.churchservices.tv"}:
        return HubHint(
            key="churchservices_tv",
            site_type="link_only",
            label="churchservices.tv webcam — pointer only until a newsletter file is proved",
            confidence="low",
            notes=(
                "Webcam first. Look on the same page for a newsletter link. Else keep the real parish site.",
            ),
            do_not=(
                "Do not harvest the livestream as a bulletin.",
                "Do not invent a PDF because a webcam exists.",
            ),
        )

    if path.rstrip("/").endswith("current-newsletter"):
        return HubHint(
            key="current_newsletter_redirect",
            site_type="permanent_redirect_document",
            label="Permanent /current-newsletter/ path (Kildare / Naas pattern)",
            confidence="high",
            notes=(
                "Same URL every week. It redirects to this Sunday's PDF. Do not pin the dated upload.",
            ),
            do_not=("Do not pin the dated wp-content filename.",),
        )

    return None
