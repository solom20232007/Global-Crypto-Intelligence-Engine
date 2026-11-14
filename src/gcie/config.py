"""Minimal environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("GCIE_ENV", "development").strip().lower()
        log_level = os.getenv("GCIE_LOG_LEVEL", "INFO").strip().upper()
        allowed_environments = {"development", "test", "staging", "production"}
        allowed_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if environment not in allowed_environments:
            raise ValueError(f"Unsupported GCIE_ENV: {environment}")
        if log_level not in allowed_log_levels:
            raise ValueError(f"Unsupported GCIE_LOG_LEVEL: {log_level}")
        return cls(environment=environment, log_level=log_level)
