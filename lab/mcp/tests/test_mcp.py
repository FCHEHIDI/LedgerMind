"""Invariant 5 — MCP: test suite.

No live server process, no network, no model download.
All tests call tool functions directly or via MCPServer.handle() in-process.

Test groups:
  TestSchemas          ( 8 tests) — Pydantic schema validation
  TestExtractTool      ( 5 tests) — extract_invoice_text
  TestValidateTool     ( 5 tests) — validate_invoice_fields
  TestPostInvoiceTool  ( 4 tests) — post_invoice
  TestRAGTool          ( 4 tests) — rag_query_document (use_stub=True)
  TestLookupPCGTool    ( 4 tests) — lookup_pcg_account
  TestMCPServer        (10 tests) — JSON-RPC envelope, tools/list, tools/call
"""

from __future__ import annotations

import json

import pytest

from lab.mcp.schemas import (
    ExtractInvoiceInput,
    LookupPCGInput,
    MCPError,
    MCPRequest,
    MCPResponse,
    PostInvoiceInput,
    RAGQueryInput,
    ValidateInvoiceInput,
)
from lab.mcp.server import MCPServer
from lab.mcp.tools import (
    extract_invoice_text,
    lookup_pcg_account,
    post_invoice,
    rag_query_document,
    validate_invoice_fields,
)

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

