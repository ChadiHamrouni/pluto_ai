"""Structured exception hierarchy for Jarvis."""

from __future__ import annotations


class JarvisError(Exception):
    """Base exception for all Jarvis-specific errors."""

    def __init__(self, message: str, error_code: str = "internal_error"):
        super().__init__(message)
        self.error_code = error_code
