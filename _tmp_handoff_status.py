import json

d = json.load(open("_tmp_status_truth.json", encoding="utf-8-sig"))
print("actionable", d.get("actionable_keys"))
print("---FAILED---")
for k, p in sorted(d["parishes"].items()):
    if p.get("outcome") == "failed" and p.get("actionable"):
        err = (p.get("error") or "").replace("\n", " ")[:140]
        print(k, "|", p.get("display_name"), "|", p.get("last_tested_at"), "|", err)
print("---STALE---")
for k, p in sorted(d["parishes"].items()):
    if p.get("outcome") == "stale" and p.get("actionable"):
        err = (p.get("error") or "").replace("\n", " ")[:140]
        print(k, "|", p.get("display_name"), "|", p.get("last_tested_at"), "|", err)
print("---WATCH---")
keys = (
    "errigalparish",
    "tawnawillyparish",
    "ballymenaparish",
    "parishoflisburn",
    "portstewartparish",
    "portaferryparish",
    "glenariffeparish",
    "holycrossparishbelfast",
    "carrickparish",
    "stoliverplunkettparish",
    "saintmalachysparish",
)
for k in keys:
    p = d["parishes"].get(k) or {}
    print(k, p.get("outcome"), p.get("last_tested_at"), (p.get("url") or "")[:100])
