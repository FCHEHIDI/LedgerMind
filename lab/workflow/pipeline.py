"""Invariant 6 — Workflow: LangGraph orchestration pipeline.

Topology
--------
::

    intake_node → rag_node → graph_node ──[posted]──→ mcp_node → END
                                        └──[other]──→ END

The ``intake_node`` extracts fields via regex (Inv.3).
The ``rag_node`` indexes the document and retrieves context (Inv.4).
The ``graph_node`` validates + posts to ledger via invoice_graph (Inv.2 / Inv.1).
The ``mcp_node`` looks up PCG accounts via MCPServer (Inv.5) — valid path only.

Usage
-----
::

    from lab.workflow.pipeline import invoice_workflow

    result = invoice_workflow.invoke({"raw_text": "...invoice text..."})
    print(result["validation_status"])   # 'posted' | 'rejected'
    print(result["journal_entry_id"])    # UUID string or None
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from lab.workflow.nodes.graph_node import graph_node
from lab.workflow.nodes.intake_node import intake_node
from lab.workflow.nodes.mcp_node import mcp_node
from lab.workflow.nodes.rag_node import rag_node
from lab.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


def _route_after_graph(state: WorkflowState) -> str:
    """Route to mcp_node on success, else terminate.

    Args:
        state: Current workflow state after graph_node has run.

    Returns:
        ``"mcp_node"`` if invoice was posted, else ``END``.
    """
    status = state.get("validation_status", "")
    if status == "posted":
        logger.debug("workflow routing: posted → mcp_node")
        return "mcp_node"
    logger.debug("workflow routing: %s → END", status)
    return END


def build_workflow() -> StateGraph:
    """Construct and compile the invoice workflow graph.

    Returns:
        Compiled :class:`langgraph.graph.StateGraph` ready for ``.invoke()``.
    """
    wf: StateGraph = StateGraph(WorkflowState)

    wf.add_node("intake_node", intake_node)
    wf.add_node("rag_node", rag_node)
    wf.add_node("graph_node", graph_node)
    wf.add_node("mcp_node", mcp_node)

    wf.set_entry_point("intake_node")
    wf.add_edge("intake_node", "rag_node")
    wf.add_edge("rag_node", "graph_node")
    wf.add_conditional_edges(
        "graph_node",
        _route_after_graph,
        {"mcp_node": "mcp_node", END: END},
    )
    wf.add_edge("mcp_node", END)

    return wf.compile()


#: Module-level compiled workflow — import this for normal use.
invoice_workflow = build_workflow()
