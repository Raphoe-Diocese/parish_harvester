# -*- coding: utf-8 -*-
import re, ssl, urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
CTX = ssl._create_unverified_context()


class A(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.items = []
        self._h = None
        self._t = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self._h = urljoin(self.base, d["href"].strip())
            self._t = ""

    def handle_data(self, data):
        if self._h is not None:
            self._t += data

    def handle_endtag(self, tag):
        if tag == "a" and self._h:
            self.items.append((" ".join(self._t.split())[:90], self._h))
            self._h = None


def show(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        html = r.read().decode("utf-8", "replace")
        final = r.geturl()
    p = A(final)
    p.feed(html)
    print("PAGE", url)
    for t, h in p.items:
        if any(x in (t + h).lower() for x in (".pdf", ".rtf", ".doc", "bulletin", "newsletter", "ugd", "august")):
            print(" ", t, "->", h)


show("https://www.truaghparish.com/")
show("https://kilmoredrumsnatt.com/past-newsletters/")
show("https://magheraclooneparish.com/wp-json/wp/v2/media?per_page=8&orderby=date&order=desc")
