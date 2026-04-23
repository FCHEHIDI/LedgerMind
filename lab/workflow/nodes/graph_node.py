"""Invariant 6 — Workflow: graph node.

Delegates to :data:`lab.graph.graph.invoice_graph` (Invariant 2) to validate
extracted invoice fields and post the journal entry if valid.
"""

from __future__ import annotations

import logging
from typing import Any

from lab.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


def graph_node(state: WorkflowState) -> dict[str, Any]:
    """Run the LangGraph invoice validator and poster.

    Args:
        state: Current workflow state.  Reads ``extracted_fields``.

    Returns:
        Partial state update with ``validation_status``, ``validation_errors``,
        and ``journal_entry_id``.  On unexpected exception, wraps the error
        into ``errors`` and returns ``validation_status="rejected"``.
    """
    from lab.graph.graph import invoice_graph

    fields: dict[str, Any] = state.get("extracted_fields", {})  # type: ignore[assignment]
    try:
        result = invoice_graph.invoke({"raw_input": fields})
        status: str = result.get("status", "rejected")
        val_errors: list[str] = result.get("errors", [])
        je_id: str | None = result.get("journal_entry_id")
        logger.info("graph_node: status=%s je_id=%s errors=%s", status, je_id, val_errors)
        return {
            "validation_status": status,
            "validation_errors": val_errors,
            "journal_entry_id": je_id,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("graph_node unhandled error: %s", exc)
        return {
            "validation_status": "rejected",
            "validation_errors": [str(exc)],
            "journal_entry_id": None,
            "errors": [f"graph_node: {exc}"],
        }
