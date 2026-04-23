"""Invoice processing graph — Invariant 2.

Assembles the four nodes into a StateGraph that processes supplier invoices
from raw input through extraction, validation, and accounting (or rejection).

Graph topology:

    START
      │
    extractor ──→ validator ──→ [route_after_validation]
                                    ├─ "valid"   → accountant → END
                                    └─ "invalid" → rejector   → END

Usage::

    from lab.graph import invoice_graph

    result = invoice_graph.invoke({
        "raw_input": {
            "vendor": "ACME",
            "siren": "123456789",
            "date": "2024-01-15",
            "reference": "FA-2024-001",
            "ht_amount": "1000.00",
            "tva_rate": "0.20",
            "tva_amount": "200.00",
            "ttc_amount": "1200.00",
        },
        "invoice": None,
        "errors": [],
        "status": "pending",
        "journal_entry_id": None,
    })
    print(result["status"])          # "posted"
    print(result["journal_entry_id"]) # UUID string
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from .domain.state import InvoiceState
from .nodes.accountant import accountant_node
from .nodes.extractor import extractor_node
from .nodes.rejector import rejector_node
from .nodes.validator import validator_node

logger = logging.getLogger(__name__)


def _route_after_validation(state: InvoiceState) -> str:
    """Conditional edge: route to accountant or rejector based on status.

    Args:
        state: Current InvoiceState after validator has run.

    Returns:
        "accountant" when status is "valid", "rejector" otherwise.
    """
    route = "accountant" if state.get("status") == "valid" else "rejector"
    logger.debug("_route_after_validation: status=%s → %s", state.get("status"), route)
    return route


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

_builder: StateGraph = StateGraph(InvoiceState)

_builder.add_node("extractor",  extractor_node)
_builder.add_node("validator",  validator_node)
_builder.add_node("accountant", accountant_node)
_builder.add_node("rejector",   rejector_node)

_builder.set_entry_point("extractor")
_builder.add_edge("extractor", "validator")

_builder.add_conditional_edges(
    "validator",
    _route_after_validation,
    {"accountant": "accountant", "rejector": "rejector"},
)

_builder.add_edge("accountant", END)
_builder.add_edge("rejector",   END)

invoice_graph = _builder.compile()
