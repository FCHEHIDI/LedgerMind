"""Accountant node — builds and posts a JournalEntry from validated InvoiceData.

Responsibility: bridge between the graph layer and the ledger domain.
Only runs when status="valid".

Écriture générée (facture fournisseur TTC):

  D 607 — Achats marchandises    HT
  D 44566 — TVA déductible       TVA
    C 401 — Fournisseurs         TTC
"""

from __future__ import annotations

import logging
from datetime import date

from lab.ledger.domain.entry import JournalEntry, JournalLine
from lab.ledger.domain.money import Money
from lab.ledger.pcg.chart import get as pcg_get

from ..domain.state import InvoiceState

logger = logging.getLogger(__name__)


def accountant_node(state: InvoiceState) -> dict:
    """Create and post a double-entry JournalEntry for a supplier invoice.

    Builds the écriture:
        Débit  607  Achats marchandises  (HT)
        Débit  44566 TVA déductible      (TVA)
        Crédit 401  Fournisseurs         (TTC)

    Assumes ``state["status"] == "valid"`` and ``state["invoice"]`` is not None.
    On any ledger error, returns ``status="rejected"`` with the error message.

    Args:
        state: Current InvoiceState (must have status="valid").

    Returns:
        Partial state dict with ``status``, ``journal_entry_id``, and ``errors``.
    """
    invoice = state["invoice"]
    logger.info(
        "accountant_node: imputation facture ref=%s vendor=%s",
        invoice.reference, invoice.vendor,
    )

    try:
        currency = invoice.currency
        ht = Money.of(invoice.ht_amount, currency)
        tva = Money.of(invoice.tva_amount, currency)
        ttc = Money.of(invoice.ttc_amount, currency)

        account_charges = pcg_get("607")
        account_tva = pcg_get("44566")
        account_supplier = pcg_get("401")

        entry = JournalEntry(
            date=invoice.date,
            reference=invoice.reference,
            journal_code="AC",
            description=f"Facture {invoice.reference} — {invoice.vendor}",
        )

        entry.add_line(
            JournalLine.debit_line(account_charges, ht, "Achats marchandises HT")
        )

        # Only add TVA line when TVA > 0 (some invoices are TVA-exempt)
        if not tva.is_zero():
            entry.add_line(
                JournalLine.debit_line(account_tva, tva, "TVA déductible 20%")
            )

        entry.add_line(
            JournalLine.credit_line(account_supplier, ttc, f"Fournisseur {invoice.vendor}")
        )

        entry.post()

    except Exception as exc:
        msg = f"Erreur comptable: {exc}"
        logger.error("accountant_node: %s", msg)
        return {"status": "rejected", "errors": [msg], "journal_entry_id": None}

    logger.info(
        "accountant_node: écriture postée id=%s debit=%.2f credit=%.2f",
        entry.id, entry.total_debit, entry.total_credit,
    )
    return {
        "status": "posted",
        "journal_entry_id": str(entry.id),
        "errors": [],
    }
