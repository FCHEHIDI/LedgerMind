"""Invariant 4 — RAG: public re-exports."""

from lab.rag.pipeline import RAGPipeline, RAGResult
from lab.rag.chunking.text_splitter import Chunk, TextSplitter
from lab.rag.embeddings.embedder import EmbedderProtocol, StubEmbedder, SentenceTransformerEmbedder
from lab.rag.store.vector_store import NumpyVectorStore, FAISSVectorStore, SearchResult
from lab.rag.retrieval.retriever import Retriever

__all__ = [
    "RAGPipeline",
    "RAGResult",
    "Chunk",
    "TextSplitter",
    "EmbedderProtocol",
    "StubEmbedder",
    "SentenceTransformerEmbedder",
    "NumpyVectorStore",
    "FAISSVectorStore",
    "SearchResult",
    "Retriever",
]
