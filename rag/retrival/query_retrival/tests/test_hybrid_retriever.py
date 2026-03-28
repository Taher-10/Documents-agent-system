"""
query_retrival/tests/test_hybrid_retriever.py
──────────────────────────────────────────────
Unit tests for HybridRetriever — Step 5: norm filter and empty corpus guard.

Two behavioral scenarios:
  1. Correct norm_filter → results returned with expected fields
  2. Wrong norm_filter value ("WRONG_ID") → EmptyCorpusError raised,
     message contains the filter value

Framework: unittest.IsolatedAsyncioTestCase (stdlib — no extra dependencies)
Mocking:   AsyncMock for embedder.embed_text, MagicMock for qdrant.query_points

Run:
    pytest rag/retrival/query_retrival/tests/test_hybrid_retriever.py -v
"""
import unittest
from unittest.mock import AsyncMock, MagicMock

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.retrival.models import TransformedQuery
from rag.retrival.query_retrival.retriever import EmptyCorpusError, HybridRetriever


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_payload(norm_id: str = "ISO9001") -> dict:
    """
    Minimal valid NormChunk payload dict.

    All fields are required by _scored_point_to_chunk — a missing key raises
    KeyError immediately (intentional: missing fields indicate an ingestion bug).
    """
    return {
        "norm_id": norm_id,
        "norm_full": "ISO 9001:2015",
        "norm_version": "2015",
        "clause_number": "8.1",
        "clause_title": "Planification et maîtrise opérationnelles",
        "parent_clause": "8",
        "page_number": 23,
        "chunk_index": 1,
        "total_chunks": 1,
        "text": "L'organisme doit planifier, mettre en oeuvre, maîtriser...",
        "token_count": 42,
        "content_type": "normative",
        "shall_count": 3,
        "should_count": 0,
        "has_requirements": True,
        "has_permissions": False,
        "has_recommendations": False,
        "has_capabilities": False,
        "keywords": ["planification", "maîtrise", "opérationnelle"],
        "related_clauses": ["6.1", "9.1"],
        "embedding_model": "nomic-embed-text",
        "language": "FR",
    }


def _make_transformed_query(norm_filter: list) -> TransformedQuery:
    """
    Build a minimal TransformedQuery directly — no QueryTransformer.transform() call.

    The retriever is being tested, not the transformer.  A real qdrant_filter
    is constructed so the object is valid, but the mock Qdrant ignores it.
    """
    return TransformedQuery(
        embed_text="search_query: audit interne",
        bm25_tokens=["audit", "interne"],
        qdrant_filter=Filter(
            must=[FieldCondition(key="norm_id", match=MatchValue(value=norm_filter[0]))]
        ),
        hyde_used=False,
        iso_vocab_hits=["audit"],
        original_query="audit interne",
        language="FR",
        norm_filter=norm_filter,
    )


# ── Test classes ──────────────────────────────────────────────────────────────

class TestHybridRetrieverSuccess(unittest.IsolatedAsyncioTestCase):
    """Correct norm_filter returns a populated RetrievedChunk list."""

    def setUp(self):
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed_text = AsyncMock(return_value=[0.1] * 768)

        mock_point = MagicMock()
        mock_point.id = "test-uuid-123"
        mock_point.score = 0.42
        mock_point.payload = _make_payload(norm_id="ISO9001")

        mock_response = MagicMock()
        mock_response.points = [mock_point]

        self.mock_qdrant = MagicMock(spec=QdrantClient)
        self.mock_qdrant.query_points.return_value = mock_response

        self.retriever = HybridRetriever(
            embedder=self.mock_embedder,
            qdrant=self.mock_qdrant,
        )

    async def test_correct_filter_returns_chunks(self):
        query = _make_transformed_query(norm_filter=["ISO9001"])
        result = await self.retriever.retrieve(query, top_k=10)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chunk_id, "test-uuid-123")
        self.assertEqual(result[0].norm_id, "ISO9001")
        self.assertAlmostEqual(result[0].rrf_score, 0.42)
        self.assertAlmostEqual(result[0].dense_score, -1.0)
        self.assertAlmostEqual(result[0].sparse_score, -1.0)


class TestHybridRetrieverEmptyCorpusGuard(unittest.IsolatedAsyncioTestCase):
    """Wrong norm_filter value raises EmptyCorpusError with filter value in message."""

    def setUp(self):
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed_text = AsyncMock(return_value=[0.1] * 768)

        mock_response = MagicMock()
        mock_response.points = []

        self.mock_qdrant = MagicMock(spec=QdrantClient)
        self.mock_qdrant.query_points.return_value = mock_response

        self.retriever = HybridRetriever(
            embedder=self.mock_embedder,
            qdrant=self.mock_qdrant,
        )

    async def test_wrong_filter_raises_empty_corpus_error(self):
        query = _make_transformed_query(norm_filter=["WRONG_ID"])

        with self.assertRaises(EmptyCorpusError) as ctx:
            await self.retriever.retrieve(query, top_k=10)

        self.assertIn("WRONG_ID", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
