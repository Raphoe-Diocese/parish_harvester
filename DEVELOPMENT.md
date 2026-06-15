# Development Guide

Quick reference for developers working on Parish Bulletin Harvester.

---

## Setup

### 1. Clone & Install

```bash
git clone https://github.com/Frankytyrone/parish_harvester.git
cd parish_harvester
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m playwright install chromium
```

### 2. Environment Variables

Copy `.env.example` to `.env` and add your keys:

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required for testing:
- `MISTRAL_API_KEY` - Free from https://console.mistral.ai/
- `GH_PAT` - GitHub token for extension testing

---

## Running Tests

```bash
# All tests
pytest

# Specific file
pytest tests/test_ai_summaries.py

# With coverage
pytest --cov=harvester --cov=ocr --cov-report=html

# Skip slow tests
pytest -m "not slow"

# Verbose output
pytest -v --tb=short
```

---

## Code Quality

### Formatting

```bash
# Format all Python files
black .

# Check formatting
black --check .

# Sort imports
isort .
```

### Linting

```bash
# Run flake8
flake8 harvester ocr tests

# Type checking
mypy harvester
```

### Pre-commit (recommended)

```bash
pip install pre-commit
pre-commit install
# Now runs automatically on git commit
```

---

## Project Structure

```
parish_harvester/
├── harvester/          # Core Python modules
│   ├── fetcher.py      # Main bulletin extraction
│   ├── ai_router.py    # AI provider routing
│   ├── logger.py       # Centralized logging
│   └── ...
├── extension/          # Chrome extension
│   ├── content.js      # Toolbar & UI
│   └── manifest.json
├── ocr/                # OCR processing
│   └── generate_bulletin_pages.py
├── tests/              # pytest test suite
├── docs/               # GitHub Pages site
└── .github/workflows/  # CI/CD
```

---

## Common Tasks

### Run Harvest

```bash
# Full harvest (all dioceses)
python main.py

# Single diocese
python main.py --diocese derry_diocese

# Specific date
python main.py --target-date 2026-06-08

# Single parish (debug)
python main.py --parish banagher
```

### Generate Dashboard

```bash
python -m harvester.dashboard_generator
```

### Generate OCR Pages

```bash
python ocr/generate_bulletin_pages.py derry_diocese 2026-06-02
python ocr/generate_bulletin_pages.py --rebuild-indexes
```

### Train Recipe

```bash
python train.py banagher
```

---

## Extension Development

### Load Extension

1. Open Chrome → `chrome://extensions`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select `extension/` folder

### Debug Extension

- **Console:** Right-click extension icon → Inspect
- **Content script:** F12 on any page with toolbar
- **Background:** chrome://extensions → "Inspect views: background page"

### Test Smart Extract

1. Add Mistral API key to extension settings
2. Go to any parish website
3. Click "🆓 Smart Extract (FREE)" button
4. Check console for logs

---

## Logging

**Always use logger, never print():**

```python
from harvester.logger import get_logger

logger = get_logger(__name__)

logger.debug("Detailed debug info")
logger.info("Normal progress messages")
logger.warning("Something unexpected")
logger.error("Error occurred", exc_info=True)
```

**Progress (only ~13% converted, help needed!):**
- ✅ logger.py, ai_router.py, email_notifier.py, cost_tracker.py
- ✅ ai_summaries.py, dashboard_generator.py
- ❌ ~20 other files still use print()

---

## Adding Tests

Create test file in `tests/`:

```python
import pytest

def test_my_feature():
    # Arrange
    input_data = "test"
    
    # Act
    result = my_function(input_data)
    
    # Assert
    assert result == "expected"

@pytest.mark.slow
def test_external_api():
    # Mark slow tests
    pass
```

Run with: `pytest tests/test_my_feature.py`

---

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes, commit
git add .
git commit -m "feat: add new feature"

# Push and create PR
git push origin feature/my-feature
```

**Commit message format:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Add/update tests
- `refactor:` Code restructure

---

## Troubleshooting

### Playwright Issues

```bash
# Reinstall browser
python -m playwright install --force chromium

# Check browser paths
python -m playwright install --dry-run
```

### Import Errors

```bash
# Verify environment
python -c "import harvester; print(harvester.__file__)"

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Test Failures

```bash
# Clear cache
pytest --cache-clear

# Run single test with full output
pytest tests/test_name.py::test_function -vv --tb=long
```

---

## VSCode Setup

Workspace settings in `.vscode/settings.json` provide:
- Python interpreter detection
- pytest integration
- black formatting on save
- flake8 linting

**Recommended extensions:**
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Black Formatter (ms-python.black-formatter)

---

## Performance Tips

1. **Use `--dry-run`** for testing without generating PDFs
2. **Single parish runs** for debugging: `--parish <key>`
3. **Skip AI summaries:** `PARISH_AI_SUMMARIES_DISABLE=1`
4. **Disable priority:** `PARISH_HARVEST_NO_PRIORITY=1` for alphabetical

---

## Resources

- **Audit:** [docs/audit/2026-05-22-deep-audit.md](docs/audit/2026-05-22-deep-audit.md)
- **AI Agent:** [FREE_SOLUTION.md](FREE_SOLUTION.md)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)

---

## Getting Help

- **Issues:** Open GitHub issue with reproduction steps
- **AI Conversations:** Check `ai_conversations/` for past solutions
- **Tests:** Look at existing tests for examples

**Remember:** Always read ai_conversations/ history first! Solutions are documented.
