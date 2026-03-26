"""
embedder/bm25_encoder.py
────────────────────────
Two-pass corpus BM25 encoder: NormChunk.bm25_tokens → (indices, values)
suitable for Qdrant SparseVector.

Algorithm
---------
Pass 1 — __init__(chunks):
    Iterate all chunks to compute per-token document frequency (DF),
    total document count (N), and average document length (avgdl).

Pass 2 — encode(chunk):
    For each token in the chunk, compute the Robertson-Walker BM25 score:

        IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)

        score(t, D) = IDF(t) * TF(t,D)*(k1+1)
                               ─────────────────────────────────
                               TF(t,D) + k1*(1 - b + b*|D|/avgdl)

    with k1=1.2, b=0.75 (Okapi BM25 industry defaults).

Index mapping
-------------
Tokens are mapped to integer indices via a deterministic hash:
    index = int(md5(token.encode("utf-8")).hexdigest(), 16) % SPARSE_DIM

Using hashlib.md5 ensures the same token always maps to the same index
across all pipeline runs without a persistent vocabulary file.

Hash collisions (≈2 % probability at 80 tokens / 131 072 buckets) are
resolved by summing the BM25 scores of colliding tokens — the standard
strategy for hashing-based sparse retrieval.

Output
------
encode() returns two parallel lists sorted by ascending index:
    indices: List[int]   — Qdrant SparseVector integer indices
    values:  List[float] — corresponding BM25 scores (always > 0)

Dependency rule
---------------
Standard library only + NormChunk (chunker.models) + SPARSE_DIM (embedder.config).
No qdrant_client, no segmenter, no enricher, no registry imports.
"""
from __future__ import annotations

import math
from collections import Counter
from hashlib import md5
from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:
    from chunker.models import NormChunk

from .config import SPARSE_DIM


class BM25SparseEncoder:
    """
    Corpus-level BM25 encoder for a batch of NormChunks.

    Lifecycle
    ---------
    1. Instantiate once per embed_chunks() call, passing ALL eligible chunks
       so that corpus statistics (DF, avgdl) reflect the full vocabulary.
    2. Call encode(chunk) once per chunk to get (indices, values).

    Parameters
    ----------
    chunks : List[NormChunk]
        All chunks that will be embedded in this run (used for Pass 1).
    k1 : float
        BM25 term-saturation parameter (default 1.2).
    b : float
        BM25 length-normalisation parameter (default 0.75).
    """

    def __init__(
        self,
        chunks: List[NormChunk],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self._k1: float = k1
        self._b: float = b
        self._n_docs: int = len(chunks)

        # Pass 1 — build corpus statistics from bm25_tokens.
        # bm25_tokens are already stop-word-filtered and enriched by Phase 5;
        # use set() when counting DF so each token counts once per document.
        self._df: Dict[str, int] = {}
        total_len: int = 0
        for chunk in chunks:
            tokens = chunk.bm25_tokens
            total_len += len(tokens)
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1

        self._avgdl: float = total_len / self._n_docs if self._n_docs > 0 else 1.0

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _token_to_index(token: str) -> int:
        """
        Map a token string to a deterministic integer index in [0, SPARSE_DIM).

        hashlib.md5 produces a stable 128-bit hash regardless of PYTHONHASHSEED,
        making this safe for multi-run vocabulary consistency.
        """
        return int(md5(token.encode("utf-8")).hexdigest(), 16) % SPARSE_DIM

    def _idf(self, token: str) -> float:
        """
        Robertson-Walker IDF variant — always positive even when df = N.

            IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)

        Falls back to df=1 for tokens unseen in Pass 1 (defensive guard;
        should never occur when encode() is called on a corpus chunk).
        """
        df = self._df.get(token, 1)
        return math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1.0)

    # ── Public API ────────────────────────────────────────────────────────────

    def encode(self, chunk: NormChunk) -> Tuple[List[int], List[float]]:
        """
        Compute the BM25 sparse vector for a single chunk.

        Steps
        -----
        1. Count term frequencies in chunk.bm25_tokens.
        2. For each token compute BM25 score.
        3. Map token to integer index via MD5 hash.
        4. Sum scores on index collision.
        5. Return (indices, values) sorted by ascending index.

        Returns
        -------
        Tuple[List[int], List[float]]
            Two parallel lists ready for SparseVector(indices=..., values=...).
            Both lists are empty when bm25_tokens is empty.
            All values are > 0.0 (zero-score tokens are skipped).
        """
        tokens = chunk.bm25_tokens
        if not tokens:
            return [], []

        doc_len = len(tokens)
        tf = Counter(tokens)

        scores: Dict[int, float] = {}
        for token, tf_val in tf.items():
            idf = self._idf(token)
            numerator = tf_val * (self._k1 + 1.0)
            denominator = tf_val + self._k1 * (
                1.0 - self._b + self._b * doc_len / self._avgdl
            )
            score = idf * (numerator / denominator)
            if score <= 0.0:
                continue  # skip zero/negative scores (rare with Robertson IDF)
            idx = self._token_to_index(token)
            scores[idx] = scores.get(idx, 0.0) + score  # collision → sum

        sorted_pairs = sorted(scores.items())  # ascending index order
        indices = [i for i, _ in sorted_pairs]
        values = [v for _, v in sorted_pairs]
        return indices, values


    
    @staticmethod
    def encode_query(tokens: List[str]) -> Tuple[List[int], List[float]]:
        """
        Produce a sparse query vector for hybrid retrieval.

        Unlike encode(), this method requires no corpus statistics.
        Each token is assigned uniform weight 1.0 — IDF weighting already
        happened at index time via the document-side BM25 scores stored in
        Qdrant.  The query just signals *which* tokens to look for.

        Collision handling mirrors encode(): when two tokens hash to the
        same index, their weights are summed.

        Parameters
        ----------
        tokens : List[str]
            Pre-processed query tokens (e.g. TransformedQuery.bm25_tokens).
            May be empty — returns ([], []) in that case.

        Returns
        -------
        Tuple[List[int], List[float]]
            Two parallel lists sorted by ascending index, ready for
            SparseVector(indices=..., values=...).
        """
        if not tokens:
            return [], []

        scores: Dict[int, float] = {}
        for token in tokens:
            idx = BM25SparseEncoder._token_to_index(token)
            scores[idx] = scores.get(idx, 0.0) + 1.0  # uniform weight; sum on collision

        sorted_pairs = sorted(scores.items())           # ascending index order
        indices = [i for i, _ in sorted_pairs]
        values  = [v for _, v in sorted_pairs]
        return indices, values
