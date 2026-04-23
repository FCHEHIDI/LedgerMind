"""Rejector node — terminal node for invalid or rejected invoices.

Responsibility: log the rejection and emit a clean final status.
No side effects beyond logging — notification/alerting belongs to
the infrastructure layer (out of scope for this lab invariant).
"""

from __future__ import annotations

import logging

from ..domain.state import InvoiceState

logger = logging.getLogger(__name__)


def rejector_node(state: InvoiceState) -> dict:
    """Log and finalize the rejection of an invoice.

    Reads accumulated errors from the state and logs them at WARNING level.
    Sets status to "rejected" as the canonical terminal value for failures.

    Args:
        state: Current InvoiceState (status should be "invalid").

    Returns:
        Partial state dict: ``{"status": "rejected"}``.
    """
    invoice = state.get("invoice")
    ref = invoice.reference if invoice else "UNKNOWN"
    errors = state.get("errors", [])

    logger.warning(
        "rejector_node: facture rejetée ref=%s — %d erreur(s): %s",
        ref, len(errors), errors,
    )
    return {"status": "rejected"}
