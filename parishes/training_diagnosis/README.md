# Training diagnosis (extension → repo)

When you **push a recipe** or tap **Save diagnosis** in the Parish Trainer popup, the extension writes a JSON file here:

`parishes/training_diagnosis/{parish_key}.json`

## What is already captured (no questionnaire required)

| Source | Location | Contents |
|--------|----------|----------|
| **Recipe** | `parishes/recipes/{diocese}/{key}.json` | Recorded steps, `site_type`, `playbook_type`, `operator_notes`, `do_not` |
| **HTML fingerprint** | diagnosis `html_fingerprint` | Page type, capture method (PDF / image / HTML), best download URL |
| **Site patterns** | `parishes/site_patterns.json` | Learned layout archetypes from successful pushes |
| **Host profiles** | `parishes/host_profiles.json` | Timeouts, `navigation_wait_until`, slow-host notes |
| **Harvest failures** | `Bulletins/report.json` | Last error + diagnosis block per parish |
| **Backlog** | `parishes/training_backlog.json` | Generated merge of recipe + report + suggested action |

The extension infers **bulletin format** (`pdf_download`, `word`, `html`, `image_stack`, etc.) from the HTML fingerprint and records it in `site_intake` inside each diagnosis file.

## Optional operator questionnaire

A formal questionnaire is only needed when the fingerprint is ambiguous (e.g. Wix with both images and a PDF viewer). The diagnosis payload includes:

```json
"site_intake": {
  "bulletin_format": "pdf_download",
  "suggested_terminal_step": "download",
  "operator_confirm": {
    "bulletin_format": null,
    "notes": ""
  }
}
```

Set `operator_confirm.bulletin_format` in the saved JSON if auto-detection was wrong.

## Two-way communication (extension ↔ repo)

| Direction | How |
|-----------|-----|
| **Extension → GitHub** | Push recipe, save diagnosis, learn host profile & site pattern (needs GitHub PAT in extension settings) |
| **Repo → Extension** | On push, extension reads recipe + `consecutive_failures.json` + report context from GitHub |
| **Repo → Harvester** | Recipes, host profiles, patterns used on every GitHub Actions harvest |
| **Live to Cursor / AI** | **No** — nothing streams live. The AI only sees what is committed/pushed or what you paste in chat |

The extension runs **only in Chrome on machines where you load it** (your laptop). I cannot see your screen or training session unless you push diagnosis to GitHub and pull, or share the file.

## How to populate this folder

1. Open parish site in Chrome with Parish Trainer loaded.
2. Run training or open popup → **Save diagnosis to GitHub**.
3. Pull `main` — file appears here.
4. Or push a recipe (diagnosis snapshot is saved automatically on push).

## Related scripts

```bash
py -3 scripts/diagnose_recipe_health.py
py -3 scripts/autofix_recipes.py
py -3 scripts/build_training_backlog.py
```
