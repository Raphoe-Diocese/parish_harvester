#!/usr/bin/env python3
"""Batch-discover genuine weekly parish bulletin documents from research leads.

Never publishes a candidate or edits a parish recipe. Only records verified
PDF/image bytes with a date independently found in the link URL or caption.
A later per-parish harvest must still validate the actual bulletin masthead.
"""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from harvester.utils import extract_date_from_string, extract_date_from_slug

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "docs/discovery/research-queue-2026-11-15.json"
HARVEST_REPORT = ROOT / "Bulletins/report.json"
OUTPUT = ROOT / "docs/discovery/batch-bulletin-probes.json"
CURSOR = ROOT / "parishes/batch_probe_cursor.json"
ADDITIONAL = ROOT / "docs/discovery/additional-web-leads-2026-11-20.json"
USER_AGENT = "ParishPress-BatchDiscovery/1.0 (+https://www.parishpress.ie/)"
BAD = re.compile(r"gdpr|consent|standing.order|gift.aid|donat|privacy|cookie|safeguard|baptism.form|application.form|finance|accounts|lotto|raffle|poster|advert|logo|background|wedding", re.I)
GOOD = re.compile(r"newsletter|bulletin|parish.news|sunday|mass.sheet|weekly", re.I)
FILES = re.compile(r"\.(pdf|jpe?g|png)(?:$|[?#])", re.I)
SOCIAL = {"facebook.com", "instagram.com", "youtube.com", "x.com", "twitter.com", "tiktok.com"}
MAX_HTML = 1_250_000
MAX_FILE = 12_000_000


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def allowed(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("https", "http") and bool(p.hostname) and host(url) not in SOCIAL


def fetch(url: str, limit: int, timeout: int = 12) -> tuple[bytes, str, str]:
    if not allowed(url):
        return b"", "", ""
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,image/*;q=0.8,*/*;q=0.5"})
    try:
        with urlopen(req, timeout=timeout) as res:
            final = res.geturl()
            if not allowed(final):
                return b"", "", ""
            kind = res.headers.get("Content-Type", "").lower()
            length = res.headers.get("Content-Length")
            if length and length.isdigit() and int(length) > limit:
                return b"", kind, final
            data = res.read(limit + 1)
            if len(data) > limit:
                return b"", kind, final
            return data, kind, final
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return b"", "", ""


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href = ""
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.href = attrs.get("href", "")
            self.text = []
        elif tag == "img":
            src = attrs.get("src", "")
            alt = attrs.get("alt", "")
            if src:
                self.links.append((src, alt))

    def handle_data(self, data):
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, " ".join(self.text)))
            self.href = ""
            self.text = []


def parse_issue_date(blob: str, year: int) -> date | None:
    found = extract_date_from_string(blob) or extract_date_from_slug(blob)
    if found:
        return found
    # Captions such as "Sunday 15th November" without a year.
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s_-]+(January|February|March|April|May|June|July|August|September|October|November|December)\b", blob, re.I)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def verify_file(raw: bytes, url: str) -> str:
    path = urlparse(url).path.lower()
    if raw.startswith(b"%PDF-") and len(raw) > 2048:
        return "pdf"
    if raw.startswith(b"\xff\xd8\xff") and len(raw) > 2048 and path.endswith((".jpg", ".jpeg")):
        return "jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) > 2048 and path.endswith(".png"):
        return "png"
    return ""



def wordpress_media_candidates(page_url: str, sunday: date) -> list[str]:
    """Find dated newsletter files in the WordPress REST media library.

    Many WordPress homepages expose no PDF links. Only a dated *filename or
    title* matching the requested Sunday is accepted, never an upload date.
    """
    parsed = urlparse(page_url)
    if not parsed.hostname:
        return []
    api = f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/media?per_page=75&orderby=date&order=desc"
    raw, kind, _resolved = fetch(api, MAX_HTML, timeout=12)
    if not raw or ("json" not in kind and not raw.lstrip().startswith(b"[")):
        return []
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    results = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("source_url") or "")
        title = entry.get("title") or {}
        if isinstance(title, dict):
            title = str(title.get("rendered") or "")
        combined = urlparse(url).path.rsplit("/", 1)[-1] + " " + str(title)
        if not allowed(url) or not FILES.search(url):
            continue
        if BAD.search(combined) or not GOOD.search(combined):
            continue
        filename = urlparse(url).path.rsplit("/", 1)[-1]
        issue = parse_issue_date(filename, sunday.year) or parse_issue_date(str(title), sunday.year)
        if issue == sunday:
            results.append(url)
    return list(dict.fromkeys(results))[:5]


