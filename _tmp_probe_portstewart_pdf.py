import ssl
import urllib.request

URL = "https://portstewartparish.website/?mdocs-file=9538"
req = urllib.request.Request(
    URL,
    headers={"User-Agent": "Mozilla/5.0 ParishHarvester"},
)
ctx = ssl._create_unverified_context()
with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
    data = resp.read()
    print("status", resp.status)
    print("final", resp.geturl())
    print("ctype", resp.headers.get("Content-Type"))
    print("disp", resp.headers.get("Content-Disposition"))
    print("len", len(data))
    print("magic", data[:8])
    print("pdf", data[:5] == b"%PDF-")
