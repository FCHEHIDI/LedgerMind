"""Invariant 6 — Workflow: shared LangGraph state definition."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional

from typing_extensions import TypedDict


class WorkflowState(TypedDict):
    """Full mutable state threaded through the invoice workflow graph.

    Only ``raw_text`` is required at invocation time.  All other fields are
    populated by the workflow nodes.

    Attributes:
        raw_text: Raw invoice text (required at invocation).
        extracted_fields: Regex-extracted field dict from intake_node.
        rag_context: Concatenated top-k chunk texts from rag_node.
        rag_chunks_found: Number of chunks retrieved by rag_node.
        validation_status: 'posted' | 'rejected' | 'invalid' from graph_node.
        validation_errors: List of validation error messages from graph_node.
        journal_entry_id: UUID string set when invoice is posted, else None.
        pcg_lookups: PCG account lookup results from mcp_node (valid path only).
        errors: Accumulated node-level errors (reducer: list concatenation).
    """

    raw_text: str
    extracted_fields: dict[str, Any]
    rag_context: str
    rag_chunks_found: int
    validation_status: str
    validation_errors: list[str]
    journal_entry_id: Optional[str]
    pcg_lookups: list[dict[str, Any]]
    errors: Annotated[list[str], operator.add]