def probe_one(item: dict, sunday: date) -> dict:
    initial = str(item.get("url") or "")
    result = {"parish": item.get("matched_parish"), "name": item.get("name"),
              "seed": initial, "status_hint": item.get("status_hint"),
              "source_type": item.get("source_type"), "verdict": "not_verified"}
    if not allowed(initial):
        result["reason"] = "unsupported_or_social_source"
        return result
    if item.get("source_type") in ("mcn_live", "churchmedia", "google_drive"):
        result["reason"] = "specialised_api_needed"
        return result

    content, kind, final = fetch(initial, MAX_FILE if FILES.search(initial) else MAX_HTML)
    if not content:
        result["reason"] = "unreachable_or_too_large"
        return result
    if content.startswith(b"%PDF-"):
        from harvester.bulletin_freshness import heading_date_in_pdf_bytes
        name_date = parse_issue_date(urlparse(final).path, sunday.year)
        heading_date = heading_date_in_pdf_bytes(content, target=sunday)
        if heading_date == sunday and name_date in (sunday, None):
            result.update(verdict="candidate_verified_masthead",
                          document_url=final, file_kind="pdf",
                          issue_date=sunday.isoformat(), masthead_verified=True,
                          bytes=len(content),
                          reason="Direct PDF has target-Sunday masthead; parish identity still needs checking")
        else:
            result["reason"] = "direct_pdf_stale_or_undated"
        if result["verdict"] == "candidate_verified_masthead":
            return result
        # A dated old PDF is a historical pointer, NOT the weekly source.
        # Recover from its own WordPress parish host rather than immediately
        # discarding the entire lead; never pivot into a generic CDN or Drive.
        path = urlparse(final).path.lower()
        host_name = host(final)
        if ("/wp-content/uploads/" in path
                and "cdn" not in host_name
                and "google" not in host_name
                and "wordpress.com" not in host_name):
            root = urlparse(final)
            website = f"{root.scheme}://{root.netloc}/"
            content, kind, final = fetch(website, MAX_HTML)
            if not content:
                result["reason"] = "stale_pdf_and_website_unreachable"
                return result
            result["fallback_website"] = website
        else:
            return result
    if "html" not in kind and not content[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        result["reason"] = "not_html"
        return result
    page = Links()
    try:
        page.feed(content.decode("utf-8", "replace"))
    except ValueError:
        result["reason"] = "invalid_html"
        return result
    # A newsletter is often on an article one click beyond the homepage.
    # Probe only same-host bulletin/newsletter links, never generic navigation.
    # This expands coverage without giving arbitrary links a PDF verdict.
    article_urls = []
    for href, caption in page.links:
        sub = urljoin(final, href.strip())
        if (allowed(sub) and host(sub) == host(final)
                and not FILES.search(sub) and sub != final
                and GOOD.search(urlparse(sub).path + " " + caption)
                and not BAD.search(urlparse(sub).path + " " + caption)):
            article_urls.append(sub)
    expanded = list(page.links)
    for article in list(dict.fromkeys(article_urls))[:2]:
        subcontent, subtype, suburl = fetch(article, MAX_HTML)
        if not subcontent or "html" not in subtype:
            continue
        subpage = Links()
        subpage.feed(subcontent.decode("utf-8", "replace"))
        expanded.extend((urljoin(suburl or article, href), text) for href, text in subpage.links)

    candidates = []
    seen = set()
    for href, caption in expanded:
        url = urljoin(final, href.strip())
        if not allowed(url) or not FILES.search(url) or url in seen:
            continue
        seen.add(url)
        name = urlparse(url).path.rsplit("/", 1)[-1]
        blob = f"{name} {caption}"
        if BAD.search(blob) or not GOOD.search(blob):
            continue
        found = parse_issue_date(name, sunday.year) or parse_issue_date(caption, sunday.year)
        # Strict: only Sunday issue dates are automatically tagged as current.
        if found != sunday:
            continue
        candidates.append(url)
    if not candidates:
        # Broadly reusable recovery: WordPress media often holds the current
        # parish PDF when its homepage and archive pages have none.
        candidates.extend(wordpress_media_candidates(final, sunday))
    for url in candidates[:5]:
        body, ctype, resolved = fetch(url, MAX_FILE, timeout=20)
        file_kind = verify_file(body, resolved or url)
        if not file_kind:
            continue
        masthead_date = None
        if file_kind == "pdf":
            from harvester.bulletin_freshness import heading_date_in_pdf_bytes
            masthead_date = heading_date_in_pdf_bytes(body, target=sunday)
            # An older masthead invalidates a current-looking filename.
            if masthead_date is not None and masthead_date != sunday:
                continue
        confirmed_masthead = masthead_date == sunday
        result.update(
            verdict=("candidate_verified_masthead" if confirmed_masthead
                     else "candidate_verified_bytes_and_link_date"),
            document_url=resolved or url, file_kind=file_kind,
            issue_date=sunday.isoformat(), bytes=len(body),
            masthead_verified=confirmed_masthead,
            reason=("PDF masthead and link match target Sunday; parish identity still needs harvest check"
                    if confirmed_masthead else
                    "Document signature and link date verified; image-only or unreadable masthead needs OCR and parish identity check"),
        )
        return result
    result["reason"] = "no_current_dated_file_with_valid_bytes"
    result["candidate_links"] = len(candidates)
    return result


def run(queue: dict, state: dict, sunday: date, limit: int, workers: int) -> tuple[dict, dict]:
    leads = [r for r in queue.get("leads", []) if r.get("status_hint") != "downloaded"
             and r.get("validation") == "unverified_seed"]
    # Stable deduplication: scan each distinct URL once, even if multiple aliases exist.
    unique = list({str(x.get("url")): x for x in reversed(leads) if x.get("url")})
    unique.reverse()
    if not unique:
        return {"target_date": sunday.isoformat(), "rows": [], "summary": {}}, {"offset": 0}
    offset = int(state.get("offset", 0)) % len(unique)
    batch = (unique + unique)[offset:offset + min(limit, len(unique))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda r: probe_one(r, sunday), batch))
    verified = [r for r in rows if str(r.get("verdict", "")).startswith("candidate_verified_")]
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "target_date": sunday.isoformat(), "total_unresolved_leads": len(unique),
              "window_start": offset, "rows": rows,
              "summary": {"probed": len(rows), "verified_candidate_links": len(verified),
                          "not_verified": len(rows) - len(verified),
                          "requires_masthead_check": sum(not r.get("masthead_verified") for r in verified),
                          "masthead_verified": sum(bool(r.get("masthead_verified")) for r in verified)}}
    return report, {"offset": (offset + len(batch)) % len(unique), "target_date": sunday.isoformat()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--date", default="")
    args = ap.parse_args()
    now = datetime.now(timezone.utc).date()
    sunday = date.fromisoformat(args.date) if args.date else now - timedelta(days=(now.weekday() + 1) % 7)
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    if ADDITIONAL.exists():
        extra = json.loads(ADDITIONAL.read_text(encoding="utf-8"))
        queue["leads"] = (extra.get("leads") or []) + (queue.get("leads") or [])
    # Recover sources not represented among the old 456 user-supplied leads.
    # Downloaded parishes are deliberately excluded.
    if HARVEST_REPORT.exists():
        historic = json.loads(HARVEST_REPORT.read_text(encoding="utf-8"))
        live_rows = []
        for group in ("failed", "stale_rejected"):
            for row in historic.get(group, []):
                if row.get("url") and row.get("parish"):
                    live_rows.append({
                        "url": row["url"], "name": row.get("display_name") or row["parish"],
                        "matched_parish": row["parish"], "status_hint": group,
                        "validation": "unverified_seed", "source_type": "website",
                    })
        queue["leads"] = live_rows + queue["leads"]
    state = json.loads(CURSOR.read_text(encoding="utf-8")) if CURSOR.exists() else {}
    if state.get("target_date") != sunday.isoformat():
        state = {"offset": 0}
    report, new_state = run(queue, state, sunday, max(1, args.limit), max(1, min(32, args.workers)))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # Keep a full-week ledger, not only the last 120 probes. Results are
    # refreshed by seed URL on subsequent scans, preserving prior findings.
    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        if previous.get("target_date") == sunday.isoformat():
            ledger = {row["seed"]: row for row in previous.get("rows", []) if row.get("seed")}
            ledger.update({row["seed"]: row for row in report["rows"] if row.get("seed")})
            report["rows"] = list(ledger.values())
            report["summary"]["total_checked_this_week"] = len(ledger)
            report["summary"]["total_verified_links_this_week"] = sum(
                str(row.get("verdict", "")).startswith("candidate_verified_")
                for row in ledger.values()
            )
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    CURSOR.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
