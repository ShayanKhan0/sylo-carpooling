"""
Purpose: Centralized logging configuration with structured JSON logs for production
         and pretty-printed logs for local development.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Uses Python's logging module with JSON formatting for easier log aggregation
       in production environments (ELK, CloudWatch, etc.)
       Includes async log rotation and comprehensive error tracking.
"""

import logging
import sys
import os
from typing import Any, Dict
import json
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    Outputs logs in JSON format for easy parsing by log aggregation tools.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON string.

        Args:
            record: LogRecord instance containing log information

        Returns:
            JSON formatted log string
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class PrettyFormatter(logging.Formatter):
    """
    Pretty formatter for local development with colors and readable format.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors for terminal output.

        Args:
            record: LogRecord instance

        Returns:
            Colored formatted log string
        """
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]

        log_format = (
            f"{color}[{record.levelname}]{reset} "
            f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} "
            f"- {record.name} - {record.getMessage()}"
        )

        if record.exc_info:
            log_format += f"\n{self.formatException(record.exc_info)}"

        return log_format


def setup_logging() -> None:
    """
    Configure application-wide logging based on environment settings.
    Sets up handlers, formatters, and log levels with async log rotation.

    Returns:
        None
    """
    # Determine log level from settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Choose formatter based on environment
    if settings.LOG_FORMAT == "json" or settings.APP_ENV == "production":
        formatter = JSONFormatter()
    else:
        formatter = PrettyFormatter()

    # 1. Console handler for stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. File handler with rotation (for production/staging)
    if settings.APP_ENV in ["production", "staging"]:
        try:
            # Create logs directory if it doesn't exist
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)

            # Timed rotating file handler - rotates daily, keeps 30 days
            file_handler = TimedRotatingFileHandler(
                filename=log_dir / "app.log",
                when="midnight",  # Rotate at midnight
                interval=1,  # Every 1 day
                backupCount=30,  # Keep 30 days of logs
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

            # Separate error log file - only errors and above
            error_handler = TimedRotatingFileHandler(
                filename=log_dir / "error.log",
                when="midnight",
                interval=1,
                backupCount=90,  # Keep errors for 90 days
                encoding="utf-8",
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            root_logger.addHandler(error_handler)

        except Exception as e:
            # If file logging fails, log to console
            console_handler.setLevel(logging.WARNING)
            root_logger.warning(f"Failed to setup file logging: {e}")

    # Set log levels for third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logging.info(
        f"✅ Logging configured: level={settings.LOG_LEVEL}, "
        f"format={settings.LOG_FORMAT}, env={settings.APP_ENV}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Name of the logger (usually __name__ of the module)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
