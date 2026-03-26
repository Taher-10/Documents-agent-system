"""
query_retrival/tests/test_sparse_encoder_query.py
──────────────────────────────────────────────────
Unit tests for BM25SparseEncoder.encode_query().

The critical invariant: encode_query must produce the same token→index mapping
as _token_to_index (same MD5, same SPARSE_DIM modulus).  If this breaks,
sparse search returns wrong results with no error message.

Run from the retrival/ directory:
    python query_retrival/tests/test_sparse_encoder_query.py

No external dependencies — standard library only.
"""
import importlib.util
import os
import sys
import types
import unittest

# ── Module bootstrap ───────────────────────────────────────────────────────────
# embedder/__init__.py re-exports EmbedderService, which cascades through the
# full ingestion pipeline (chunker → segmenter → parser → fitz).  We only need
# bm25_encoder.py and config.py, so we load them directly with importlib and
# register lightweight stubs for their transitive dependencies.

_HERE = os.path.dirname(os.path.abspath(__file__))
# tests/ → query_retrival/ → retrival/ → rag/ → ingestion_pipeline/embedder/
_EMBEDDER_DIR = os.path.normpath(
    os.path.join(_HERE, "..", "..", "..", "ingestion_pipeline", "embedder")
)


def _load_as(module_name: str, file_path: str):
    """Load a .py file under an explicit module name, bypassing __init__.py."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register a bare embedder package so the relative import `from .config import
# SPARSE_DIM` inside bm25_encoder.py resolves against embedder.config
# (loaded explicitly below) without running embedder/__init__.py.
if "embedder" not in sys.modules:
    sys.modules["embedder"] = types.ModuleType("embedder")

# Load config.py and bm25_encoder.py directly.
_load_as("embedder.config", os.path.join(_EMBEDDER_DIR, "config.py"))
_bm25_mod = _load_as(
    "embedder.bm25_encoder", os.path.join(_EMBEDDER_DIR, "bm25_encoder.py")
)

BM25SparseEncoder = _bm25_mod.BM25SparseEncoder
from embedder.config import SPARSE_DIM  # noqa: E402  (module registered above)


# ── Test classes ───────────────────────────────────────────────────────────────

class TestEncodeQueryHashAlignment(unittest.TestCase):
    """
    The critical correctness invariant: encode_query must produce the same
    index as _token_to_index for every token.  If this breaks, sparse search
    returns wrong results with no error message.
    """

    def test_single_token_index_matches_token_to_index(self):
        """Index from encode_query([token]) equals _token_to_index(token)."""
        token = "documented"
        expected_idx = BM25SparseEncoder._token_to_index(token)
        indices, values = BM25SparseEncoder.encode_query([token])
        self.assertEqual(len(indices), 1)
        self.assertEqual(indices[0], expected_idx)

    def test_multiple_tokens_each_index_matches(self):
        """Every index in the output matches the corresponding _token_to_index call."""
        tokens = ["management", "review", "shall", "documented", "information"]
        indices, values = BM25SparseEncoder.encode_query(tokens)
        expected = {BM25SparseEncoder._token_to_index(t) for t in tokens}
        # After dedup/collision, the set of output indices must be a subset
        # of the expected set (collisions reduce unique count).
        self.assertTrue(set(indices).issubset(expected))
        # And the total weight always equals the number of input tokens.
        self.assertAlmostEqual(sum(values), float(len(tokens)))

    def test_index_within_sparse_dim(self):
        """All indices must be in [0, SPARSE_DIM)."""
        tokens = ["organisation", "processus", "exigence", "conformite"]
        indices, _ = BM25SparseEncoder.encode_query(tokens)
        for idx in indices:
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, SPARSE_DIM)


class TestEncodeQueryUniformWeight(unittest.TestCase):
    """encode_query assigns weight 1.0 per token (before collision summing)."""

    def test_single_token_weight_is_1(self):
        indices, values = BM25SparseEncoder.encode_query(["shall"])
        self.assertEqual(len(values), 1)
        self.assertAlmostEqual(values[0], 1.0)

    def test_total_weight_equals_token_count(self):
        """sum(values) == len(tokens) always holds regardless of collisions."""
        tokens = ["audit", "corrective", "action", "management", "system"]
        _, values = BM25SparseEncoder.encode_query(tokens)
        self.assertAlmostEqual(sum(values), float(len(tokens)))


class TestEncodeQueryCollisionSumming(unittest.TestCase):
    """
    When two tokens hash to the same index, their weights are summed → 2.0.
    We manufacture a collision by brute-force search rather than hardcoding
    magic pairs — this stays correct even if SPARSE_DIM changes via env var.
    """

    @staticmethod
    def _find_collision_pair():
        """
        Find two strings that share an MD5-derived index.
        Returns (token_a, token_b, shared_index).
        Birthday paradox: expected first collision at ~sqrt(SPARSE_DIM) ≈ 362 candidates.
        """
        seen: dict = {}
        for i in range(2_000_000):
            token = f"collision_candidate_{i}"
            idx = BM25SparseEncoder._token_to_index(token)
            if idx in seen:
                return seen[idx], token, idx
            seen[idx] = token
        raise RuntimeError("No collision found within search budget")  # pragma: no cover

    def test_collision_sums_to_2(self):
        """Two tokens hashing to the same index produce a single entry with value=2.0."""
        token_a, token_b, shared_idx = self._find_collision_pair()
        indices, values = BM25SparseEncoder.encode_query([token_a, token_b])
        self.assertEqual(len(indices), 1,
                         f"Expected 1 index after collision, got {len(indices)}")
        self.assertEqual(indices[0], shared_idx)
        self.assertAlmostEqual(values[0], 2.0)

    def test_total_weight_invariant_with_collision(self):
        """sum(values) == len(tokens) holds even when a collision occurs."""
        token_a, token_b, _ = self._find_collision_pair()
        _, values = BM25SparseEncoder.encode_query([token_a, token_b])
        self.assertAlmostEqual(sum(values), 2.0)


class TestEncodeQueryEdgeCases(unittest.TestCase):
    """Empty input and repeated tokens."""

    def test_empty_tokens_returns_empty_lists(self):
        indices, values = BM25SparseEncoder.encode_query([])
        self.assertEqual(indices, [])
        self.assertEqual(values, [])

    def test_same_token_twice_produces_single_index_value_2(self):
        """Same token repeated → one index, weight=2.0."""
        token = "documented"
        indices, values = BM25SparseEncoder.encode_query([token, token])
        self.assertEqual(len(indices), 1)
        self.assertEqual(indices[0], BM25SparseEncoder._token_to_index(token))
        self.assertAlmostEqual(values[0], 2.0)

    def test_single_token_list_lengths_equal(self):
        indices, values = BM25SparseEncoder.encode_query(["process"])
        self.assertEqual(len(indices), len(values))
        self.assertEqual(len(indices), 1)


class TestEncodeQuerySortOrder(unittest.TestCase):
    """Output indices must be in strictly ascending order."""

    def test_output_sorted_ascending(self):
        tokens = [
            "organisation", "quality", "management", "system",
            "shall", "documented", "information", "process",
            "audit", "corrective", "action", "improvement",
        ]
        indices, _ = BM25SparseEncoder.encode_query(tokens)
        self.assertEqual(indices, sorted(indices),
                         "Indices must be in ascending order")

    def test_parallel_lists_same_length(self):
        tokens = ["context", "interested", "parties", "scope"]
        indices, values = BM25SparseEncoder.encode_query(tokens)
        self.assertEqual(len(indices), len(values))


if __name__ == "__main__":
    unittest.main(verbosity=2)
