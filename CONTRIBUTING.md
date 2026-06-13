# Contributing to Parish Bulletin Harvester

Thank you for your interest in contributing! This guide will help you set up your development environment and understand the project structure.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Making Changes](#making-changes)
- [Debugging](#debugging)

---

## Development Setup

### Prerequisites

- Python 3.12 or higher
- Git
- A text editor or IDE (VS Code recommended)

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Frankytyrone/parish_harvester.git
   cd parish_harvester
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -r requirements-ocr.txt  # For OCR features
   ```

4. **Install Playwright browsers:**
   ```bash
   python -m playwright install chromium
   ```

5. **Set up environment variables:**
   
   Create a `.env` file in the root directory:
   ```bash
   # AI Provider Keys (at least one required)
   MISTRAL_API_KEY=your-mistral-key
   GEMINI_API_KEY=your-gemini-key
   OPENAI_API_KEY=your-openai-key
   
   # Email (optional, for harvest notifications)
   HARVEST_EMAIL_TO=your-email@example.com
   HARVEST_EMAIL_FROM=harvester@example.com
   EMAIL_PROVIDER=smtp
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@example.com
   SMTP_PASSWORD=your-app-password
   ```

### Verify Setup

Run the test suite to ensure everything is working:
```bash
pytest
```

---

## Project Structure

```
parish_harvester/
├── harvester/           # Core Python package
│   ├── fetcher.py      # Bulletin downloading logic
│   ├── stitcher.py     # PDF merging
│   ├── ai_router.py    # AI provider routing
│   ├── logger.py       # Logging configuration
│   └── ...
├── ocr/                # OCR processing
│   ├── convert_bulletin.py
│   └── generate_bulletin_pages.py
├── extension/          # Chrome/Brave extension
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   └── ...
├── parishes/           # Parish data
│   ├── *_bulletin_urls.txt   # Evidence files
│   ├── recipes/              # Training recipes
│   └── consecutive_failures.json
├── tests/              # Test files
│   ├── conftest.py    # Shared fixtures
│   └── test_*.py
├── docs/               # GitHub Pages site
├── .github/workflows/  # CI/CD
├── main.py            # CLI entry point
├── train.py           # Recipe training
└── requirements.txt   # Dependencies
```

### Key Modules

- **harvester/fetcher.py**: Downloads bulletins using evidence-based URLs
- **harvester/stitcher.py**: Merges PDFs into diocesan mega-bulletins
- **harvester/replay.py**: Replays training recipes with Playwright
- **harvester/logger.py**: Centralized logging (use this instead of print!)
- **extension/**: Chrome extension for training recipes

---

## Running Tests

### Run all tests:
```bash
pytest
```

### Run specific test file:
```bash
pytest tests/test_fetcher.py
```

### Run with verbose output:
```bash
pytest -v
```

### Run with coverage:
```bash
pytest --cov=harvester --cov=ocr --cov-report=html
```

### Run only fast tests (skip slow ones):
```bash
pytest -m "not slow"
```

### Test markers available:
- `@pytest.mark.slow` - Slow tests
- `@pytest.mark.integration` - Integration tests requiring external resources
- `@pytest.mark.unit` - Fast unit tests

---

## Code Style

### Python

- Follow [PEP 8](https://pep8.org/)
- Use type hints (Python 3.10+ syntax with `from __future__ import annotations`)
- Maximum line length: 100 characters
- Use f-strings for string formatting
- Use `pathlib.Path` instead of `os.path`

### Logging

**Always use the logging module, never print():**

```python
from harvester.logger import get_logger

logger = get_logger(__name__)

# Good
logger.info("Processing parish: %s", parish_name)
logger.warning("Bulletin URL returned 404")
logger.error("Failed to download: %s", exc, exc_info=True)

# Bad
print(f"Processing {parish_name}")
```

### Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Keep comments up-to-date with code changes

Example:
```python
def fetch_bulletin(url: str, timeout: int = 30) -> bytes:
    """Download a parish bulletin from the given URL.
    
    Args:
        url: Full URL to the bulletin PDF
        timeout: Request timeout in seconds
        
    Returns:
        PDF content as bytes
        
    Raises:
        URLError: If download fails
        ValueError: If URL is invalid
    """
```

---

## Making Changes

### Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write tests for new functionality
   - Update documentation
   - Use proper logging

3. **Run tests:**
   ```bash
   pytest
   ```

4. **Commit with clear messages:**
   ```bash
   git add .
   git commit -m "feat: add support for new bulletin pattern"
   ```

5. **Push and create a pull request:**
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `style:` - Code style (formatting, no logic change)
- `refactor:` - Code restructuring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

Examples:
```bash
feat: add Raphoe diocese support
fix: handle 404 responses in fetcher
docs: update AUTO_UPDATE_SETUP.md
test: add tests for pattern detection
```

---

## Debugging

### Enable Debug Logging

Set the log level in your code:
```python
from harvester.logger import setup_logging
import logging

setup_logging(level=logging.DEBUG)
```

Or via environment variable:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

### Debug Playwright Issues

Run with headed browser (visible):
```python
# In train.py or when using Playwright
await browser.new_context(
    viewport={"width": 1280, "height": 720},
    # Add this to see the browser:
    # headless=False
)
```

### Common Issues

**Issue**: `ModuleNotFoundError: No module named 'harvester'`
- **Fix**: Make sure you're in the repo root and have activated the virtual environment

**Issue**: Tests fail with "Playwright not found"
- **Fix**: Run `python -m playwright install chromium`

**Issue**: "No AI provider available"
- **Fix**: Set at least one `*_API_KEY` in your `.env` file

**Issue**: Import errors after moving test files
- **Fix**: Update imports to use relative paths or install package in editable mode:
  ```bash
  pip install -e .
  ```

---

## Need Help?

- Check existing issues: https://github.com/Frankytyrone/parish_harvester/issues
- Review conversation logs: `ai_conversations/`
- Read the deep audit: `docs/audit/2026-05-22-deep-audit.md`

---

## License

This project is private and for personal use. Do not redistribute without permission.
