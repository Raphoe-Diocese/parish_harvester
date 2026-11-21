"""Collect attributed profile evidence from official church and parish office pages.

Run python -m scripts.parish_profile_review URL [URL ...] > profile-review.json
Review church, parish office and effective dates before publishing.
"""
import argparse
from datetime import date
import json
from urllib.parse import urlparse

from scripts.batch_bulletin_probe import MAX_HTML, fetch
from playwright.sync_api import Error as BrowserError, sync_playwright


def read_page(page, url):
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Expected an HTTP or HTTPS parish page")
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except BrowserError:
        # Some hosts only respond to the HTTP client. Keep the real origin so
        # relative map and contact links still resolve on the rendered page.
        body, kind, resolved = fetch(url, MAX_HTML)
        if not body or "html" not in kind:
            raise
        def offline_route(route):
            if route.request.is_navigation_request() and route.request.url == resolved:
                route.fulfill(body=body, content_type=kind)
            else:
                route.abort()
        page.route("**/*", offline_route)
        try:
            response = page.goto(resolved, wait_until="domcontentloaded", timeout=25000)
        finally:
            page.unroute("**/*", offline_route)
    if not response or not response.ok:
        raise ValueError(f"Parish page returned {response.status if response else 'no response'}")
    return {
        "source": page.url, "checked": date.today().isoformat(),
        "title": page.title(), "status": "requires_review",
        **page.evaluate(r"""() => {
            const root = document.querySelector('main, article') || document.body;
            const links = [...document.querySelectorAll('a[href]')];
            const contacts = links.filter(a => /^(tel:|mailto:)/i.test(a.getAttribute('href')))
                .map(a => ({label: a.innerText.trim(), href: a.getAttribute('href')}));
            const maps = [...document.querySelectorAll('a[href],iframe[src]')]
                .map(e => e.href || e.src).filter(u => /^https?:/.test(u) &&
                    /maps\.app\.goo\.gl|google\.[^/]+\/maps|maps\.google\.|openstreetmap\.org/i.test(u));
            const sections = [];
            for (const heading of root.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
                if (!/mass|aifreann|aifrinn|adoration|confession|reconciliation|office|contact|address/i.test(heading.innerText)) continue;
                const lines = [];
                let element = heading.nextElementSibling;
                while (element && !element.matches('h1,h2,h3,h4,h5,h6') && !element.querySelector('h1,h2,h3,h4,h5,h6')) {
                    if (element.innerText?.trim()) lines.push(element.innerText.trim());
                    element = element.nextElementSibling;
                }
                if (lines.length) sections.push({heading: heading.innerText.trim(), text: lines.join('\n')});
            }
            return {contacts, maps: [...new Set(maps)], sections};
        }"""),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="+")
    rows = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for url in parser.parse_args().urls:
            try:
                rows.append(read_page(page, url))
            except (ValueError, BrowserError) as exc:
                rows.append({"source": url, "status": "unavailable", "reason": str(exc)})
        browser.close()
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
