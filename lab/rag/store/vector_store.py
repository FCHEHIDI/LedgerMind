"""Invariant 4 — RAG: in-memory FAISS vector store.

This module wraps FAISS ``IndexFlatIP`` (inner-product / cosine similarity on
L2-normalised vectors) with a simple Python API that maps search results back
to the original :class:`~lab.rag.chunking.text_splitter.Chunk` objects.

Design decisions
----------------
* **FAISS ``IndexFlatIP``** — exact search, no approximation.  Correct for a
  lab with < 10 k chunks.  For production, swap for ``IndexIVFFlat`` with a
  trained quantizer.
* **Cosine similarity via inner-product** — works because both index vectors
  and query vectors are L2-normalised before insertion / search.
* **Lazy FAISS import** — ``faiss`` is imported only inside methods so the
  module can be imported in environments where FAISS is absent (unit tests
  inject a :class:`NumpyVectorStore` that uses only numpy).

Two implementations are provided:
* :class:`FAISSVectorStore` — production store backed by FAISS.
* :class:`NumpyVectorStore` — pure-numpy fallback for environments without
  FAISS (used in unit tests).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from lab.rag.chunking.text_splitter import Chunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """A single retrieval result.

    Attributes:
        chunk: The matching :class:`Chunk`.
        score: Cosine similarity in ``[−1, 1]``.  Higher is more similar.
            Exact inner-product of two L2-normalised vectors.
    """

    chunk: Chunk
    score: float


# ---------------------------------------------------------------------------
# FAISS-backed store (production)
# ---------------------------------------------------------------------------


class FAISSVectorStore:
    """In-memory vector store backed by FAISS ``IndexFlatIP``.

    Vectors must be L2-normalised before insertion so that inner-product ==
    cosine similarity.

    Args:
        dim: Embedding dimension.  Must match the embedder output dimension.

    Raises:
        ImportError: If ``faiss-cpu`` (or ``faiss-gpu``) is not installed.
    """

    def __init__(self, dim: int) -> None:
        if dim < 1:
            raise ValueError(f"dim must be >= 1, got {dim}")
        self._dim = dim
        self._chunks: list[Chunk] = []
        self._index = None  # built lazily on first add()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """Index *chunks* with their corresponding *embeddings*.

        Args:
            chunks: Source chunks to store.
            embeddings: Float32 ndarray of shape ``(len(chunks), dim)``.
                Rows must be L2-normalised.

        Raises:
            ValueError: If ``len(chunks) != len(embeddings)`` or dim mismatch.
            ImportError: If FAISS is not installed.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have equal length"
            )
        if embeddings.shape[1] != self._dim:
            raise ValueError(
                f"Embedding dim mismatch: expected {self._dim}, got {embeddings.shape[1]}"
            )

        self._ensure_index()
        vectors = embeddings.astype(np.float32)
        self._index.add(vectors)  # type: ignore[union-attr]
        self._chunks.extend(chunks)
        logger.debug("FAISSVectorStore.add: +%d chunks (total=%d)", len(chunks), len(self._chunks))

    def search(self, query_embedding: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Return the *k* most similar chunks.

        Args:
            query_embedding: 1-D float32 vector of size *dim* (L2-normalised).
            k: Number of results to return.  Clamped to ``len(self)``.

        Returns:
            List of :class:`SearchResult` sorted by descending score.

        Raises:
            RuntimeError: If the store is empty.
        """
        if len(self._chunks) == 0:
            raise RuntimeError("Vector store is empty. Call add() first.")

        k = min(k, len(self._chunks))
        query = query_embedding.astype(np.float32).reshape(1, -1)
        scores, indices = self._index.search(query, k)  # type: ignore[union-attr]

        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue  # FAISS sentinel for not-found
            results.append(SearchResult(chunk=self._chunks[idx], score=float(score)))

        logger.debug("FAISSVectorStore.search: k=%d → %d results", k, len(results))
        return results

    def __len__(self) -> int:
        """Return the number of indexed chunks."""
        return len(self._chunks)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_index(self) -> None:
        """Build FAISS index on first use."""
        if self._index is not None:
            return
        try:
            import faiss  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "faiss-cpu is required. Install it with: pip install faiss-cpu"
            ) from exc
        self._index = faiss.IndexFlatIP(self._dim)
        logger.debug("FAISSVectorStore: IndexFlatIP created (dim=%d)", self._dim)


# ---------------------------------------------------------------------------
# Pure-numpy fallback (unit tests, no FAISS dependency)
# ---------------------------------------------------------------------------


class NumpyVectorStore:
    """Pure-numpy brute-force cosine-similarity store.

    Identical public API to :class:`FAISSVectorStore`.  O(n·d) per query —
    suitable only for small corpora (< 10 k chunks).  Use in tests and
    environments where FAISS is unavailable.

    Args:
        dim: Embedding dimension.
    """

    def __init__(self, dim: int) -> None:
        if dim < 1:
            raise ValueError(f"dim must be >= 1, got {dim}")
        self._dim = dim
        self._chunks: list[Chunk] = []
        self._matrix: np.ndarray | None = None  # (n, dim) float32

    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """Add *chunks* with *embeddings* to the store.

        Args:
            chunks: Source chunks.
            embeddings: Float32 ndarray of shape ``(len(chunks), dim)``.

        Raises:
            ValueError: On shape mismatch.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch"
            )
        if embeddings.shape[1] != self._dim:
            raise ValueError(
                f"Embedding dim mismatch: expected {self._dim}, got {embeddings.shape[1]}"
            )
        vecs = embeddings.astype(np.float32)
        self._chunks.extend(chunks)
        self._matrix = vecs if self._matrix is None else np.vstack([self._matrix, vecs])
        logger.debug("NumpyVectorStore.add: +%d chunks (total=%d)", len(chunks), len(self._chunks))

    def search(self, query_embedding: np.ndarray, k: int = 5) -> list[SearchResult]:
        """Return *k* most similar chunks by cosine similarity.

        Args:
            query_embedding: 1-D float32 vector of size *dim*.
            k: Number of results.

        Returns:
            :class:`SearchResult` list sorted by descending score.

        Raises:
            RuntimeError: If the store is empty.
        """
        if self._matrix is None or len(self._chunks) == 0:
            raise RuntimeError("Vector store is empty. Call add() first.")

        q = query_embedding.astype(np.float32).flatten()
        # Cosine similarity = dot product (vectors already normalised).
        scores: np.ndarray = self._matrix @ q
        k = min(k, len(self._chunks))
        top_indices = np.argsort(-scores)[:k]

        results = [
            SearchResult(chunk=self._chunks[int(i)], score=float(scores[i]))
            for i in top_indices
        ]
        logger.debug("NumpyVectorStore.search: k=%d → %d results", k, len(results))
        return results

    def __len__(self) -> int:
        """Return the number of indexed chunks."""
        return len(self._chunks)
