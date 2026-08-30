## Summary
- Carrickfergus harvest was failing on the old `/info` click `Mass Times up to` (that link is gone).
- Recipe now starts on the Bulletin Back Issues catalogue and picks the newest dated PDF. Do not harvest the `/info` “Mass Times from 17th August onwards” 1-page schedule (that would fake a current week).
- Newest real file is still 28/06/2026. After merge, expect **stale**, not ok.

## Proof pack
- Source page: https://www.carrickparish.org/registration
- Found bulletin: https://www.carrickparish.org/_files/ugd/18d125_02051fa18f7e40b2baca445517fe43dd.pdf (label **28th June 2026**, same file as `/info` “Final Summer edition”)
- HTTP check: 200, `application/pdf`, 373141 bytes
- PDF check: `%PDF-1.7`, 2 pages, Saint Nicholas / 13th Sunday / anniversaries (not a wedding/GDPR file)
- Date check: 28/06/2026, stale vs harvest week 16/08/2026. No July/August catalogue rows. `/info` Mass Times sheet is 1 page dated 17/08/2026 (schedule only).
- Files changed: `parishes/recipes/down_and_connor/carrickparish.json`, `tests/test_http_scrape_and_predicted_pdf.py`
- Tests run: `tests/test_http_scrape_and_predicted_pdf.py`, `tests/test_replay_recipe_steps.py`, `tests/test_bulletin_freshness.py` (106 passed)

## Test plan
- [ ] CI green
- [ ] Merge, then `harvest.yml` `target_parish=carrickparish`
- [ ] Live `parish_status.json` becomes stale (28/06/2026), not failed and not a fake ok from Mass Times
