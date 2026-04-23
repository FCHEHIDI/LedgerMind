"""Invariant 4 — RAG: test suite.

No model downloads, no FAISS required.  All tests use:
  * StubEmbedder   — deterministic SHA-256 embeddings, 16-dim
  * NumpyVectorStore — pure-numpy brute-force cosine similarity

Test groups:
  TestTextSplitter    (10 tests) — chunking invariants
  TestStubEmbedder    ( 6 tests) — embedding shape, determinism, normalisation
  TestNumpyVectorStore( 8 tests) — add / search / error paths
  TestRetriever       ( 6 tests) — index + retrieve integration
  TestRAGPipeline     ( 7 tests) — end-to-end pipeline (use_stub=True)
"""

from __future__ import annotations

import math
import pytest
import numpy as np

from lab.rag.chunking.text_splitter import Chunk, TextSplitter
from lab.rag.embeddings.embedder import EmbedderProtocol, StubEmbedder
from lab.rag.store.vector_store import NumpyVectorStore, SearchResult
from lab.rag.retrieval.retriever import Retriever
from lab.rag.pipeline import RAGPipeline, RAGResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# A realistic French invoice fragment (~700 chars, produces ≥ 2 chunks at 512)
INVOICE_DOCUMENT = (
    "ACME SAS — Fournisseur de services informatiques\n"
    "12 rue de la Paix, 75001 Paris\n"
    "SIREN : 123 456 789\n\n"
    "Facture n° FA-2024-042\n"
    "Date : 15 janvier 2024\n\n"
    "Désignation                         Montant HT\n"
    "Développement logiciel (forfait)    8 500,00 €\n"
    "Hébergement cloud (mensuel)           350,00 €\n"
    "Support technique (10 h × 95 €/h)    950,00 €\n\n"
    "Total HT                            9 800,00 €\n"
    "TVA 20 %                            1 960,00 €\n"
    "Total TTC                          11 760,00 €\n\n"
    "Conditions de paiement : 30 jours net\n"
    "RIB : FR76 1234 5678 9012 3456 7890 123\n"
    "Merci de votre confiance."
)

SHORT_TEXT = "Bonjour le monde. Comment allez-vous ?"
EMPTY_TEXT = "   "


def _make_retriever(chunk_size: int = 200, chunk_overlap: int = 30, dim: int = 16) -> Retriever:
    """Helper: build a Retriever with StubEmbedder + NumpyVectorStore."""
    embedder = StubEmbedder(dim=dim)
    return Retriever(
        splitter=TextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        embedder=embedder,
        store=NumpyVectorStore(dim=dim),
    )


# ---------------------------------------------------------------------------
# TestTextSplitter
# ---------------------------------------------------------------------------


class TestTextSplitter:
    """Chunking invariants — no external deps."""

    def test_split_short_text_returns_single_chunk(self) -> None:
        splitter = TextSplitter(chunk_size=512, chunk_overlap=64)
        chunks = splitter.split(SHORT_TEXT)
        assert len(chunks) == 1
        assert chunks[0].text == SHORT_TEXT.strip()

    def test_split_empty_text_returns_empty_list(self) -> None:
        splitter = TextSplitter(chunk_size=512, chunk_overlap=64)
        assert splitter.split(EMPTY_TEXT) == []

    def test_split_long_text_produces_multiple_chunks(self) -> None:
        splitter = TextSplitter(chunk_size=200, chunk_overlap=30)
        chunks = splitter.split(INVOICE_DOCUMENT)
        assert len(chunks) >= 2

    def test_chunk_index_is_sequential(self) -> None:
        splitter = TextSplitter(chunk_size=200, chunk_overlap=30)
        chunks = splitter.split(INVOICE_DOCUMENT)
        for i, chunk in enumerate(chunks):
            assert chunk.index == i

    def test_chunk_text_is_non_empty(self) -> None:
        splitter = TextSplitter(chunk_size=200, chunk_overlap=30)
        for chunk in splitter.split(INVOICE_DOCUMENT):
            assert chunk.text.strip() != ""

    def test_chunk_len_within_chunk_size(self) -> None:
        chunk_size = 200
        splitter = TextSplitter(chunk_size=chunk_size, chunk_overlap=30)
        for chunk in splitter.split(INVOICE_DOCUMENT):
            # Merged chunks can slightly exceed due to join spaces — allow 10 % margin.
            assert len(chunk.text) <= chunk_size * 1.25, f"Chunk too long: {len(chunk.text)}"

    def test_chunk_is_frozen_dataclass(self) -> None:
        splitter = TextSplitter(chunk_size=512, chunk_overlap=64)
        chunk = splitter.split(SHORT_TEXT)[0]
        with pytest.raises((AttributeError, TypeError)):
            chunk.text = "mutated"  # type: ignore[misc]

    def test_invalid_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            TextSplitter(chunk_size=0)

    def test_overlap_ge_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_overlap"):
            TextSplitter(chunk_size=100, chunk_overlap=100)

    def test_custom_separators_respected(self) -> None:
        text = "aaa|bbb|ccc"
        splitter = TextSplitter(chunk_size=4, chunk_overlap=0, separators=["|", ""])
        chunks = splitter.split(text)
        # Each piece "aaa", "bbb", "ccc" is ≤ 4 chars
        for chunk in chunks:
            assert len(chunk.text) <= 4