VALID_RAW_FIELDS = {
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

INVALID_RAW_FIELDS = {
    "vendor": "ACME SAS",
    "siren": "123456789",
    "date": "2024-01-15",
    "reference": "FA-2024-001",
    "ht_amount": "1000.00",
    "tva_rate": "0.20",
    "tva_amount": "200.00",
    "ttc_amount": "999.00",   # TTC ≠ HT + TVA → invalid
    "currency": "EUR",
}


# ---------------------------------------------------------------------------
# TestSchemas
# ---------------------------------------------------------------------------


class TestSchemas:
    """Pydantic model validation at schema level."""

    def test_extract_input_rejects_empty_text(self) -> None:
        with pytest.raises(Exception):
            ExtractInvoiceInput(text="")

    def test_validate_input_accepts_dict(self) -> None:
        inp = ValidateInvoiceInput(raw_fields=VALID_RAW_FIELDS)
        assert inp.raw_fields["siren"] == "123456789"

    def test_post_input_accepts_dict(self) -> None:
        inp = PostInvoiceInput(raw_fields=VALID_RAW_FIELDS)
        assert inp.raw_fields["ht_amount"] == "1000.00"

    def test_rag_input_k_defaults_to_3(self) -> None:
        inp = RAGQueryInput(document="doc", question="q")
        assert inp.k == 3

    def test_rag_input_k_must_be_ge_1(self) -> None:
        with pytest.raises(Exception):
            RAGQueryInput(document="doc", question="q", k=0)

    def test_lookup_input_rejects_empty_code(self) -> None:
        with pytest.raises(Exception):
            LookupPCGInput(code="")

    def test_mcp_request_defaults_jsonrpc(self) -> None:
        req = MCPRequest(method="tools/list")
        assert req.jsonrpc == "2.0"

    def test_mcp_response_has_result(self) -> None:
        resp = MCPResponse(id=1, result={"ok": True})
        assert resp.result == {"ok": True}


# ---------------------------------------------------------------------------
# TestExtractTool
# ---------------------------------------------------------------------------


class TestExtractTool:
    """extract_invoice_text — regex extraction."""

    def test_extracts_siren_from_sample(self) -> None:
        out = extract_invoice_text(ExtractInvoiceInput(text=INVOICE_TEXT))
        assert out.siren == "123456789"

    def test_extracts_ttc_from_sample(self) -> None:
        out = extract_invoice_text(ExtractInvoiceInput(text=INVOICE_TEXT))
        assert out.ttc_amount == "1200.00"

    def test_extracts_ht_from_sample(self) -> None:
        out = extract_invoice_text(ExtractInvoiceInput(text=INVOICE_TEXT))
        assert out.ht_amount == "1000.00"

    def test_missing_fields_are_none(self) -> None:
        out = extract_invoice_text(ExtractInvoiceInput(text="aucun champ ici"))
        assert out.siren is None
        assert out.ttc_amount is None

    def test_returns_extract_invoice_output_type(self) -> None:
        from lab.mcp.schemas import ExtractInvoiceOutput
        out = extract_invoice_text(ExtractInvoiceInput(text=INVOICE_TEXT))
        assert isinstance(out, ExtractInvoiceOutput)


# ---------------------------------------------------------------------------
# TestValidateTool
# ---------------------------------------------------------------------------


class TestValidateTool:
    """validate_invoice_fields — business rules via invoice_graph."""

    def test_valid_fields_return_valid_or_posted_status(self) -> None:
        out = validate_invoice_fields(ValidateInvoiceInput(raw_fields=VALID_RAW_FIELDS))
        assert out.status in ("valid", "posted")

    def test_invalid_ttc_returns_invalid_status(self) -> None:
        out = validate_invoice_fields(ValidateInvoiceInput(raw_fields=INVALID_RAW_FIELDS))
        assert out.status in ("invalid", "rejected")

    def test_invalid_has_non_empty_errors(self) -> None:
        out = validate_invoice_fields(ValidateInvoiceInput(raw_fields=INVALID_RAW_FIELDS))
        assert len(out.errors) >= 1

    def test_valid_errors_list_is_empty(self) -> None:
        out = validate_invoice_fields(ValidateInvoiceInput(raw_fields=VALID_RAW_FIELDS))
        assert out.errors == []

    def test_missing_vendor_returns_invalid(self) -> None:
        fields = {**VALID_RAW_FIELDS}
        del fields["vendor"]
        out = validate_invoice_fields(ValidateInvoiceInput(raw_fields=fields))
        assert out.status in ("invalid", "rejected")


# ---------------------------------------------------------------------------
# TestPostInvoiceTool
# ---------------------------------------------------------------------------


class TestPostInvoiceTool:
    """post_invoice — full graph including accountant_node."""

    def test_valid_invoice_is_posted(self) -> None:
        out = post_invoice(PostInvoiceInput(raw_fields=VALID_RAW_FIELDS))
        assert out.status == "posted"

    def test_posted_invoice_has_journal_entry_id(self) -> None:
        out = post_invoice(PostInvoiceInput(raw_fields=VALID_RAW_FIELDS))
        assert out.journal_entry_id is not None

    def test_journal_entry_id_is_uuid_string(self) -> None:
        import re
        out = post_invoice(PostInvoiceInput(raw_fields=VALID_RAW_FIELDS))
        uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert uuid_re.match(out.journal_entry_id or ""), f"Not a UUID: {out.journal_entry_id}"

    def test_invalid_invoice_is_rejected(self) -> None:
        out = post_invoice(PostInvoiceInput(raw_fields=INVALID_RAW_FIELDS))
        assert out.status in ("invalid", "rejected")


# ---------------------------------------------------------------------------
# TestRAGTool
# ---------------------------------------------------------------------------


class TestRAGTool:
    """rag_query_document — pipeline with StubEmbedder."""

    def test_returns_rag_query_output(self) -> None:
        from lab.mcp.schemas import RAGQueryOutput
        out = rag_query_document(RAGQueryInput(document=INVOICE_TEXT, question="SIREN", k=2))
        assert isinstance(out, RAGQueryOutput)

    def test_context_is_non_empty_after_indexing(self) -> None:
        out = rag_query_document(RAGQueryInput(document=INVOICE_TEXT, question="Total TTC", k=2))
        assert len(out.context) > 0

    def test_chunks_found_le_k(self) -> None:
        out = rag_query_document(RAGQueryInput(document=INVOICE_TEXT, question="TVA", k=2))
        assert out.chunks_found <= 2

    def test_query_echoed_in_output(self) -> None:
        out = rag_query_document(RAGQueryInput(document=INVOICE_TEXT, question="montant HT", k=1))
        assert out.query == "montant HT"


# ---------------------------------------------------------------------------
# TestLookupPCGTool
# ---------------------------------------------------------------------------


class TestLookupPCGTool:
    """lookup_pcg_account — PCG resolution."""

    def test_known_code_returns_found(self) -> None:
        out = lookup_pcg_account(LookupPCGInput(code="607"))
        assert out.found is True

    def test_known_code_has_non_empty_label(self) -> None:
        out = lookup_pcg_account(LookupPCGInput(code="401"))
        assert len(out.label) > 0

    def test_unknown_code_returns_not_found(self) -> None:
        out = lookup_pcg_account(LookupPCGInput(code="99999"))
        assert out.found is False

    def test_unknown_code_echoes_input(self) -> None:
        out = lookup_pcg_account(LookupPCGInput(code="99999"))
        assert out.code == "99999"


# ---------------------------------------------------------------------------
# TestMCPServer
# ---------------------------------------------------------------------------


class TestMCPServer:
    """JSON-RPC 2.0 server — envelope validation and dispatch."""

    def _server(self) -> MCPServer:
        return MCPServer()

    def test_tools_list_returns_result(self) -> None:
        resp = self._server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert "result" in resp
        assert "error" not in resp

    def test_tools_list_contains_five_tools(self) -> None:
        resp = self._server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = resp["result"]["tools"]
        assert len(tools) == 5

    def test_tools_list_tool_has_name_and_schema(self) -> None:
        resp = self._server().handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        for tool in resp["result"]["tools"]:
            assert "name" in tool
            assert "input_schema" in tool

    def test_tools_call_extract_succeeds(self) -> None:
        resp = self._server().handle({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "extract_invoice_text", "arguments": {"text": INVOICE_TEXT}},
        })
        assert "result" in resp
        assert resp["result"]["siren"] == "123456789"

    def test_tools_call_lookup_known_account(self) -> None:
        resp = self._server().handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "lookup_pcg_account", "arguments": {"code": "607"}},
        })
        assert resp["result"]["found"] is True

    def test_tools_call_unknown_tool_returns_error(self) -> None:
        resp = self._server().handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_unknown_method_returns_method_not_found(self) -> None:
        resp = self._server().handle({
            "jsonrpc": "2.0", "id": 5, "method": "some/unknown", "params": {}
        })
        assert resp["error"]["code"] == -32601

    def test_invalid_params_returns_invalid_params_error(self) -> None:
        resp = self._server().handle({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "extract_invoice_text", "arguments": {}},  # missing 'text'
        })
        assert "error" in resp
        assert resp["error"]["code"] == -32602

    def test_handle_json_parses_and_responds(self) -> None:
        req = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {}})
        resp_str = self._server().handle_json(req)
        resp = json.loads(resp_str)
        assert "result" in resp

    def test_handle_json_invalid_json_returns_parse_error(self) -> None:
        resp_str = self._server().handle_json("{not valid json")
        resp = json.loads(resp_str)
        assert resp["error"]["code"] == -32700
