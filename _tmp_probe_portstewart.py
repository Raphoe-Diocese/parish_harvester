import re
import ssl
import urllib.request

URLS = [
    "https://portstewartparish.website/weekly-bulletin/",
    "http://portstewartparish.website/weekly-bulletin/",
    "https://portstewartparish.website/bulletins/",
    "http://portstewartparish.website/bulletins/",
]
CTX_OK = ssl.create_default_context()
CTX_BAD = ssl._create_unverified_context()
UA = {"User-Agent": "Mozilla/5.0 ParishHarvester"}


def fetch(url: str, verify: bool) -> tuple[int, str, bytes, str]:
    req = urllib.request.Request(url, headers=UA)
    ctx = CTX_OK if verify else CTX_BAD
    with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
        return resp.status, resp.geturl(), resp.read(), resp.headers.get("Content-Type", "")


def summarize(html: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    texts = re.findall(r">([^<]*\.pdf[^<]*)<", html, flags=re.I)
    mdocs = [h for h in hrefs if "mdocs-file" in h.lower() or ".pdf" in h.lower()]
    print("  sample mdocs/pdf hrefs:", mdocs[:20])
    print("  pdf texts:", texts[:15])
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S)
    print("  tr count:", len(rows))
    for i, row in enumerate(rows[:8]):
        clean = re.sub(r"<[^>]+>", " ", row)
        clean = re.sub(r"\s+", " ", clean).strip()[:220]
        hrefs_row = re.findall(r'href=["\']([^"\']+)["\']', row, flags=re.I)
        print(f"  row{i}: {clean}")
        print(f"   hrefs: {hrefs_row[:8]}")
    return mdocs


def get_pdf(url: str) -> None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=90, context=CTX_BAD) as resp:
            data = resp.read(32)
            print(
                "  FILE",
                url,
                "status",
                resp.status,
                "final",
                resp.geturl(),
                "ctype",
                resp.headers.get("Content-Type"),
                "disp",
                resp.headers.get("Content-Disposition"),
                "clen",
                resp.headers.get("Content-Length"),
                "magic",
                data[:8],
            )
    except Exception as exc:
        print("  FILE ERR", url, type(exc).__name__, exc)


def main() -> None:
    seen_mdocs: list[str] = []
    for url in URLS:
        print("===== TRY", url)
        ok = False
        for verify in (True, False):
            try:
                status, final, body, ctype = fetch(url, verify)
                print(
                    "  verify",
                    verify,
                    "status",
                    status,
                    "final",
                    final,
                    "bytes",
                    len(body),
                    "ctype",
                    ctype,
                )
                seen_mdocs = summarize(body.decode("utf-8", "replace"))
                ok = True
                break
            except Exception as exc:
                print("  verify", verify, "ERR", type(exc).__name__, exc)
        if ok:
            break
    if seen_mdocs:
        first = seen_mdocs[0]
        if first.startswith("/"):
            first = "http://portstewartparish.website" + first
        elif first.startswith("?"):
            first = "http://portstewartparish.website/" + first
        elif not first.startswith("http"):
            first = "http://portstewartparish.website/" + first.lstrip("/")
        print("===== FIRST MDOCS")
        get_pdf(first)
        https = first.replace("http://", "https://", 1)
        print("===== FIRST MDOCS HTTPS")
        get_pdf(https)


if __name__ == "__main__":
    main()