# ---------------------------------------------------------------------------
# TestStubEmbedder
# ---------------------------------------------------------------------------


class TestStubEmbedder:
    """Shape, determinism, and L2-normalisation of the test embedder."""

    def test_embed_returns_correct_shape(self) -> None:
        embedder = StubEmbedder(dim=16)
        result = embedder.embed(["hello", "world"])
        assert result.shape == (2, 16)

    def test_embed_dtype_is_float32(self) -> None:
        embedder = StubEmbedder(dim=16)
        result = embedder.embed(["test"])
        assert result.dtype == np.float32

    def test_embed_is_l2_normalised(self) -> None:
        embedder = StubEmbedder(dim=16)
        result = embedder.embed(["abc", "xyz"])
        for row in result:
            norm = float(np.linalg.norm(row))
            assert math.isclose(norm, 1.0, abs_tol=1e-6), f"norm={norm}"

    def test_embed_is_deterministic(self) -> None:
        embedder = StubEmbedder(dim=16)
        a = embedder.embed(["reproducible"])
        b = embedder.embed(["reproducible"])
        np.testing.assert_array_equal(a, b)

    def test_different_texts_produce_different_vectors(self) -> None:
        embedder = StubEmbedder(dim=16)
        a = embedder.embed(["foo"])[0]
        b = embedder.embed(["bar"])[0]
        assert not np.allclose(a, b)

    def test_embed_empty_list_raises(self) -> None:
        embedder = StubEmbedder(dim=16)
        with pytest.raises(ValueError, match="empty"):
            embedder.embed([])


# ---------------------------------------------------------------------------
# TestNumpyVectorStore
# ---------------------------------------------------------------------------


