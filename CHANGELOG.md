# Changelog

All notable changes to the Parish Bulletin Harvester will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive logging system with colored console output (`harvester/logger.py`)
- Proper `.gitignore` with Python, IDE, and OS file exclusions
- `SECURITY.md` documenting known security issues and best practices
- `CONTRIBUTING.md` with development setup and coding guidelines
- `pytest.ini` for centralized test configuration
- `tests/conftest.py` with shared test fixtures
- `CHANGELOG.md` for tracking changes
- Complete dependency list in `requirements.txt` with version pins
- README in `parishes/recipes/unknown/` documenting cleanup policy

### Changed
- **BREAKING**: Moved all test files from root to `tests/` directory
- Replaced `print()` statements with proper logging in:
  - `harvester/ai_router.py`
  - `harvester/email_notifier.py`
  - `harvester/cost_tracker.py`
- Updated `requirements-ocr.txt` with deprecation notice
- Extension version bumped to 1.30.109

### Fixed
- Restored `release-extension.yml` workflow (was temporarily disabled)
- Cleaned up 4 duplicate recipe files in `parishes/recipes/unknown/`
- Fixed incomplete `requirements.txt` (only had playwright)

### Removed
- Duplicate recipes from `unknown/`:
  - `banagherparish.json` (exists in derry/)
  - `bellaghyparish.json` (exists in derry/)
  - `parishofballinascreen.json` (exists in derry/)
  - `saulandballeeparish.json` (exists in down_and_connor/)

### Security
- Documented extension private key exposure in `SECURITY.md`
- Added proper `.gitignore` to prevent accidental credential commits
- Added API key environment variable documentation

## [1.30.109] - 2026-05-25

### Added
- OCR search bar with real-time highlight in diocese pages
- PDF and OCR "Open in new tab" buttons
- UX improvements across all 26 diocese pages

### Changed
- Updated Gemini model from `gemini-1.5-flash` to `gemini-2.5-flash`
- Slimmed homepage by removing large top card grid

### Fixed
- OCR provider fallback chain (Mistral → Gemini → OpenAI)
- Extension manifest `update_url` and `world: MAIN` for content scripts
- Test failures in extension manifest validation

## [1.30.100] - 2026-05-24

### Fixed
- AI Help in floating toolbar now uses correct Gemini model
- Enhanced logging for AI Help diagnostics
- Added fallback message when model unavailable

## [1.30.96] - 2026-05-23

### Fixed
- Trusted Types errors in extension UI code
- AI Help tab selection (avoids extension/internal tabs)
- Improved popup diagnostics for remote troubleshooting

## [Previous Versions]

See `ai_conversations/` folder for detailed logs of earlier changes and development sessions.

---

## Version History Notes

The project uses semantic versioning for the extension (MAJOR.MINOR.PATCH):
- **MAJOR**: Breaking changes to extension API or installation
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, no new features

For harvest workflow and Python code, versioning is tracked through git commits and conversation logs.
