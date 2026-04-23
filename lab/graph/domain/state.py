"""Shared state types for the invoice processing graph.

The InvoiceState TypedDict is the "cartable" passed between every node.
LangGraph merges partial dict returns — nodes only return the keys they modify.

Reducer:
    errors uses ``operator.add`` so each node appends without overwriting.
    All other fields use last-write-wins (default LangGraph behaviour).
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, TypedDict


@dataclass(frozen=True)
class InvoiceData:
    """Structured invoice data extracted from raw input.

    Immutable value object produced by the extractor node and consumed
    by the validator and accountant nodes.

    Args:
        vendor: Supplier name (free text).
        siren: French company identifier (9 digits).
        date: Invoice date.
        reference: Invoice reference number (e.g. "FA-2024-001").
        ht_amount: Pre-tax amount (HT).
        tva_rate: VAT rate as a decimal (e.g. Decimal("0.20") for 20 %).
        tva_amount: VAT amount.
        ttc_amount: Total amount including VAT (TTC = HT + TVA).
        currency: ISO 4217 currency code (default "EUR").
    """

    vendor: str
    siren: str
    date: date
    reference: str
    ht_amount: Decimal
    tva_rate: Decimal
    tva_amount: Decimal
    ttc_amount: Decimal
    currency: str = "EUR"


class InvoiceState(TypedDict):
    """Shared state flowing through every node of the invoice graph.

    Attributes:
        raw_input: Raw dict from upstream (LLM/OCR parser, file reader, etc.).
        invoice: Structured invoice after extraction. None until extractor runs.
        errors: Accumulated validation errors. Append-only via ``operator.add``.
        status: Processing status — one of:
            "pending"  → extracted, not yet validated
            "valid"    → all business rules passed
            "invalid"  → extraction or validation failed
            "posted"   → journal entry created and posted
            "rejected" → rejected after validation failure
        journal_entry_id: UUID string of the posted JournalEntry. None until posted.
    """

    raw_input: dict
    invoice: InvoiceData | None
    errors: Annotated[list[str], operator.add]
    status: str
    journal_entry_id: str | None
