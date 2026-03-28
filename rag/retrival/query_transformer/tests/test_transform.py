"""
tests/test_transform.py
────────────────────────
Unit tests for QueryTransformer.transform().

Verifies:
1. transform() is synchronous (not a coroutine)
2. hyde_used is always False
3. embed_text equals the input query (Stage 1 — no prefix yet)
4. bm25_tokens are non-empty for ISO-vocabulary queries
5. qdrant_filter is constructed (non-None)
6. iso_vocab_hits contains expected canonical terms

Run:
    pytest rag/retrival/query_transformer/tests/test_transform.py -v
"""
import inspect
import unittest

from rag.retrival.query_transformer.Querytransformer import transform


class TestTransformIsSync(unittest.TestCase):
    """transform() must be a plain synchronous function, not a coroutine."""

    def test_transform_is_not_coroutine(self):
        self.assertFalse(
            inspect.iscoroutinefunction(transform),
            "transform() must be sync — remove async def",
        )

    def test_transform_returns_transformed_query_not_coroutine(self):
        result = transform("audit interne", norm_filter=["ISO9001"], language="FR")
        # If still async, result would be a coroutine object, not TransformedQuery
        self.assertFalse(
            inspect.iscoroutine(result),
            "transform() returned a coroutine — it must be sync",
        )
        if inspect.iscoroutine(result):
            result.close()  # prevent ResourceWarning


class TestTransformHydeAlwaysFalse(unittest.TestCase):
    """hyde_used must always be False regardless of query content."""

    def test_short_query_hyde_false(self):
        tq = transform("NC", norm_filter=["ISO9001"], language="FR")
        self.assertFalse(tq.hyde_used)

    def test_long_operational_query_hyde_false(self):
        query = (
            "L'organisation analyse régulièrement les facteurs internes "
            "et externes susceptibles d'influencer ses performances"
        )
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertFalse(tq.hyde_used)

    def test_english_query_hyde_false(self):
        tq = transform("document control and records management", norm_filter=["ISO9001"], language="EN")
        self.assertFalse(tq.hyde_used)


class TestTransformEmbedText(unittest.TestCase):
    """embed_text must equal the input query (Stage 1 — no prefix yet)."""

    def test_embed_text_equals_input(self):
        query = "audit interne planifié"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertEqual(tq.embed_text, query)

    def test_original_query_preserved(self):
        query = "revue de direction"
        tq = transform(query, norm_filter=["ISO9001"], language="FR")
        self.assertEqual(tq.original_query, query)


class TestTransformBm25Tokens(unittest.TestCase):
    """bm25_tokens must be non-empty for vocabulary-bearing queries."""

    def test_iso_vocab_query_produces_tokens(self):
        tq = transform("audit interne planifié", norm_filter=["ISO9001"], language="FR")
        self.assertGreater(len(tq.bm25_tokens), 0)

    def test_english_iso_vocab_produces_tokens(self):
        tq = transform("internal audit planning and programme", norm_filter=["ISO9001"], language="EN")
        self.assertGreater(len(tq.bm25_tokens), 0)


class TestTransformVocabHits(unittest.TestCase):
    """iso_vocab_hits must contain expected canonical terms."""

    def test_nc_standalone_fr_hits_nonconformite(self):
        tq = transform("un NC a été détecté lors de l'audit", norm_filter=["ISO9001"], language="FR")
        self.assertIn("non-conformité", tq.iso_vocab_hits)

    def test_nc_in_influencer_fr_no_nonconformite(self):
        """NC inside 'influencer' must NOT appear in vocab hits."""
        tq = transform(
            "les facteurs susceptibles d'influencer les performances",
            norm_filter=["ISO9001"],
            language="FR",
        )
        self.assertNotIn("non-conformité", tq.iso_vocab_hits)

    def test_norm_filter_is_applied(self):
        tq = transform("système de management", norm_filter=["ISO9001"], language="FR")
        self.assertIsNotNone(tq.qdrant_filter)


class TestTransformNormFilter(unittest.TestCase):
    """Empty norm_filter must raise ValueError."""

    def test_empty_norm_filter_raises(self):
        with self.assertRaises(ValueError):
            transform("any query", norm_filter=[], language="EN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
