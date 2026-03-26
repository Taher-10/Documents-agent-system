"""
embedder/config.py
───────────────────
Environment-controlled configuration for Phase 7 (embedding).

All values are read once at module import time.
Dependency rule: standard library only — no pipeline package imports.
"""
import os

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_EMBED_ENDPOINT: str = f"{OLLAMA_BASE_URL}/api/embeddings"
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

EMBED_BATCH_SIZE: int = int(os.getenv("EMBED_BATCH_SIZE", "50"))

# Maximum number of concurrent Ollama requests per batch (semaphore limit).
# Reduce if Ollama is running on a resource-constrained machine.
MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))

# Retry configuration for individual Ollama requests.
EMBED_MAX_RETRIES: int = int(os.getenv("EMBED_MAX_RETRIES", "5"))
EMBED_RETRY_BASE_DELAY: float = float(os.getenv("EMBED_RETRY_BASE_DELAY", "0.5"))
EMBED_RETRY_MAX_DELAY: float = float(os.getenv("EMBED_RETRY_MAX_DELAY", "30.0"))
EMBED_RETRY_JITTER: float = float(os.getenv("EMBED_RETRY_JITTER", "0.5"))

# Failure-rate thresholds.  failure_rate = failed_chunks / total_eligible.
# > WARNING_THRESHOLD  → UserWarning emitted by pipeline.py
# > CRITICAL_THRESHOLD → RuntimeError raised by pipeline.py (aborts upsert)
EMBED_WARNING_THRESHOLD: float = float(os.getenv("EMBED_WARNING_THRESHOLD", "0.10"))
EMBED_CRITICAL_THRESHOLD: float = float(os.getenv("EMBED_CRITICAL_THRESHOLD", "0.30"))

# Hash modulus for BM25 sparse index mapping.
# Tokens are mapped to integer indices via hashlib.md5(token) % SPARSE_DIM.
# Changing this value invalidates all stored sparse indices — the sentinel
# guard in VectorStoreManager will raise RuntimeError on mismatch.
from rag.shared.bm25.config import SPARSE_DIM  # re-exported from shared

# All four ContentType values are embedded — STRUCTURAL enables navigation-level
# RAG queries (scope statements, section headers).
# Stored as strings to avoid importing segmenter/chunker from config.
EMBED_CONTENT_TYPES: frozenset = frozenset({
    "requirement",
    "recommendation",
    "informative",
    "structural",
})
