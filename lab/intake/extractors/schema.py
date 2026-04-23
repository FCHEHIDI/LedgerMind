"""Pydantic schema for raw invoice data extracted from document text.

RawInvoice is the contract between the regex extractor and the pipeline.
It validates and coerces all fields before they are handed off to the
LangGraph invoice graph.

Design notes:
  - All monetary fields use Decimal (never float).
  - date is a Python date object after coercion from YYYYMMDD / DD/MM/YYYY.
  - tva_rate is optional — computed from tva_amount / ht_amount if absent.
  - Extra fields are forbidden (strict mode) to catch extractor bugs early.
"""

from __future__ import annotations

import re
from datetime import date as Date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class RawInvoice(BaseModel):
    """Validated raw invoice data extracted from document text.

    This model is the single source of truth for field shapes entering
    the LangGraph pipeline. Validation is strict — unknown fields are
    rejected to catch extractor drift early.

    Args:
        vendor: Supplier name (required, non-empty).
        siren: French 9-digit company identifier.
        date: Invoice date (parsed from multiple format variants).
        reference: Invoice reference / number.
        ht_amount: Pre-tax amount (must be > 0).
        tva_rate: VAT rate as a decimal fraction (0.20 for 20%).
                  Computed automatically when absent.
        tva_amount: VAT amount (must be >= 0).
        ttc_amount: Total including VAT (must be > 0).
        currency: ISO 4217 code, defaults to "EUR".

    Raises:
        ValidationError: On any field constraint violation.
    """

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    vendor: str = Field(..., min_length=1, description="Supplier name")
    siren: str = Field(..., description="9-digit SIREN")
    date: Date = Field(..., description="Invoice date")
    reference: str = Field(..., min_length=1, description="Invoice reference")
    ht_amount: Decimal = Field(..., gt=Decimal("0"), description="Pre-tax amount")
    tva_rate: Optional[Decimal] = Field(None, ge=Decimal("0"), description="VAT rate")
    tva_amount: Decimal = Field(..., ge=Decimal("0"), description="VAT amount")
    ttc_amount: Decimal = Field(..., gt=Decimal("0"), description="Total incl. VAT")
    currency: str = Field(default="EUR", description="ISO 4217 currency")

    @field_validator("siren")
    @classmethod
    def validate_siren(cls, v: str) -> str:
        """Ensure SIREN is exactly 9 digits."""
        cleaned = re.sub(r"\s", "", v)
        if not re.fullmatch(r"\d{9}", cleaned):
            raise ValueError(f"SIREN must be 9 digits, got: '{v}'")
        return cleaned

    @field_validator("currency")
    @classmethod
    def normalise_currency(cls, v: str) -> str:
        """Uppercase and validate currency length (ISO 4217 = 3 chars)."""
        upper = v.upper().strip()
        if len(upper) != 3:
            raise ValueError(f"Currency must be 3 chars (ISO 4217), got: '{v}'")
        return upper

    @model_validator(mode="after")
    def compute_tva_rate_if_absent(self) -> "RawInvoice":
        """Derive tva_rate from tva_amount / ht_amount when not provided."""
        if self.tva_rate is None:
            if self.ht_amount and self.ht_amount > 0:
                self.tva_rate = (self.tva_amount / self.ht_amount).quantize(
                    Decimal("0.0001")
                )
            else:
                self.tva_rate = Decimal("0")
        return self

    def to_graph_input(self) -> dict:
        """Serialise to the raw_input dict expected by the LangGraph pipeline.

        Returns:
            Dict with all fields as strings/date objects suitable for
            ``InvoiceState["raw_input"]``.
        """
        return {
            "vendor": self.vendor,
            "siren": self.siren,
            "date": self.date,
            "reference": self.reference,
            "ht_amount": str(self.ht_amount),
            "tva_rate": str(self.tva_rate),
            "tva_amount": str(self.tva_amount),
            "ttc_amount": str(self.ttc_amount),
            "currency": self.currency,
        }
