from pathlib import Path

sp = Path("extension/sidepanel.js")
text = sp.read_text(encoding="utf-8")
start = text.find("async function _problemsDeadPollRemoved_DELETED(parishKey) {")
if start < 0:
    start = text.find("async function _problemsDeadPollRemoved(parishKey) {")
end = text.find("async function _problemsWatchParishHarvest(parishKey, displayName, dispatchAt) {")
if start < 0 or end < 0 or end <= start:
    raise SystemExit(f"sidepanel markers missing start={start} end={end}")
sp.write_text(text[:start] + text[end:], encoding="utf-8")
print("sidepanel removed", end - start, "chars")

cj = Path("extension/content.js")
c = cj.read_text(encoding="utf-8")
marker = "      /* removed unused report.json harvest-line fallback */"
if marker in c:
    a = c.find(marker)
    b = c.find("      let resolvedDiocese = \"\";", a)
    if b < 0:
        raise SystemExit("content.js end marker missing")
    cj.write_text(c[:a] + c[b:], encoding="utf-8")
    print("content removed leftover if(false) block", b - a, "chars")
else:
    marker2 = "        return;\n        const settings = await _storageGet([\"gh_repo\"]);"
    if marker2 in c:
        a = c.find(marker2)
        # keep function close before the return
        # find preceding `      };` after we drop from return
        b = c.find("      let resolvedDiocese = \"\";", a)
        if b < 0:
            raise SystemExit("content.js diocese marker missing")
        # ensure _refreshHarvestStatusLine is closed
        prefix = c[:a].rstrip()
        if not prefix.endswith("};"):
            prefix = prefix + "\n      };\n\n"
        else:
            prefix = prefix + "\n\n"
        cj.write_text(prefix + c[b:], encoding="utf-8")
        print("content removed dead return-fallback")
    else:
        print("content: no leftover harvest fallback found")
