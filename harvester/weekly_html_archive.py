"""Print one dated issue from a text-only HTML archive with Sunday headings."""
from datetime import date
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re

import fitz

from .utils import extract_date_from_string


class WeeklyIssueParser(HTMLParser):
    blocks = {"p", "ul", "ol", "li", "br", "h1", "h2", "h3", "h4", "strong", "em", "table", "tr", "td", "th"}

    def __init__(self, target: date):
        super().__init__()
        self.target = target
        self.heading = None
        self.collect = False
        self.complete = False
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.skip += 1
        elif not self.skip and tag == "h1":
            self.heading = []
        elif self.collect and self.heading is None and tag in self.blocks:
            self.parts.append(f"<{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        if self.heading is not None:
            self.heading.append(data)
        elif self.collect:
            self.parts.append(escape(data))

    def handle_endtag(self, tag):
        if tag in {"style", "script"}:
            self.skip = max(0, self.skip - 1)
        elif tag == "h1" and self.heading is not None:
            title = " ".join("".join(self.heading).split())
            self.heading = None
            if re.fullmatch(r"Sunday,?\s+\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+20\d{2}", title, re.I):
                if self.collect:
                    self.complete = True
                self.collect = not self.complete and extract_date_from_string(title) == self.target
            if self.collect:
                self.parts.append(f"<h1>{escape(title)}</h1>")
        elif self.collect and self.heading is None and tag in self.blocks and tag != "br":
            self.parts.append(f"</{tag}>")


def write_weekly_html_issue(html: str, target: date, dest: Path) -> bool:
    parser = WeeklyIssueParser(target)
    parser.feed(html)
    parser.close()
    if not parser.complete:
        return False
    story = fitz.Story(html="".join(parser.parts))
    sheet = fitz.paper_rect("a4")
    with fitz.DocumentWriter(str(dest)) as writer:
        story.write(writer, lambda *_: (sheet, sheet + (42, 42, -42, -42), None))
    return True
