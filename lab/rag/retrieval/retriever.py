"""Invariant 4 — RAG: retriever.

:class:`Retriever` wires together a :class:`TextSplitter`, an
:class:`EmbedderProtocol`, and a vector store.  It exposes two operations:

* **index** — splits a document, embeds every chunk, adds them to the store.
* **retrieve** — embeds a query string, searches the store, returns ranked
  :class:`SearchResult` objects.

Dependencies are injected so every component can be swapped (e.g.
:class:`StubEmbedder` + :class:`NumpyVectorStore` in tests).
"""

from __future__ import annotations

import logging

from lab.rag.chunking.text_splitter import Chunk, TextSplitter
from lab.rag.embeddings.embedder import EmbedderProtocol
from lab.rag.store.vector_store import NumpyVectorStore, SearchResult

logger = logging.getLogger(__name__)

# The store type is structural — any object with add() / search() / __len__()
# works.  We use NumpyVectorStore as the default type hint for the lab.
_StoreT = NumpyVectorStore  # type alias (not enforced at runtime)


class Retriever:
    """Orchestrates chunking → embedding → indexing → retrieval.

    Args:
        splitter: A :class:`TextSplitter` instance.
        embedder: Any object implementing :class:`EmbedderProtocol`.
        store: A vector store instance (:class:`NumpyVectorStore` or
            :class:`FAISSVectorStore`).

    Example::

        from lab.rag.chunking.text_splitter import TextSplitter
        from lab.rag.embeddings.embedder import StubEmbedder
        from lab.rag.store.vector_store import NumpyVectorStore
        from lab.rag.retrieval.retriever import Retriever

        embedder = StubEmbedder(dim=16)
        retriever = Retriever(
            splitter=TextSplitter(chunk_size=256, chunk_overlap=32),
            embedder=embedder,
            store=NumpyVectorStore(dim=embedder.dim),
        )
        retriever.index("Long document text…")
        results = retriever.retrieve("query", k=3)
    """

    def __init__(
        self,
        splitter: TextSplitter,
        embedder: EmbedderProtocol,
        store: _StoreT,
    ) -> None:
        self._splitter = splitter
        self._embedder = embedder
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index(self, text: str) -> int:
        """Split *text*, embed chunks, add to the vector store.

        Args:
            text: Source document text.

        Returns:
            Number of chunks added to the store (0 if *text* is empty).
        """
        chunks: list[Chunk] = self._splitter.split(text)
        if not chunks:
            logger.warning("Retriever.index: no chunks produced from text of length %d", len(text))
            return 0

        texts = [c.text for c in chunks]
        embeddings = self._embedder.embed(texts)
        self._store.add(chunks, embeddings)
        logger.info("Retriever.index: indexed %d chunks", len(chunks))
        return len(chunks)

    def retrieve(self, query: str, k: int = 5) -> list[SearchResult]:
        """Retrieve the *k* most relevant chunks for *query*.

        Args:
            query: The search query string.
            k: Maximum number of results to return.

        Returns:
            List of :class:`SearchResult` objects sorted by descending
            cosine similarity.  Empty list if the store is empty.

        Raises:
            ValueError: If *query* is empty or whitespace.
        """
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if len(self._store) == 0:
            logger.warning("Retriever.retrieve called on empty store")
            return []

        query_embedding = self._embedder.embed([query])[0]
        results = self._store.search(query_embedding, k=k)
        logger.debug("Retriever.retrieve: query=%r → %d results", query, len(results))
        return results

    def __len__(self) -> int:
        """Return the total number of indexed chunks."""
        return len(self._store)
