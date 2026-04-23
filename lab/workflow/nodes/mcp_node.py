"""Invariant 6 — Workflow: MCP node.

Uses :class:`lab.mcp.server.MCPServer` (Invariant 5) to look up the PCG
accounts that appear in a standard purchase invoice journal entry:

    401  — Fournisseurs
    607  — Achats de marchandises
    44566 — TVA déductible sur autres biens et services

This node is only reached when the invoice has been successfully posted
(``validation_status == "posted"``).
"""

from __future__ import annotations

import logging
from typing import Any

from lab.workflow.state import WorkflowState

logger = logging.getLogger(__name__)

# Standard PCG accounts involved in a purchase invoice journal entry.
_PCG_CODES = ["401", "607", "44566"]


def mcp_node(state: WorkflowState) -> dict[str, Any]:
    """Look up PCG accounts for the posted journal entry via MCPServer.

    Args:
        state: Current workflow state.  Reads ``journal_entry_id`` for logging.

    Returns:
        Partial state update: ``{"pcg_lookups": list[dict]}``.
    """
    from lab.mcp.server import MCPServer

    server = MCPServer()
    je_id: str | None = state.get("journal_entry_id")  # type: ignore[assignment]
    lookups: list[dict[str, Any]] = []

    for code in _PCG_CODES:
        resp = server.handle({
            "jsonrpc": "2.0",
            "id": code,
            "method": "tools/call",
            "params": {"name": "lookup_pcg_account", "arguments": {"code": code}},
        })
        if "result" in resp:
            lookups.append(resp["result"])
        else:
            # Should never happen — lookup_pcg_account never raises.
            logger.warning("mcp_node: unexpected error for code=%s: %s", code, resp.get("error"))

    logger.info("mcp_node: je_id=%s looked up %d accounts", je_id, len(lookups))
    return {"pcg_lookups": lookups}
