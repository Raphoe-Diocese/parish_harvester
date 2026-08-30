"""Search churchmedia JS for how newsletter PDFs are fetched."""
from __future__ import annotations

import re
import urllib.request

UA = "Mozilla/5.0"
URLS = [
    "https://churchmedia.tv/main-es2015.js",
    "https://churchmedia.tv/common-es2015.js",
    "https://churchmedia.tv/627-es2015.js",
    "https://churchmedia.tv/928-es2015.js",
    "https://churchmedia.tv/223-es2015.js",
    "https://churchmedia.tv/850-es2015.js",
    "https://churchmedia.tv/480-es2015.js",
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def main() -> None:
    for url in URLS:
        print("=" * 80)
        print(url)
        try:
            body = fetch(url)
        except Exception as exc:
            print("ERR", exc)
            continue
        print("len", len(body))
        for pat in (
            r".{0,60}newsletter.{0,80}",
            r".{0,40}newsLetter.{0,80}",
            r".{0,40}/newsletter/.{0,80}",
            r".{0,40}application/pdf.{0,40}",
            r".{0,40}cache\.churchmedia.{0,80}",
        ):
            hits = re.findall(pat, body, re.I)
            if hits:
                print("PAT", pat)
                for h in hits[:12]:
                    print(" ", h.replace("\n", " ")[:200])


if __name__ == "__main__":
    main()
