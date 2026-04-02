#!/usr/bin/env python3
"""
config.py - Centralized configuration loader for OpenClaw Multi-Agent Dashboard.

This module provides a single source of truth for all environment variables
and configuration settings used throughout the application.

F0.7 — Variables de entorno y configuración

Usage:
    from config import config
    
    # Access configuration values
    api_key = config.DASHBOARD_API_KEY
    cors_origins = config.DASHBOARD_ALLOWED_ORIGINS
    
    # Validate configuration at startup
    config.validate()
"""

import os
import sys
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Load environment variables from .env file (F0.7)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env only

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean from environment variable."""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def _parse_int(value: str | None, default: int) -> int:
    """Parse an integer from environment variable."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float(value: str | None, default: float) -> float:
    """Parse a float from environment variable."""
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_list(value: str | None, default: list[str] | None = None) -> list[str]:
    """Parse a comma-separated list from environment variable."""
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_path(value: str | None, default: Path | None = None) -> Path | None:
    """Parse a path from environment variable."""
    if value is None:
        return default
    return Path(value)


@dataclass
class Config:
    """
    Centralized configuration for OpenClaw Multi-Agent Dashboard.
    
    All configuration values are loaded from environment variables at startup.
    Use config.validate() to ensure all required values are set.
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # Dashboard API Configuration
    # ═══════════════════════════════════════════════════════════════════════
    
    # API key for dashboard authentication (empty = disabled)
    DASHBOARD_API_KEY: str = field(default_factory=lambda: os.getenv("DASHBOARD_API_KEY", ""))
    
    # CORS allowed origins (comma-separated)
    DASHBOARD_ALLOWED_ORIGINS: list[str] = field(
        default_factory=lambda: _parse_list(
            os.getenv("DASHBOARD_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
        )
    )
    
    # Session configuration (F0.1)
    DASHBOARD_SESSION_SECRET: str = field(
        default_factory=lambda: os.getenv("DASHBOARD_SESSION_SECRET", "")
    )
    DASHBOARD_SESSION_MAX_AGE: int = field(
        default_factory=lambda: _parse_int(os.getenv("DASHBOARD_SESSION_MAX_AGE"), 86400)
    )
    
    # Server configuration
    DASHBOARD_HOST: str = field(default_factory=lambda: os.getenv("DASHBOARD_HOST", "0.0.0.0"))
    DASHBOARD_PORT: int = field(default_factory=lambda: _parse_int(os.getenv("DASHBOARD_PORT"), 8001))
    DASHBOARD_WORKERS: int = field(default_factory=lambda: _parse_int(os.getenv("DASHBOARD_WORKERS"), 1))
    
    # ═══════════════════════════════════════════════════════════════════════
    # Model Fallback Configuration (F0.3)
    # ═══════════════════════════════════════════════════════════════════════
    
    MODEL_STATUS_CACHE_PATH: Path | None = field(
        default_factory=lambda: _parse_path(
            os.getenv("MODEL_STATUS_CACHE_PATH", "/var/cache/openclaw/model_status.json")
        )
    )
    MODEL_STATUS_CACHE_TTL: int = field(
        default_factory=lambda: _parse_int(os.getenv("MODEL_STATUS_CACHE_TTL"), 300)
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # Gateway Configuration
    # ═══════════════════════════════════════════════════════════════════════
    
    OPENCLAW_GATEWAY_TOKEN: str = field(default_factory=lambda: os.getenv("OPENCLAW_GATEWAY_TOKEN", ""))
    OPENCLAW_GATEWAY_HOST: str = field(default_factory=lambda: os.getenv("OPENCLAW_GATEWAY_HOST", "127.0.0.1"))
    OPENCLAW_GATEWAY_PORT: int = field(default_factory=lambda: _parse_int(os.getenv("OPENCLAW_GATEWAY_PORT"), 18789))
    
    # ═══════════════════════════════════════════════════════════════════════
    # Runtime Profile Configuration
    # ═══════════════════════════════════════════════════════════════════════
    
    OPENCLAW_RUNTIME_HOME: Path = field(
        default_factory=lambda: _parse_path(
            os.getenv("OPENCLAW_RUNTIME_HOME", str(Path.home() / ".openclaw-runtime"))
        ) or Path.home() / ".openclaw-runtime"
    )
    OPENCLAW_PROFILE: str = field(default_factory=lambda: os.getenv("OPENCLAW_PROFILE", "multi-agents-runtime-v2"))
    OPENCLAW_RUNTIME_DIR: Path = field(
        default_factory=lambda: _parse_path(
            os.getenv("OPENCLAW_RUNTIME_DIR", "/root/.openclaw/multi-agents")
        ) or Path("/root/.openclaw/multi-agents")
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # Telegram Notifications
    # ═══════════════════════════════════════════════════════════════════════
    
    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    TELEGRAM_CHAT_ID: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    
    # ═══════════════════════════════════════════════════════════════════════
    # Git Identity
    # ═══════════════════════════════════════════════════════════════════════
    
    GIT_AUTHOR_NAME: str = field(default_factory=lambda: os.getenv("GIT_AUTHOR_NAME", "OpenClaw"))
    GIT_AUTHOR_EMAIL: str = field(default_factory=lambda: os.getenv("GIT_AUTHOR_EMAIL", "openclaw@example.com"))
    GIT_COMMITTER_NAME: str = field(default_factory=lambda: os.getenv("GIT_COMMITTER_NAME", "OpenClaw"))
    GIT_COMMITTER_EMAIL: str = field(default_factory=lambda: os.getenv("GIT_COMMITTER_EMAIL", "openclaw@example.com"))
    
    # ═══════════════════════════════════════════════════════════════════════
    # Miniverse / Preview Integrations
    # ═══════════════════════════════════════════════════════════════════════
    
    MINIVERSE_ENABLED: bool = field(default_factory=lambda: _parse_bool(os.getenv("MINIVERSE_ENABLED"), False))
    MINIVERSE_URL: str = field(default_factory=lambda: os.getenv("MINIVERSE_URL", "http://127.0.0.1:9999"))
    MINIVERSE_UI_URL: str = field(default_factory=lambda: os.getenv("MINIVERSE_UI_URL", "http://127.0.0.1:9999"))
    MINIVERSE_REQUEST_TIMEOUT_SEC: float = field(
        default_factory=lambda: _parse_float(os.getenv("MINIVERSE_REQUEST_TIMEOUT_SEC"), 6.0)
    )
    MINIVERSE_CACHE_TTL_SEC: float = field(
        default_factory=lambda: _parse_float(os.getenv("MINIVERSE_CACHE_TTL_SEC"), 300.0)
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # Provider API Keys (optional)
    # ═══════════════════════════════════════════════════════════════════════
    
    FIREWORKS_API_KEY: str = field(default_factory=lambda: os.getenv("FIREWORKS_API_KEY", ""))
    GROQ_API_KEY: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    NVIDIA_API_KEY: str = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY", ""))
    BLINK_API_KEY: str = field(default_factory=lambda: os.getenv("BLINK_API_KEY", ""))
    OPENCLAW_GITHUB_TOKEN: str = field(default_factory=lambda: os.getenv("OPENCLAW_GITHUB_TOKEN", ""))
    GITHUB_TOKEN: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    
    # ═══════════════════════════════════════════════════════════════════════
    # Test Configuration
    # ═══════════════════════════════════════════════════════════════════════
    
    TEST_API_URL: str = field(default_factory=lambda: os.getenv("TEST_API_URL", "http://127.0.0.1:8001"))
    
    def validate(self) -> list[str]:
        """
        Validate configuration and return list of issues.
        
        Returns:
            List of configuration issues (empty if all valid)
        """
        issues: list[str] = []
        
        # Validate required paths exist or can be created
        if self.MODEL_STATUS_CACHE_PATH:
            cache_dir = self.MODEL_STATUS_CACHE_PATH.parent
            if not cache_dir.exists():
                log.info(f"Cache directory will be created: {cache_dir}")
        
        # Validate numeric ranges
        if self.DASHBOARD_SESSION_MAX_AGE < 60:
            issues.append(f"DASHBOARD_SESSION_MAX_AGE ({self.DASHBOARD_SESSION_MAX_AGE}) should be at least 60 seconds")
        
        if self.MODEL_STATUS_CACHE_TTL < 60:
            issues.append(f"MODEL_STATUS_CACHE_TTL ({self.MODEL_STATUS_CACHE_TTL}) should be at least 60 seconds")
        
        # Validate CORS origins
        if "*" in self.DASHBOARD_ALLOWED_ORIGINS and self.DASHBOARD_API_KEY:
            issues.append("Using wildcard CORS origin with authentication is insecure")
        
        return issues
    
    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of current configuration (safe for logging).
        
        Returns:
            Dictionary with non-sensitive configuration values
        """
        return {
            "dashboard": {
                "host": self.DASHBOARD_HOST,
                "port": self.DASHBOARD_PORT,
                "workers": self.DASHBOARD_WORKERS,
                "auth_enabled": bool(self.DASHBOARD_API_KEY),
                "cors_origins": self.DASHBOARD_ALLOWED_ORIGINS,
                "session_max_age": self.DASHBOARD_SESSION_MAX_AGE,
            },
            "gateway": {
                "host": self.OPENCLAW_GATEWAY_HOST,
                "port": self.OPENCLAW_GATEWAY_PORT,
                "token_configured": bool(self.OPENCLAW_GATEWAY_TOKEN),
            },
            "runtime": {
                "home": str(self.OPENCLAW_RUNTIME_HOME),
                "profile": self.OPENCLAW_PROFILE,
                "runtime_dir": str(self.OPENCLAW_RUNTIME_DIR),
            },
            "notifications": {
                "telegram_configured": bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID),
            },
            "miniverse": {
                "enabled": self.MINIVERSE_ENABLED,
                "url": self.MINIVERSE_URL,
            },
            "cache": {
                "model_status_path": str(self.MODEL_STATUS_CACHE_PATH) if self.MODEL_STATUS_CACHE_PATH else None,
                "model_status_ttl": self.MODEL_STATUS_CACHE_TTL,
            },
        }
    
    def print_summary(self) -> None:
        """Print configuration summary to log."""
        summary = self.get_summary()
        log.info("=" * 60)
        log.info("Configuration Summary")
        log.info("=" * 60)
        for section, values in summary.items():
            log.info(f"\n[{section.upper()}]")
            for key, value in values.items():
                log.info(f"  {key}: {value}")
        log.info("=" * 60)


# Global configuration instance
config = Config()


def load_config() -> Config:
    """
    Load and validate configuration.
    
    This should be called at application startup.
    
    Returns:
        Config instance with validated configuration
    """
    global config
    config = Config()
    
    # Validate configuration
    issues = config.validate()
    if issues:
        for issue in issues:
            log.warning(f"Configuration issue: {issue}")
    
    config.print_summary()
    
    return config


# Export config for easy import
__all__ = ["config", "load_config", "Config"]
