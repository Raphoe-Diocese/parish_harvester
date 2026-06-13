"""
conftest.py — Shared test fixtures and configuration for pytest.

This file is automatically loaded by pytest and provides:
- Common fixtures available to all tests
- Test environment setup/teardown
- Shared test utilities
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest


# ============================================================================
# Session-wide fixtures
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def test_environment():
    """Set up test environment variables for the entire test session."""
    # Ensure we're in test mode
    os.environ["TESTING"] = "1"
    
    # Disable actual API calls in tests (unless explicitly enabled)
    if "ALLOW_EXTERNAL_CALLS" not in os.environ:
        os.environ["NO_EXTERNAL_CALLS"] = "1"
    
    yield
    
    # Cleanup
    os.environ.pop("TESTING", None)
    os.environ.pop("NO_EXTERNAL_CALLS", None)


# ============================================================================
# Directory fixtures
# ============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that's cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root directory."""
    # conftest.py is in tests/, so parent is root
    return Path(__file__).parent.parent


@pytest.fixture
def test_data_dir(repo_root: Path) -> Path:
    """Return the test data directory (if it exists)."""
    test_data = repo_root / "tests" / "test_data"
    if not test_data.exists():
        test_data.mkdir(parents=True)
    return test_data


# ============================================================================
# Mock fixtures for external dependencies
# ============================================================================

@pytest.fixture
def mock_api_keys(monkeypatch):
    """Mock API keys for testing without real credentials."""
    monkeypatch.setenv("MISTRAL_API_KEY", "test-mistral-key-12345")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-12345")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345")


@pytest.fixture
def mock_smtp_config(monkeypatch):
    """Mock SMTP configuration for email testing."""
    monkeypatch.setenv("HARVEST_EMAIL_TO", "test@example.com")
    monkeypatch.setenv("HARVEST_EMAIL_FROM", "harvester@example.com")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-password")


# ============================================================================
# Helper functions
# ============================================================================

def create_test_pdf(path: Path, content: bytes = b"%PDF-1.4\n%test\nendobj\n%%EOF") -> None:
    """Create a minimal test PDF file."""
    path.write_bytes(content)


def create_test_bulletin_entry(
    key: str,
    display_name: str,
    pattern: str = "A",
    url: str = "https://example.com/bulletin.pdf"
) -> dict:
    """Create a test parish entry dictionary."""
    return {
        "key": key,
        "display_name": display_name,
        "pattern": pattern,
        "content_type": "pdf",
        "example_url": url,
        "bulletin_page": "",
        "all_urls": [url]
    }


# Make helper functions available to all tests
pytest.create_test_pdf = create_test_pdf
pytest.create_test_bulletin_entry = create_test_bulletin_entry


# ============================================================================
# Pytest hooks
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Add custom markers
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests requiring external resources"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection - add markers automatically based on test location."""
    for item in items:
        # Auto-mark slow tests
        if "slow" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)
        
        # Auto-mark integration tests
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)
