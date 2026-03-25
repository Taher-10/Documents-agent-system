"""
registry/__init__.py
─────────────────────
Public API for the registry package (Phase 6).

Responsibilities:
  Phase 6a — validate_chunks(): Pydantic structural validation (warnings only).
  Phase 6b — write_registry():  JSON registry serialisation with timestamped
              filenames and a stable latest-pointer file.

These functions are internal pipeline steps called by pipeline.py.
They are not re-exported to end callers — callers interact with segment()
and receive the SegmenterResult directly.

If you need them directly (e.g. for testing):
  from registry import validate_chunks, write_registry
"""

from .registry import validate_chunks, write_registry

__all__ = [
    "validate_chunks",
    "write_registry",
]
