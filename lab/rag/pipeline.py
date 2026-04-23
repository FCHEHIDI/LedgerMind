"""Invariant 4 — RAG: high-level pipeline.

:class:`RAGPipeline` is the public entry-point for the retrieval-augmented
generation layer.  It assembles :class:`TextSplitter`, an embedder, and a
vector store into a single object that the Workflow invariant (Inv.6) will
orchestrate.

Usage::

    from lab.rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()          # uses StubEmbedder in test mode
    pipeline.index(document_text)
    result = pipeline.query("Quel est le montant HT ?")
    print(result.context)             # top-k chunk text, joined

By default the pipeline uses :class:`SentenceTransformerEmbedder` (which
downloads a model on first use).  Pass ``use_stub=True`` for offline / test
environments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from lab.rag.chunking.text_splitter import TextSplitter
from lab.rag.embeddings.embedder import EmbedderProtocol, StubEmbedder
from lab.rag.retrieval.retriever import Retriever
from lab.rag.store.vector_store import NumpyVectorStore, SearchResult

logger = logging.getLogger(__name__)

_CONTEXT_SEPARATOR = "\n\n---\n\n"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class RAGResult:
    """Output of a single RAG query.

    Attributes:
        query: The original question string.
        results: Ranked :class:`SearchResult` objects (best first).
        context: Concatenated chunk texts, ready to inject into an LLM prompt.
        chunks_found: Number of results returned (≤ k).
    """

    query: str
    results: list[SearchResult]
    context: str
    chunks_found: int


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class RAGPipeline:
    """End-to-end RAG pipeline: index documents, then query them.

    Args:
        chunk_size: Maximum characters per chunk (default 512).
        chunk_overlap: Overlap between consecutive chunks (default 64).
        use_stub: If ``True``, use :class:`StubEmbedder` (16-dim, offline).
            If ``False`` (default), use :class:`SentenceTransformerEmbedder`.
        model_name: HuggingFace model ID (ignored when *use_stub* is True).
        k_default: Default number of results returned by :meth:`query`.

    Example::

        pipe = RAGPipeline(use_stub=True)
        pipe.index("Prestation 1 000 € HT — TVA 20 %…")
        result = pipe.query("montant HT")
        assert result.chunks_found >= 1
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        use_stub: bool = False,
        model_name: str = "all-MiniLM-L6-v2",
        k_default: int = 5,
    ) -> None:
        self._k_default = k_default

        splitter = TextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        if use_stub:
            embedder: EmbedderProtocol = StubEmbedder(dim=16)
            dim = 16
        else:
            from lab.rag.embeddings.embedder import SentenceTransformerEmbedder

            embedder = SentenceTransformerEmbedder(model_name=model_name)
            dim = 384  # all-MiniLM-L6-v2 default; overridden after first embed

        store = NumpyVectorStore(dim=dim)
        self._retriever = Retriever(splitter=splitter, embedder=embedder, store=store)
        logger.debug(
            "RAGPipeline init: chunk_size=%d, chunk_overlap=%d, use_stub=%s",
            chunk_size,
            chunk_overlap,
            use_stub,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index(self, text: str) -> int:
        """Chunk, embed and index *text*.

        Args:
            text: Document text (e.g. output of :class:`IntakePipeline`).

        Returns:
            Number of chunks indexed (0 if *text* is empty).
        """
        n = self._retriever.index(text)
        logger.info("RAGPipeline.index: %d chunks indexed", n)
        return n

    def query(self, question: str, k: int | None = None) -> RAGResult:
        """Retrieve the most relevant chunks for *question*.

        Args:
            question: The natural-language query.
            k: Number of chunks to retrieve.  Defaults to ``k_default``.

        Returns:
            :class:`RAGResult` with ranked chunks and a formatted context
            string.
        """
        k = k if k is not None else self._k_default
        results = self._retriever.retrieve(question, k=k)
        context = _CONTEXT_SEPARATOR.join(r.chunk.text for r in results)
        rag_result = RAGResult(
            query=question,
            results=results,
            context=context,
            chunks_found=len(results),
        )
        logger.debug("RAGPipeline.query: %r → %d chunks", question, len(results))
        return rag_result

    def __len__(self) -> int:
        """Total number of indexed chunks."""
        return len(self._retriever)
