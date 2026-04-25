"""Normalization helpers for incoming norm identifiers."""

from __future__ import annotations


def normalize_norm_id(norm: str) -> str:
    """Normalize user-facing norm labels to SQLite key format.

    Examples:
    - "ISO 9001" -> "ISO9001"
    - "ISO 14001:2015" -> "ISO14001"
    """
    normalized = norm.upper().replace(" ", "").replace("-", "")
    if ":" in normalized:
        normalized = normalized.split(":", 1)[0]
    return normalized
