"""
logger.py — Centralized logging configuration for the Parish Bulletin Harvester.

Provides a consistent logging setup across all harvester modules with:
- Colored console output for better readability
- Structured log format with timestamps
- Separate log levels for different components
- Optional file logging

Usage:
    from harvester.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("Processing parish bulletin")
    logger.warning("Bulletin URL returned 404")
    logger.error("Failed to download bulletin", exc_info=True)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright foreground colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.BRIGHT_BLACK,
        logging.INFO: Colors.BRIGHT_BLUE,
        logging.WARNING: Colors.BRIGHT_YELLOW,
        logging.ERROR: Colors.BRIGHT_RED,
        logging.CRITICAL: Colors.BOLD + Colors.BRIGHT_RED,
    }
    
    def __init__(self, fmt: Optional[str] = None, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors
    
    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors and sys.stderr.isatty():
            # Save original values
            original_levelname = record.levelname
            
            # Colorize level name
            color = self.LEVEL_COLORS.get(record.levelno, "")
            record.levelname = f"{color}{record.levelname:8}{Colors.RESET}"
            
            # Format the message
            result = super().format(record)
            
            # Restore original values
            record.levelname = original_levelname
            
            return result
        else:
            return super().format(record)


# Global flag to track if logging has been configured
_logging_configured = False


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    use_colors: bool = True
) -> None:
    """Configure logging for the entire application.
    
    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG)
        log_file: Optional path to write logs to a file
        use_colors: Whether to use colored output (auto-disabled if not a TTY)
    """
    global _logging_configured
    
    if _logging_configured:
        return
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    
    # Format: 2026-06-02 14:30:45 INFO     [fetcher] Downloading bulletin...
    console_format = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    console_formatter = ColoredFormatter(console_format, use_colors=use_colors)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Optional file handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        
        # File format: same but without colors
        file_format = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
        file_formatter = logging.Formatter(file_format)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    
    # Silence noisy third-party loggers
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    
    _logging_configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name.
    
    Args:
        name: Module name (typically __name__)
    
    Returns:
        Logger instance configured with the application settings
    
    Example:
        logger = get_logger(__name__)
        logger.info("Processing bulletin")
    """
    # Ensure logging is configured
    if not _logging_configured:
        setup_logging()
    
    return logging.getLogger(name)
