# Unknown Diocese Recipes

This folder contains training recipes for parishes whose diocese assignment is not yet determined.

## Purpose

When the Parish Trainer extension saves a recipe and the diocese is unknown or cannot be determined, the recipe is temporarily stored here. This is a **holding area only** and should be kept minimal.

## Cleanup Policy

**Important**: Recipes in this folder should be moved to their correct diocese folder as soon as the diocese is known.

Duplicate recipes (same parish key exists in both `unknown/` and a diocese folder) create maintenance problems:
- Training may update the wrong recipe
- Recipe drift between duplicates
- Unclear which recipe is current

## Moving Recipes

To move a recipe from `unknown/` to the correct diocese folder:

1. Determine the parish's diocese (check parish website, contacts, or diocese listings)
2. Move the `.json` file to the appropriate diocese folder:
   - `derry/` for Derry Diocese
   - `down_and_connor/` for Down and Connor Diocese
   - `raphoe/` for Raphoe Diocese
3. Delete the file from `unknown/`
4. Update the evidence file (`parishes/{diocese}_bulletin_urls.txt`) if needed

## Current Contents

As of last cleanup (June 2, 2026), this folder contains training recipes that need diocese assignment:

- Recipes without clear diocese affiliation
- Parishes that may span multiple dioceses
- Training sessions where diocese was not specified

**Action needed**: Review each recipe and move to the correct diocese folder.

---

For more information, see:
- [Training guide](../../../README.md#training-mode)
- [Parish evidence files](../../)
