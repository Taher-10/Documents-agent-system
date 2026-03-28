"""
shared/vocabulary/__init__.py
──────────────────────────────
Public API for the shared ISO vocabulary package.

Exports
-------
    ISO_VOCABULARY_EN  — English canonical term dictionary
    ISO_VOCABULARY_FR  — French canonical term dictionary
    build_lookup       — Build a flat surface-form → canonical-key lookup
    scan_iso_vocabulary — Scan text for ISO vocabulary hits (canonical keys)
"""

from .vocabulary import ISO_VOCABULARY_EN, ISO_VOCABULARY_FR, build_lookup
from .scanner import scan_iso_vocabulary

__all__ = [
    "ISO_VOCABULARY_EN",
    "ISO_VOCABULARY_FR",
    "build_lookup",
    "scan_iso_vocabulary",
]
