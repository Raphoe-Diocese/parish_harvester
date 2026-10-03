# Recipe Brain / Referee

Frank unlocked this on 23/09/2026. The written list is in `GAMEPLAN.md` (23/09 lock). This file is the living checklist. Do not say the brain is finished until harvest proof exists.

## What we agreed it must do

1. **Stale harder** — refuse a file whose best date is older than harvest-week Sunday. Do not promote a yearless archive into this week. *Shipped and live-proved 29/09 (Aughavas).*
2. **Click memory** — when a hunt or Send & test wins, write the trick into `parishes/site_patterns.json` and `extension/site_memory.js` the same day. One win must open many more.
3. **Fingerprint** — host + listing shape + filename pattern, so the next similar page is not a blank Guess.
4. **Picker challenge** — if the listing has a newer dated PDF than the recipe pin, re-pick. Do not quietly stitch the stale pin. *Code exists as `_challenge_pin_against_listing` in `harvester/replay.py`. Not proved as a parish hunt pass.*
5. **Guess date** — no invented future dates. Proved patterns only.

## Hubs to try every hunt (remember these)

| Hub | What it is | Recipe | Do not |
|---|---|---|---|
| `mcn.live` /camera/ | Webcam page. Newsletter is JSON next to the camera (Frank trained this). | `mcn_live_parish_page` | Do not treat the webcam as the bulletin. Do not pin a dated PDF. |
| `churchmedia.tv` | “View Our Latest Newsletter” on the livestream page. | `churchmedia_newsletter` | Do not pin `/newsletter/<token>.….pdf`. The token dies. |
| `mayo.ie` parish-newsletters | Mayo County Council hosts PDFs (Belmullet proved). | `http_scrape_newest_pdf` on the listing | Do not pin the `getmedia` GUID. PNG is not a PDF recipe. |
| `churchservices.tv` | Webcam. Sometimes a pointer to a real parish site. | Look for a newsletter on the same page; else keep the real site | Do not harvest the stream. Do not invent a PDF. |
| `/current-newsletter/` | Same path every week, redirects to this Sunday’s PDF (Naas / Kildare). | `permanent_redirect_document` | Do not pin the dated upload name. |

Kitchen-sink search (Google / Bing / Yahoo) stays in [`DIOCESE_HUNT.md`](DIOCESE_HUNT.md). That runs in cloud hunts, not on this 16GB laptop.

## 24/7

Sunday harvest on GitHub Actions is the repeating job (`harvest.yml` 09:00 UTC). This PC must not run a full harvest or mega PDF.

A night-and-day skip-parish hub scan on Actions is **Next**, not this turn. Do not start it on the laptop.

## Code

- Hints from a URL: `harvester/recipe_brain.py` `hint_for_url`
- Trainer catalog: `extension/site_memory.js`
- Learned patterns: `parishes/site_patterns.json`
- Hunt command: `docs/DIOCESE_HUNT.md`
