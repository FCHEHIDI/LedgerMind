"""Invariant 6 — Workflow: RAG node.

Indexes the raw invoice text and retrieves the most relevant passages using
:class:`lab.rag.pipeline.RAGPipeline` with ``use_stub=True`` (no model
download required).
"""

from __future__ import annotations

import logging
from typing import Any

from lab.workflow.state import WorkflowState

logger = logging.getLogger(__name__)

_RAG_QUERY = "montant TVA HT TTC facture fournisseur"
_RAG_K = 3


def rag_node(state: WorkflowState) -> dict[str, Any]:
    """Index the invoice document and retrieve relevant context passages.

    Args:
        state: Current workflow state.  Reads ``raw_text``.

    Returns:
        Partial state update: ``{"rag_context": str, "rag_chunks_found": int}``.
    """
    from lab.rag.pipeline import RAGPipeline

    text: str = state.get("raw_text", "")  # type: ignore[assignment]
    if not text.strip():
        logger.warning("rag_node: empty raw_text — skipping indexing")
        return {"rag_context": "", "rag_chunks_found": 0}

    pipe = RAGPipeline(use_stub=True, k_default=_RAG_K)
    chunk_count = pipe.index(text)
    result = pipe.query(_RAG_QUERY, k=_RAG_K)
    logger.info("rag_node: indexed %d chunks, retrieved %d", chunk_count, result.chunks_found)
    return {"rag_context": result.context, "rag_chunks_found": result.chunks_found}
