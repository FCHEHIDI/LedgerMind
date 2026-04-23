"""Extractor node — transforms raw_input dict into a structured InvoiceData.

Responsibility: type-coerce and parse raw data. No business rules here —
those live in the validator. On any parsing failure the node returns early
with status="invalid" so downstream nodes can short-circuit cleanly.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from ..domain.state import InvoiceData, InvoiceState

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "vendor", "siren", "date", "reference",
    "ht_amount", "tva_rate", "tva_amount", "ttc_amount",
})


def extractor_node(state: InvoiceState) -> dict:
    """Extract and type-coerce raw_input into a typed InvoiceData.

    Reads ``state["raw_input"]`` and attempts to build an InvoiceData
    value object. On any parsing failure the function returns early with
    ``status="invalid"`` — no exception is propagated to the graph.

    Args:
        state: Current InvoiceState.

    Returns:
        Partial state dict with keys: ``invoice``, ``status``, ``errors``.
        On success: ``invoice`` is populated, ``status="pending"``, ``errors=[]``.
        On failure: ``invoice=None``, ``status="invalid"``, ``errors=[reason]``.
    """
    raw = state["raw_input"]
    logger.debug("extractor_node: raw_input keys=%s", list(raw.keys()))

    missing = _REQUIRED_FIELDS - raw.keys()
    if missing:
        msg = f"Champs manquants: {sorted(missing)}"
        logger.warning("extractor_node: %s", msg)
        return {"invoice": None, "status": "invalid", "errors": [msg]}

    try:
        invoice_date = (
            raw["date"]
            if isinstance(raw["date"], date)
            else date.fromisoformat(str(raw["date"]))
        )
        invoice = InvoiceData(
            vendor=str(raw["vendor"]).strip(),
            siren=str(raw["siren"]).strip(),
            date=invoice_date,
            reference=str(raw["reference"]).strip(),
            ht_amount=Decimal(str(raw["ht_amount"])),
            tva_rate=Decimal(str(raw["tva_rate"])),
            tva_amount=Decimal(str(raw["tva_amount"])),
            ttc_amount=Decimal(str(raw["ttc_amount"])),
            currency=str(raw.get("currency", "EUR")).strip().upper(),
        )
    except (InvalidOperation, ValueError, KeyError) as exc:
        msg = f"Erreur d'extraction: {exc}"
        logger.error("extractor_node: %s", msg)
        return {"invoice": None, "status": "invalid", "errors": [msg]}

    logger.info(
        "extractor_node: ref=%s vendor=%s ttc=%.2f",
        invoice.reference, invoice.vendor, invoice.ttc_amount,
    )
    return {"invoice": invoice, "status": "pending", "errors": []}
