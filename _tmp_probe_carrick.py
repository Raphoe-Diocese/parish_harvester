import io
import re
import urllib.request
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from harvester.bulletin_freshness import check_bulletin_freshness, extract_bulletin_date
from harvester.utils import extract_date_from_string

UA = "Mozilla/5.0 (compatible; ParishHarvester/1.0)"
TARGET = date(2026, 8, 16)

CANDIDATES = {
    "mass_times_from_17_aug": "https://www.carrickparish.org/_files/ugd/18d125_e29380ad624948a7b3dfdebf8a26fb4f.pdf",
    "final_summer": "https://www.carrickparish.org/_files/ugd/18d125_02051fa18f7e40b2baca445517fe43dd.pdf",
    "fr_davis": "https://www.carrickparish.org/_files/ugd/18d125_b8602e08bb144d4b9a025c905b415630.pdf",
    "unlabeled": "https://www.carrickparish.org/_files/ugd/18d125_593092963abf434abc12c3fd7104b6d4.pdf",
    "old_recipe_hash": "https://www.carrickparish.org/_files/ugd/18d125_e29380ad624948a7b3dfdebf8a26fb4f.pdf",
}

PAGES = [
    "https://www.carrickparish.org/",
    "https://www.carrickparish.org/info",
    "https://www.carrickparish.org/registration",
    "https://www.carrickparish.org/events",
]


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.status, dict(resp.headers), resp.read()


def pdf_text(body: bytes, max_chars: int = 1800) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(body))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages)
    return len(reader.pages), text[:max_chars]


for name, url in CANDIDATES.items():
    print(f"=== PDF {name} ===")
    try:
        status, headers, body = get(url)
    except Exception as exc:
        print("ERROR", exc)
        print()
        continue
    print("status", status, "bytes", len(body), "ct", headers.get("Content-Type"), "magic", body[:8])
    print("is_pdf", body.startswith(b"%PDF"))
    if body.startswith(b"%PDF"):
        Path(f"_tmp_proof_carrick_{name}.pdf").write_bytes(body)
        pages, text = pdf_text(body)
        print("pages", pages)
        print("url_date", extract_date_from_string(url), "bulletin_date", extract_bulletin_date(url))
        print("freshness", check_bulletin_freshness(url, TARGET))
        print("text_date", extract_date_from_string(text), "text_bulletin_date", extract_bulletin_date(text))
        print("freshness_text", check_bulletin_freshness(text, TARGET))
        print("--- text ---")
        print(text)
    print()

print("=== PAGES ===")
for url in PAGES:
    print(f"--- {url} ---")
    try:
        status, headers, body = get(url)
    except Exception as exc:
        print("ERROR", exc)
        continue
    html = body.decode("utf-8", errors="ignore")
    print("status", status, "bytes", len(body), "ct", headers.get("Content-Type"))
    hrefs = re.findall(r"""href=["']([^"']+)["']""", html, flags=re.I)
    texts = re.findall(r"<a[^>]*>(.*?)</a>", html, flags=re.I | re.S)
    print("mass times mentions:", len(re.findall(r"Mass Times", html, flags=re.I)))
    print("bulletin mentions:", len(re.findall(r"bulletin|newsletter", html, flags=re.I)))
    pdfs = [h for h in hrefs if ".pdf" in h.lower() or "/ugd/" in h.lower()]
    for h in pdfs[:20]:
        print(" ", h)
    for needle in ("Mass Times", "Weekly", "August", "Sunday", "newsletter", "bulletin"):
        if needle.lower() in html.lower():
            print("contains", needle)
    print()
