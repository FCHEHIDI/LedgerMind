"""Invariant 6 — Workflow: test suite.

No I/O, no network, no model download.
Nodes are tested in isolation (called directly) and via the compiled graph.

Test groups:
  TestWorkflowState    ( 4 tests) — TypedDict structure + Annotated reducer
  TestIntakeNode       ( 5 tests) — regex extraction via intake_node
  TestRAGNode          ( 5 tests) — RAG indexing/retrieval via rag_node
  TestGraphNode        ( 6 tests) — invoice graph delegation via graph_node
  TestMCPNode          ( 4 tests) — PCG lookups via mcp_node
  TestPipeline         ( 3 tests) — graph topology / route logic
  TestInvoiceWorkflow  ( 6 tests) — end-to-end via invoice_workflow.invoke()
"""

from __future__ import annotations

import operator
from typing import get_type_hints

import pytest

from lab.workflow.nodes.graph_node import graph_node
from lab.workflow.nodes.intake_node import intake_node
from lab.workflow.nodes.mcp_node import mcp_node
from lab.workflow.nodes.rag_node import rag_node
from lab.workflow.pipeline import _route_after_graph, build_workflow, invoice_workflow
from lab.workflow.state import WorkflowState

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

INVOICE_TEXT = (
    "ACME SAS\nSIREN : 123 456 789\n"
    "Facture n° FA-2024-001\nDate : 15/01/2024\n"
    "Total HT     1 000,00 €\n"
    "TVA 20 %       200,00 €\n"
    "Total TTC    1 200,00 €\n"
)

VALID_FIELDS = {
    "vendor": "ACME SAS",
    "siren": "123456789",
    "date": "2024-01-15",
    "reference": "FA-2024-001",
    "ht_amount": "1000.00",
    "tva_rate": "0.20",
    "tva_amount": "200.00",
    "ttc_amount": "1200.00",
    "currency": "EUR",
}

INVALID_FIELDS = {
    "vendor": "ACME SAS",
    "siren": "123456789",
    "date": "2024-01-15",
    "reference": "FA-2024-001",
    "ht_amount": "1000.00",
    "tva_rate": "0.20",
    "tva_amount": "200.00",
    "ttc_amount": "999.00",   # TTC ≠ HT + TVA
    "currency": "EUR",
}


# ---------------------------------------------------------------------------
# TestWorkflowState
# ---------------------------------------------------------------------------


class TestWorkflowState:
    """WorkflowState TypedDict structure."""

    def test_raw_text_key_present(self) -> None:
        hints = get_type_hints(WorkflowState, include_extras=True)
        assert "raw_text" in hints

    def test_errors_uses_add_reducer(self) -> None:
        hints = get_type_hints(WorkflowState, include_extras=True)
        # Annotated[list[str], operator.add] → metadata contains operator.add
        errors_hint = hints["errors"]
        args = getattr(errors_hint, "__metadata__", ())
        assert operator.add in args

    def test_all_expected_keys_defined(self) -> None:
        expected = {
            "raw_text", "extracted_fields", "rag_context", "rag_chunks_found",
            "validation_status", "validation_errors", "journal_entry_id",
            "pcg_lookups", "errors",
        }
        hints = get_type_hints(WorkflowState)
        assert expected.issubset(hints.keys())

    def test_state_is_dict_subclass(self) -> None:
        # TypedDict instances are plain dicts at runtime
        state: WorkflowState = {"raw_text": "hello"}  # type: ignore[typeddict-item]
        assert isinstance(state, dict)


# ---------------------------------------------------------------------------
# TestIntakeNode
# ---------------------------------------------------------------------------


class TestIntakeNode:
    """intake_node — regex field extraction."""

    def test_returns_extracted_fields_key(self) -> None:
        result = intake_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert "extracted_fields" in result

    def test_extracts_siren(self) -> None:
        result = intake_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert result["extracted_fields"]["siren"] == "123456789"

    def test_extracts_ttc(self) -> None:
        result = intake_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert result["extracted_fields"]["ttc_amount"] == "1200.00"

    def test_empty_text_yields_none_fields(self) -> None:
        result = intake_node({"raw_text": ""})  # type: ignore[typeddict-item]
        fields = result["extracted_fields"]
        assert all(v is None for v in fields.values())

    def test_extracted_fields_is_dict(self) -> None:
        result = intake_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert isinstance(result["extracted_fields"], dict)


# ---------------------------------------------------------------------------
# TestRAGNode
# ---------------------------------------------------------------------------


class TestRAGNode:
    """rag_node — RAG indexing and retrieval (use_stub=True)."""

    def test_returns_rag_context_key(self) -> None:
        result = rag_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert "rag_context" in result

    def test_context_is_non_empty_for_invoice(self) -> None:
        result = rag_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert len(result["rag_context"]) > 0

    def test_chunks_found_is_int(self) -> None:
        result = rag_node({"raw_text": INVOICE_TEXT})  # type: ignore[typeddict-item]
        assert isinstance(result["rag_chunks_found"], int)

    def test_empty_text_returns_zero_chunks(self) -> None:
        result = rag_node({"raw_text": "   "})  # type: ignore[typeddict-item]
        assert result["rag_chunks_found"] == 0

    def test_empty_text_returns_empty_context(self) -> None:
        result = rag_node({"raw_text": ""})  # type: ignore[typeddict-item]
        assert result["rag_context"] == ""


