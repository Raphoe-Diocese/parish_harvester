"""Find churchmedia.tv API / newsletter endpoints from SPA JS."""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
PAGE = "https://churchmedia.tv/st-patricks-church-2"
BASE = "https://churchmedia.tv/"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> None:
    html = fetch(PAGE).decode("utf-8", "replace")
    scripts = re.findall(r'src=["\']([^"\']+\.js)["\']', html)
    print("scripts", scripts)
    blobs: list[str] = []
    for src in scripts:
        if src.startswith("http"):
            url = src
        else:
            url = BASE + src.lstrip("/")
        if "gstatic" in url or "google" in url or "accounts.google" in url:
            continue
        print("FETCH", url)
        try:
            body = fetch(url).decode("utf-8", "replace")
        except Exception as exc:
            print("ERR", url, exc)
            continue
        print("  len", len(body))
        for pat in (
            r"https?://[^\"']{0,120}newsletter[^\"']{0,80}",
            r"/api/[^\"']{0,80}",
            r"churchmedia[^\"']{0,80}",
            r"View Our Latest Newsletter",
            r"newsLetter",
            r"newsletterUrl",
            r"itechmedia[^\"']{0,80}",
        ):
            hits = re.findall(pat, body, re.I)
            if hits:
                print("  PAT", pat, "->", hits[:15])
        # interesting string literals
        interesting = re.findall(
            r'["\'](/?(?:api|v1|v2|church|newsletter|webcam|parish)[^"\']{0,80})["\']',
            body,
            re.I,
        )
        uniq = []
        for x in interesting:
            if x not in uniq:
                uniq.append(x)
        print("  PATHS", uniq[:40])
        blobs.append(f"===== {url} len={len(body)} =====\n")
        # keep snippets around newsletter
        for m in re.finditer(r".{0,80}newsletter.{0,80}", body, re.I):
            blobs.append(m.group(0) + "\n")

    Path("_tmp_probe_portaferry_api.txt").write_text("".join(blobs)[:20000], encoding="utf-8")


if __name__ == "__main__":
    main()
