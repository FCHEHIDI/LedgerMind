"""Validator node — enforces business invariants on InvoiceData.

Responsibility: pure business rules, no I/O, no side effects.
Short-circuits immediately if the extractor already marked the state invalid.

Rules enforced:
  1. ht_amount > 0
  2. tva_amount >= 0
  3. ttc_amount > 0
  4. ttc = ht + tva  (tolerance 2 centimes for rounding)
  5. tva = ht × tva_rate  (tolerance 2 centimes)
  6. siren: exactly 9 digits
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from ..domain.state import InvoiceState

logger = logging.getLogger(__name__)

_SIREN_RE = re.compile(r"^\d{9}$")
_TVA_TOLERANCE = Decimal("0.02")  # 2 centimes — covers standard rounding


def validator_node(state: InvoiceState) -> dict:
    """Validate business rules on the extracted InvoiceData.

    Short-circuits (returns empty dict) when the extractor has already
    set ``status="invalid"``, preserving its error messages unmodified.

    Args:
        state: Current InvoiceState.

    Returns:
        Partial state dict with ``status`` and ``errors``.
        On success: ``{"status": "valid", "errors": []}``.
        On failure: ``{"status": "invalid", "errors": [list of violations]}``.
        When short-circuiting: ``{}`` (no state change).
    """
    # Short-circuit: extractor already failed
    if state.get("status") == "invalid":
        logger.debug("validator_node: skipping — extractor already failed")
        return {}

    invoice = state.get("invoice")
    if invoice is None:
        return {"status": "invalid", "errors": ["Aucune facture extraite"]}

    errors: list[str] = []

    # Rule 1 — positive HT
    if invoice.ht_amount <= Decimal("0"):
        errors.append(f"Montant HT invalide: {invoice.ht_amount}")

    # Rule 2 — non-negative TVA
    if invoice.tva_amount < Decimal("0"):
        errors.append(f"Montant TVA invalide: {invoice.tva_amount}")

    # Rule 3 — positive TTC
    if invoice.ttc_amount <= Decimal("0"):
        errors.append(f"Montant TTC invalide: {invoice.ttc_amount}")

    # Rule 4 — TTC = HT + TVA
    expected_ttc = invoice.ht_amount + invoice.tva_amount
    if abs(invoice.ttc_amount - expected_ttc) > _TVA_TOLERANCE:
        errors.append(
            f"TTC incohérent: {invoice.ttc_amount} ≠ "
            f"HT({invoice.ht_amount}) + TVA({invoice.tva_amount})"
        )

    # Rule 5 — TVA = HT × taux
    if invoice.tva_rate >= Decimal("0"):
        expected_tva = (invoice.ht_amount * invoice.tva_rate).quantize(Decimal("0.01"))
        if abs(invoice.tva_amount - expected_tva) > _TVA_TOLERANCE:
            errors.append(
                f"TVA incohérente: {invoice.tva_amount} ≠ "
                f"{invoice.ht_amount} × {invoice.tva_rate}"
            )

    # Rule 6 — SIREN format
    if not _SIREN_RE.match(invoice.siren):
        errors.append(f"SIREN invalide: '{invoice.siren}' (9 chiffres requis)")

    if errors:
        logger.warning(
            "validator_node: ref=%s — %d violation(s): %s",
            invoice.reference, len(errors), errors,
        )
        return {"status": "invalid", "errors": errors}

    logger.info("validator_node: ref=%s validée", invoice.reference)
    return {"status": "valid", "errors": []}
