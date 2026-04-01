"""Structured exception hierarchy for Pluto."""

from __future__ import annotations


class PlutoError(Exception):
    """Base exception for all Pluto-specific errors."""

    def __init__(self, message: str, error_code: str = "internal_error"):
        super().__init__(message)
        self.error_code = error_code