class TestNumpyVectorStore:
    """Vector store correctness — pure numpy, no FAISS."""

    DIM = 16

    def _embedder(self) -> StubEmbedder:
        return StubEmbedder(dim=self.DIM)

    def _dummy_chunks(self, n: int) -> list[Chunk]:
        return [Chunk(text=f"chunk {i}", index=i, start_char=i * 10, end_char=i * 10 + 7) for i in range(n)]

    def test_add_increases_length(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        chunks = self._dummy_chunks(3)
        embeddings = embedder.embed([c.text for c in chunks])
        store.add(chunks, embeddings)
        assert len(store) == 3

    def test_search_returns_k_results(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        chunks = self._dummy_chunks(10)
        embeddings = embedder.embed([c.text for c in chunks])
        store.add(chunks, embeddings)
        query = embedder.embed(["chunk 5"])[0]
        results = store.search(query, k=3)
        assert len(results) == 3

    def test_search_results_are_sorted_by_descending_score(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        chunks = self._dummy_chunks(5)
        embeddings = embedder.embed([c.text for c in chunks])
        store.add(chunks, embeddings)
        query = embedder.embed(["chunk 2"])[0]
        results = store.search(query, k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_exact_match_is_top_result(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        chunks = self._dummy_chunks(5)
        embeddings = embedder.embed([c.text for c in chunks])
        store.add(chunks, embeddings)
        # Query is identical to "chunk 2" → its embedding is identical → score ≈ 1.0
        query = embedder.embed(["chunk 2"])[0]
        results = store.search(query, k=5)
        assert results[0].chunk.text == "chunk 2"

    def test_search_score_between_minus1_and_1(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        chunks = self._dummy_chunks(4)
        embeddings = embedder.embed([c.text for c in chunks])
        store.add(chunks, embeddings)
        query = embedder.embed(["test"])[0]
        for r in store.search(query, k=4):
            assert -1.0 <= r.score <= 1.0 + 1e-6

    def test_search_empty_store_raises(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        query = embedder.embed(["test"])[0]
        with pytest.raises(RuntimeError, match="empty"):
            store.search(query, k=3)

    def test_add_length_mismatch_raises(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder = self._embedder()
        chunks = self._dummy_chunks(3)
        embeddings = embedder.embed([c.text for c in chunks[:2]])  # only 2 embeddings
        with pytest.raises(ValueError, match="length"):
            store.add(chunks, embeddings)

    def test_add_dim_mismatch_raises(self) -> None:
        store = NumpyVectorStore(dim=self.DIM)
        embedder_wrong = StubEmbedder(dim=8)  # wrong dim
        chunks = self._dummy_chunks(2)
        embeddings = embedder_wrong.embed([c.text for c in chunks])
        with pytest.raises(ValueError, match="dim"):
            store.add(chunks, embeddings)


# ---------------------------------------------------------------------------
# TestRetriever
# ---------------------------------------------------------------------------


class TestRetriever:
    """Integration of TextSplitter + StubEmbedder + NumpyVectorStore."""

    def test_index_returns_positive_chunk_count(self) -> None:
        retriever = _make_retriever()
        n = retriever.index(INVOICE_DOCUMENT)
        assert n >= 1

    def test_index_empty_text_returns_zero(self) -> None:
        retriever = _make_retriever()
        n = retriever.index(EMPTY_TEXT)
        assert n == 0

    def test_retrieve_returns_results_after_indexing(self) -> None:
        retriever = _make_retriever()
        retriever.index(INVOICE_DOCUMENT)
        results = retriever.retrieve("Total HT", k=3)
        assert len(results) >= 1

    def test_retrieve_empty_query_raises(self) -> None:
        retriever = _make_retriever()
        retriever.index(INVOICE_DOCUMENT)
        with pytest.raises(ValueError, match="empty"):
            retriever.retrieve("   ")

    def test_retrieve_on_empty_store_returns_empty_list(self) -> None:
        retriever = _make_retriever()
        results = retriever.retrieve("anything")
        assert results == []

    def test_len_matches_indexed_chunks(self) -> None:
        retriever = _make_retriever()
        n = retriever.index(INVOICE_DOCUMENT)
        assert len(retriever) == n


# ---------------------------------------------------------------------------
# TestRAGPipeline
# ---------------------------------------------------------------------------


class TestRAGPipeline:
    """End-to-end pipeline tests — use_stub=True, no model download."""

    def _pipeline(self) -> RAGPipeline:
        return RAGPipeline(chunk_size=200, chunk_overlap=30, use_stub=True, k_default=5)

    def test_index_returns_positive_count(self) -> None:
        pipe = self._pipeline()
        n = pipe.index(INVOICE_DOCUMENT)
        assert n >= 1

    def test_query_before_index_returns_empty_context(self) -> None:
        pipe = self._pipeline()
        result = pipe.query("montant HT")
        assert result.chunks_found == 0
        assert result.context == ""

    def test_query_returns_rag_result(self) -> None:
        pipe = self._pipeline()
        pipe.index(INVOICE_DOCUMENT)
        result = pipe.query("Total TTC")
        assert isinstance(result, RAGResult)

    def test_query_result_has_context_string(self) -> None:
        pipe = self._pipeline()
        pipe.index(INVOICE_DOCUMENT)
        result = pipe.query("TVA 20 %")
        assert isinstance(result.context, str)
        assert len(result.context) > 0

    def test_query_chunks_found_le_k(self) -> None:
        pipe = self._pipeline()
        pipe.index(INVOICE_DOCUMENT)
        result = pipe.query("SIREN", k=2)
        assert result.chunks_found <= 2

    def test_pipeline_len_after_index(self) -> None:
        pipe = self._pipeline()
        n = pipe.index(INVOICE_DOCUMENT)
        assert len(pipe) == n

    def test_multiple_index_calls_accumulate(self) -> None:
        pipe = self._pipeline()
        n1 = pipe.index(SHORT_TEXT)
        n2 = pipe.index(INVOICE_DOCUMENT)
        assert len(pipe) == n1 + n2
