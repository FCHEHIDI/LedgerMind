"""Invariant 2 — Graph: test suite.

Tests are organized by invariant, from unit (node level) to integration
(full graph traversal). No mocking — every test exercises real code paths.

Test groups:
  TestExtractorNode    (6 tests) — extraction + type coercion
  TestValidatorNode    (8 tests) — business rule enforcement
  TestAccountantNode   (4 tests) — journal entry creation
  TestRejectorNode     (2 tests) — terminal rejection
  TestGraphRouting     (4 tests) — conditional edge + end-to-end traversal
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from lab.graph.domain.state import InvoiceData, InvoiceState
from lab.graph.nodes.accountant import accountant_node
from lab.graph.nodes.extractor import extractor_node
from lab.graph.nodes.rejector import rejector_node
from lab.graph.nodes.validator import validator_node
from lab.graph.graph import invoice_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_raw() -> dict:
    """Return a minimal valid raw_input dict."""
    return {
        "vendor": "ACME SAS",
        "siren": "123456789",
        "date": "2024-01-15",
        "reference": "FA-2024-001",
        "ht_amount": "1000.00",
        "tva_rate": "0.20",
        "tva_amount": "200.00",
        "ttc_amount": "1200.00",
    }


def _base_state(**overrides) -> InvoiceState:
    """Return a base InvoiceState with sensible defaults."""
    state: InvoiceState = {
        "raw_input": _base_raw(),
        "invoice": None,
        "errors": [],
        "status": "pending",
        "journal_entry_id": None,
    }
    state.update(overrides)
    return state


def _valid_invoice() -> InvoiceData:
    """Return a pre-built valid InvoiceData."""
    return InvoiceData(
        vendor="ACME SAS",
        siren="123456789",
        date=date(2024, 1, 15),
        reference="FA-2024-001",
        ht_amount=Decimal("1000.00"),
        tva_rate=Decimal("0.20"),
        tva_amount=Decimal("200.00"),
        ttc_amount=Decimal("1200.00"),
    )


# ---------------------------------------------------------------------------
# TestExtractorNode
# ---------------------------------------------------------------------------

class TestExtractorNode:
    def test_valid_raw_produces_invoice(self):
        result = extractor_node(_base_state())
        assert result["status"] == "pending"
        assert result["invoice"] is not None
        assert result["invoice"].vendor == "ACME SAS"

    def test_decimal_coercion_from_string(self):
        result = extractor_node(_base_state())
        assert isinstance(result["invoice"].ht_amount, Decimal)
        assert result["invoice"].ht_amount == Decimal("1000.00")

    def test_date_coercion_from_iso_string(self):
        result = extractor_node(_base_state())
        assert result["invoice"].date == date(2024, 1, 15)

    def test_date_object_passes_through(self):
        raw = _base_raw()
        raw["date"] = date(2024, 3, 1)
        result = extractor_node(_base_state(raw_input=raw))
        assert result["invoice"].date == date(2024, 3, 1)

    def test_missing_field_returns_invalid(self):
        raw = _base_raw()
        del raw["siren"]
        result = extractor_node(_base_state(raw_input=raw))
        assert result["status"] == "invalid"
        assert result["invoice"] is None
        assert any("siren" in e for e in result["errors"])

    def test_invalid_decimal_returns_invalid(self):
        raw = _base_raw()
        raw["ht_amount"] = "not_a_number"
        result = extractor_node(_base_state(raw_input=raw))
        assert result["status"] == "invalid"
        assert result["invoice"] is None

    def test_currency_defaults_to_eur(self):
        result = extractor_node(_base_state())
        assert result["invoice"].currency == "EUR"

    def test_explicit_currency_is_preserved(self):
        raw = _base_raw()
        raw["currency"] = "usd"
        result = extractor_node(_base_state(raw_input=raw))
        assert result["invoice"].currency == "USD"


# ---------------------------------------------------------------------------
# TestValidatorNode
# ---------------------------------------------------------------------------

class TestValidatorNode:
    def test_valid_invoice_passes(self):
        state = _base_state(invoice=_valid_invoice(), status="pending")
        result = validator_node(state)
        assert result["status"] == "valid"
        assert result["errors"] == []

    def test_already_invalid_is_skipped(self):
        state = _base_state(status="invalid", errors=["extraction failed"])
        result = validator_node(state)
        # returns empty dict — no state mutation
        assert result == {}

    def test_negative_ht_rejected(self):
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1", ht_amount=Decimal("-100"), tva_rate=Decimal("0.20"),
            tva_amount=Decimal("0"), ttc_amount=Decimal("-100"),
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "invalid"
        assert any("HT" in e for e in result["errors"])

    def test_zero_ht_rejected(self):
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1", ht_amount=Decimal("0"), tva_rate=Decimal("0"),
            tva_amount=Decimal("0"), ttc_amount=Decimal("0"),
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "invalid"

    def test_ttc_incoherence_rejected(self):
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1", ht_amount=Decimal("1000"), tva_rate=Decimal("0.20"),
            tva_amount=Decimal("200"), ttc_amount=Decimal("999"),  # wrong
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "invalid"
        assert any("TTC" in e for e in result["errors"])

    def test_tva_incoherence_rejected(self):
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1", ht_amount=Decimal("1000"), tva_rate=Decimal("0.20"),
            tva_amount=Decimal("100"),  # should be 200
            ttc_amount=Decimal("1100"),
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "invalid"

    def test_invalid_siren_rejected(self):
        inv = InvoiceData(
            vendor="X", siren="12345",  # too short
            date=date(2024, 1, 1), reference="R1",
            ht_amount=Decimal("1000"), tva_rate=Decimal("0.20"),
            tva_amount=Decimal("200"), ttc_amount=Decimal("1200"),
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "invalid"
        assert any("SIREN" in e for e in result["errors"])

    def test_tva_exempt_invoice_passes(self):
        """Invoices with 0% TVA should be valid (e.g. exports, micro-entreprise)."""
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1", ht_amount=Decimal("1000"), tva_rate=Decimal("0"),
            tva_amount=Decimal("0"), ttc_amount=Decimal("1000"),
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "valid"

    def test_multiple_violations_all_reported(self):
        inv = InvoiceData(
            vendor="X", siren="BAD",
            date=date(2024, 1, 1), reference="R1",
            ht_amount=Decimal("-1"), tva_rate=Decimal("0.20"),
            tva_amount=Decimal("-1"), ttc_amount=Decimal("-1"),
        )
        result = validator_node(_base_state(invoice=inv, status="pending"))
        assert result["status"] == "invalid"
        assert len(result["errors"]) >= 2


# ---------------------------------------------------------------------------
# TestAccountantNode
# ---------------------------------------------------------------------------

class TestAccountantNode:
    def test_valid_invoice_creates_posted_entry(self):
        state = _base_state(invoice=_valid_invoice(), status="valid")
        result = accountant_node(state)
        assert result["status"] == "posted"
        assert result["journal_entry_id"] is not None
        # Must be a valid UUID
        uuid.UUID(result["journal_entry_id"])

    def test_tva_exempt_invoice_no_tva_line(self):
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1", ht_amount=Decimal("1000"), tva_rate=Decimal("0"),
            tva_amount=Decimal("0"), ttc_amount=Decimal("1000"),
        )
        result = accountant_node(_base_state(invoice=inv, status="valid"))
        assert result["status"] == "posted"

    def test_errors_list_empty_on_success(self):
        state = _base_state(invoice=_valid_invoice(), status="valid")
        result = accountant_node(state)
        assert result["errors"] == []

    def test_imbalanced_amounts_produce_rejected_status(self):
        """Force an imbalance: ttc ≠ ht + tva so posting raises."""
        inv = InvoiceData(
            vendor="X", siren="123456789", date=date(2024, 1, 1),
            reference="R1",
            ht_amount=Decimal("1000"), tva_rate=Decimal("0.20"),
            tva_amount=Decimal("200"),
            ttc_amount=Decimal("1199"),  # wrong on purpose
        )
        result = accountant_node(_base_state(invoice=inv, status="valid"))
        assert result["status"] == "rejected"
        assert result["journal_entry_id"] is None


# ---------------------------------------------------------------------------
# TestRejectorNode
# ---------------------------------------------------------------------------

class TestRejectorNode:
    def test_rejector_sets_status_rejected(self):
        state = _base_state(status="invalid", errors=["champ manquant"])
        result = rejector_node(state)
        assert result["status"] == "rejected"

    def test_rejector_handles_no_invoice(self):
        state = _base_state(invoice=None, status="invalid", errors=["parse error"])
        result = rejector_node(state)
        assert result["status"] == "rejected"


# ---------------------------------------------------------------------------
# TestGraphRouting
# ---------------------------------------------------------------------------

class TestGraphRouting:
    def _invoke(self, raw_overrides: dict | None = None) -> InvoiceState:
        raw = _base_raw()
        if raw_overrides:
            raw.update(raw_overrides)
        return invoice_graph.invoke({
            "raw_input": raw,
            "invoice": None,
            "errors": [],
            "status": "pending",
            "journal_entry_id": None,
        })

    def test_happy_path_reaches_posted(self):
        result = self._invoke()
        assert result["status"] == "posted"
        assert result["journal_entry_id"] is not None

    def test_missing_field_reaches_rejected(self):
        result = self._invoke({"siren": None})  # will fail extraction
        assert result["status"] == "rejected"

    def test_invalid_amounts_reach_rejected(self):
        result = self._invoke({"ht_amount": "-500", "ttc_amount": "-500"})
        assert result["status"] == "rejected"

    def test_errors_accumulate_correctly(self):
        result = self._invoke({"siren": "BAD", "ht_amount": "-1", "ttc_amount": "-1"})
        assert result["status"] == "rejected"
        # validator should have produced at least 2 errors
        assert len(result["errors"]) >= 2
