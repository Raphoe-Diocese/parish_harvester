"""Probe Holy Cross Belfast listing + dated PDFs."""
from __future__ import annotations

import hashlib
import io
import re
import urllib.error
import urllib.request
from pathlib import Path

from PyPDF2 import PdfReader

OUT = Path("_tmp_holycross_probe")
OUT.mkdir(exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (compatible; parish-harvester-probe/1.0)"}
BASE = "http://www.holycrossparishbelfast.com"
LISTING = f"{BASE}/parishnews.html"
PDFS = [
    f"{BASE}/pdf/160826.pdf",
    f"{BASE}/pdf/090826.pdf",
    f"{BASE}/pdf/020826.pdf",
    f"{BASE}/pdf/260726.pdf",
    f"{BASE}/pdf/190726.pdf",
    f"{BASE}/pdf/120726.pdf",
    f"{BASE}/pdf/230826.pdf",
    f"{BASE}/pdf/170826.pdf",
    f"{BASE}/pdf/180826.pdf",
    f"{BASE}/pdf/190826.pdf",
    f"{BASE}/pdf/210826.pdf",
    f"{BASE}/GiftAidForm.pdf",
]
MESSENGER = [
    "https://theparishmessenger.com/",
    "https://www.theparishmessenger.com/",
    "https://theparishmessenger.com/holycross",
    "https://theparishmessenger.com/holy-cross",
    "https://theparishmessenger.com/belfast",
]


def fetch(url: str) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return exc.code, dict(exc.headers or {}), body


def pdf_info(data: bytes) -> dict:
    info: dict = {"magic": data[:8], "pages": None, "text_head": ""}
    try:
        reader = PdfReader(io.BytesIO(data))
        info["pages"] = len(reader.pages)
        bits = []
        for page in reader.pages[:3]:
            bits.append(page.extract_text() or "")
        info["text_head"] = "\n".join(bits)[:1200]
    except Exception as exc:
        info["err"] = f"{type(exc).__name__}: {exc}"
    return info


def main() -> None:
    print("=" * 80)
    print("LISTING", LISTING)
    status, headers, body = fetch(LISTING)
    print("status", status, "ct", headers.get("Content-Type"), "len", len(body))
    text = body.decode("utf-8", "replace")
    (OUT / "parishnews.html").write_text(text, encoding="utf-8")
    pdf_hrefs = sorted(set(re.findall(r"""(?:href|src)=['"]([^'"]+\.pdf[^'"]*)['"]""", text, re.I)))
    print("PDF HREFS", pdf_hrefs)
    print("messenger mentions", len(re.findall(r"parishmessenger|theparishmessenger", text, re.I)))
    # cards / dates
    for pat in (
        r"Sunday[^<]{0,80}",
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)[^<]{0,40}",
        r"\d{6}\.pdf",
        r"Newsletter[^<]{0,40}",
    ):
        hits = re.findall(pat, text, re.I)
        print("PAT", pat, "->", hits[:12])

    print("\n" + "=" * 80)
    print("DATED PDFS")
    hashes: dict[str, str] = {}
    for url in PDFS:
        print("-", url)
        try:
            status, headers, data = fetch(url)
        except Exception as exc:
            print("  ERR", type(exc).__name__, exc)
            continue
        ct = headers.get("Content-Type", "")
        md5 = hashlib.md5(data).hexdigest() if data else ""
        hashes[url] = md5
        print(f"  status={status} ct={ct} bytes={len(data)} md5={md5[:12]}")
        if data[:4] == b"%PDF":
            info = pdf_info(data)
            print(f"  pages={info.get('pages')} magic={info['magic']}")
            head = (info.get("text_head") or "").replace("\n", " | ")
            print("  text:", head[:400])
            name = url.rsplit("/", 1)[-1]
            (OUT / name).write_bytes(data)

    print("\nHASH GROUPS")
    groups: dict[str, list[str]] = {}
    for url, md5 in hashes.items():
        groups.setdefault(md5, []).append(url.rsplit("/", 1)[-1])
    for md5, names in groups.items():
        print(md5[:12], names)

    print("\n" + "=" * 80)
    print("MESSENGER")
    for url in MESSENGER:
        print("-", url)
        try:
            status, headers, data = fetch(url)
            print(f"  status={status} ct={headers.get('Content-Type')} bytes={len(data)}")
            loc = headers.get("Location") or headers.get("location")
            if loc:
                print("  location", loc)
        except Exception as exc:
            print("  ERR", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
