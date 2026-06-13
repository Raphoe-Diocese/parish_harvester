# AI Conversation Log — 2026-06-13: Simple Local Dev Setup (raphoe)

**Date:** 2026-06-13  
**Login:** @Frankytyrone  
**Repo:** raphoe/parish_harvester (local copy)

---

## Plain-English Summary

Franky asked for a **simple local development setup** for the raphoe repo only. Goal: run the project locally and see changes. Beginner-friendly, no complex tools, no project structure changes.

## What This Project Has (Two Parts)

1. **Python harvester** — downloads parish bulletins (`main.py`)
2. **Chrome/Brave extension** — floating toolbar on parish websites (`extension/` folder)

## One-Time Setup (Windows PowerShell)

```powershell
cd "C:\Users\Digital Admin\Desktop\harvester compare repos\parish_harvester-main raphoe\parish_harvester-main"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py -m playwright install chromium
```

Note: On Franky's PC, use **`py`** (Python 3.11) — the `python` command may not be on PATH.

## Commands to Run Daily

**Check Python works:**
```powershell
py main.py --help
```

**Safe test harvest (downloads, no mega PDF):**
```powershell
py main.py --dry-run --diocese derry_diocese
```

**Quick code check (no internet):**
```powershell
py -m unittest tests.test_extension_messaging -v
```

**Extension (see UI changes):**
1. Brave → `brave://extensions` → Developer mode ON
2. Load unpacked → select `extension/` folder
3. After editing extension files → click ↻ reload on extension card
4. Refresh the parish webpage

## Minimal Fix Applied

- `tests/test_extension_messaging.py` — fixed `REPO_ROOT` path (was pointing at `tests/` instead of repo root after tests were moved)

## Hand-off to Next AI

- `.venv` was created locally during setup — it is gitignored, Franky must run setup once per machine
- API keys are optional for `--help` and extension tests; needed for Smart Extract / full harvest AI features
- Do not point Franky at `requirements-dev.txt` unless he asks for linting/formatting tools

---

Contact: @Frankytyrone  
Last updated: 2026-06-13
