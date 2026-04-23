"""Invariant 5 — MCP: Pydantic input/output schemas for every MCP tool.

Each tool has a paired ``*Input`` / ``*Output`` model so that:
* The JSON-RPC server can validate incoming ``arguments`` before dispatch.
* Tests can assert on structured outputs rather than raw dicts.
* The tool descriptor (``tools/list``) can auto-generate JSON Schema from
  the ``*Input`` model.

All models use ``model_config = {"extra": "forbid"}`` to surface unexpected
fields immediately.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tool 1 — extract_invoice_text
# ---------------------------------------------------------------------------


class ExtractInvoiceInput(BaseModel):
    """Input for the ``extract_invoice_text`` tool."""

    model_config = {"extra": "forbid"}

    text: str = Field(..., min_length=1, description="Raw invoice text to extract fields from.")


class ExtractInvoiceOutput(BaseModel):
    """Output of ``extract_invoice_text``."""

    model_config = {"extra": "allow"}

    vendor: Optional[str] = None
    siren: Optional[str] = None
    date: Optional[str] = None
    reference: Optional[str] = None
    ht_amount: Optional[str] = None
    tva_rate: Optional[str] = None
    tva_amount: Optional[str] = None
    ttc_amount: Optional[str] = None
    currency: Optional[str] = None


# ---------------------------------------------------------------------------
# Tool 2 — validate_invoice_fields
# ---------------------------------------------------------------------------


class ValidateInvoiceInput(BaseModel):
    """Input for ``validate_invoice_fields``.

    ``raw_fields`` is a dict that mirrors ``InvoiceState["raw_input"]``.
    It must include at minimum: vendor, siren, date, reference, ht_amount,
    tva_amount, ttc_amount.
    """

    model_config = {"extra": "forbid"}

    raw_fields: dict[str, Any] = Field(
        ..., description="Extracted invoice fields as returned by extract_invoice_text."
    )


class ValidateInvoiceOutput(BaseModel):
    """Output of ``validate_invoice_fields``."""

    model_config = {"extra": "forbid"}

    status: str = Field(..., description="'valid', 'invalid', 'posted', or 'rejected'.")
    errors: list[str] = Field(default_factory=list)
    journal_entry_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Tool 3 — post_invoice
# ---------------------------------------------------------------------------


class PostInvoiceInput(BaseModel):
    """Input for ``post_invoice``.

    Runs the full invoice_graph (extract → validate → post to ledger).
    ``raw_fields`` should be the output of ``extract_invoice_text``.
    """

    model_config = {"extra": "forbid"}

    raw_fields: dict[str, Any] = Field(..., description="Invoice fields dict.")


class PostInvoiceOutput(BaseModel):
    """Output of ``post_invoice``."""

    model_config = {"extra": "forbid"}

    status: str
    journal_entry_id: Optional[str] = None
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool 4 — rag_query_document
# ---------------------------------------------------------------------------


class RAGQueryInput(BaseModel):
    """Input for ``rag_query_document``."""

    model_config = {"extra": "forbid"}

    document: str = Field(..., min_length=1, description="Document text to index and query.")
    question: str = Field(..., min_length=1, description="Natural-language question.")
    k: int = Field(default=3, ge=1, le=20, description="Number of chunks to retrieve.")


class RAGQueryOutput(BaseModel):
    """Output of ``rag_query_document``."""

    model_config = {"extra": "forbid"}

    context: str = Field(..., description="Concatenated relevant chunk texts.")
    chunks_found: int
    query: str


# ---------------------------------------------------------------------------
# Tool 5 — lookup_pcg_account
# ---------------------------------------------------------------------------


class LookupPCGInput(BaseModel):
    """Input for ``lookup_pcg_account``."""

    model_config = {"extra": "forbid"}

    code: str = Field(..., min_length=1, description="PCG account code, e.g. '607' or '44566'.")


class LookupPCGOutput(BaseModel):
    """Output of ``lookup_pcg_account``."""

    model_config = {"extra": "forbid"}

    code: str
    label: str
    found: bool


# ---------------------------------------------------------------------------
# MCP protocol envelopes (JSON-RPC 2.0)
# ---------------------------------------------------------------------------


class ToolDescriptor(BaseModel):
    """Describes a single MCP tool as returned by ``tools/list``."""

    model_config = {"extra": "forbid"}

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPRequest(BaseModel):
    """Incoming JSON-RPC 2.0 request."""

    model_config = {"extra": "allow"}

    jsonrpc: str = "2.0"
    id: Any = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class MCPResponse(BaseModel):
    """Outgoing JSON-RPC 2.0 response (success)."""

    model_config = {"extra": "forbid"}

    jsonrpc: str = "2.0"
    id: Any
    result: Any


class MCPError(BaseModel):
    """Outgoing JSON-RPC 2.0 error response."""

    model_config = {"extra": "forbid"}

    jsonrpc: str = "2.0"
    id: Any
    error: dict[str, Any]