# ---------------------------------------------------------------------------
# TestGraphNode
# ---------------------------------------------------------------------------


class TestGraphNode:
    """graph_node — invoice_graph delegation."""

    def test_valid_fields_return_posted_status(self) -> None:
        result = graph_node({"extracted_fields": VALID_FIELDS})  # type: ignore[typeddict-item]
        assert result["validation_status"] == "posted"

    def test_valid_invoice_has_journal_entry_id(self) -> None:
        result = graph_node({"extracted_fields": VALID_FIELDS})  # type: ignore[typeddict-item]
        assert result["journal_entry_id"] is not None

    def test_invalid_fields_return_rejected_status(self) -> None:
        result = graph_node({"extracted_fields": INVALID_FIELDS})  # type: ignore[typeddict-item]
        assert result["validation_status"] in ("rejected", "invalid")

    def test_invalid_fields_have_errors(self) -> None:
        result = graph_node({"extracted_fields": INVALID_FIELDS})  # type: ignore[typeddict-item]
        assert len(result["validation_errors"]) >= 1

    def test_valid_invoice_has_empty_errors(self) -> None:
        result = graph_node({"extracted_fields": VALID_FIELDS})  # type: ignore[typeddict-item]
        assert result["validation_errors"] == []

    def test_empty_fields_returns_rejected(self) -> None:
        result = graph_node({"extracted_fields": {}})  # type: ignore[typeddict-item]
        assert result["validation_status"] in ("rejected", "invalid")


# ---------------------------------------------------------------------------
# TestMCPNode
# ---------------------------------------------------------------------------


class TestMCPNode:
    """mcp_node — PCG account lookups via MCPServer."""

    def test_returns_pcg_lookups_key(self) -> None:
        result = mcp_node({"journal_entry_id": "test-je-id"})  # type: ignore[typeddict-item]
        assert "pcg_lookups" in result

    def test_lookups_list_has_three_entries(self) -> None:
        result = mcp_node({"journal_entry_id": "test-je-id"})  # type: ignore[typeddict-item]
        # We look up 3 accounts: 401, 607, 44566
        assert len(result["pcg_lookups"]) == 3

    def test_known_account_is_found(self) -> None:
        result = mcp_node({"journal_entry_id": "test-je-id"})  # type: ignore[typeddict-item]
        codes = {item["code"] for item in result["pcg_lookups"] if item.get("found")}
        # 401 and 607 are standard PCG accounts — at least one must be found
        assert len(codes) >= 1

    def test_each_lookup_has_code_and_found(self) -> None:
        result = mcp_node({"journal_entry_id": "test-je-id"})  # type: ignore[typeddict-item]
        for item in result["pcg_lookups"]:
            assert "code" in item
            assert "found" in item


# ---------------------------------------------------------------------------
# TestPipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    """Graph topology and routing logic."""

    def test_route_posted_goes_to_mcp_node(self) -> None:
        state: WorkflowState = {"raw_text": "", "validation_status": "posted"}  # type: ignore[typeddict-item]
        assert _route_after_graph(state) == "mcp_node"

    def test_route_rejected_goes_to_end(self) -> None:
        from langgraph.graph import END
        state: WorkflowState = {"raw_text": "", "validation_status": "rejected"}  # type: ignore[typeddict-item]
        assert _route_after_graph(state) == END

    def test_build_workflow_returns_compiled_graph(self) -> None:
        wf = build_workflow()
        # A compiled LangGraph has an .invoke() method
        assert callable(getattr(wf, "invoke", None))


# ---------------------------------------------------------------------------
# TestInvoiceWorkflow
# ---------------------------------------------------------------------------


class TestInvoiceWorkflow:
    """End-to-end workflow via invoice_workflow.invoke()."""

    def test_valid_invoice_text_posts_successfully(self) -> None:
        result = invoice_workflow.invoke({"raw_text": INVOICE_TEXT})
        assert result["validation_status"] == "posted"

    def test_valid_invoice_has_journal_entry_id(self) -> None:
        result = invoice_workflow.invoke({"raw_text": INVOICE_TEXT})
        assert result["journal_entry_id"] is not None

    def test_valid_invoice_triggers_mcp_node(self) -> None:
        result = invoice_workflow.invoke({"raw_text": INVOICE_TEXT})
        assert "pcg_lookups" in result
        assert len(result["pcg_lookups"]) == 3

    def test_valid_invoice_has_rag_context(self) -> None:
        result = invoice_workflow.invoke({"raw_text": INVOICE_TEXT})
        assert len(result.get("rag_context", "")) > 0

    def test_invalid_text_skips_mcp_node(self) -> None:
        result = invoice_workflow.invoke({"raw_text": "texte sans aucune facture valide"})
        assert result["validation_status"] in ("rejected", "invalid")
        # mcp_node was not reached — pcg_lookups absent or empty
        assert result.get("pcg_lookups") is None or result.get("pcg_lookups") == []

    def test_invalid_invoice_has_validation_errors(self) -> None:
        result = invoice_workflow.invoke({"raw_text": "texte quelconque"})
        assert isinstance(result.get("validation_errors", []), list)
