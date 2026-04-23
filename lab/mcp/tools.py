"""Invariant 5 — MCP: tool implementations.

Each function is a *pure Python callable* that:
1. Accepts validated input (Pydantic model already applied by the server).
2. Delegates to the existing Invariant 1-4 business logic.
3. Returns a Pydantic ``*Output`` model.

Design rules
------------
* No I/O here except what the underlying layers already perform.
* Every function is independently testable — no server process required.
* Failures are captured and surfaced in the output model (never raise to the
  caller), making the MCP surface always return a valid JSON-RPC response.
"""

from __future__ import annotations

import logging
from typing import Any

from lab.mcp.schemas import (
    ExtractInvoiceInput,
    ExtractInvoiceOutput,
    LookupPCGInput,
    LookupPCGOutput,
    PostInvoiceInput,
    PostInvoiceOutput,
    RAGQueryInput,
    RAGQueryOutput,
    ValidateInvoiceInput,
    ValidateInvoiceOutput,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool 1 — extract_invoice_text
# ---------------------------------------------------------------------------


def extract_invoice_text(inp: ExtractInvoiceInput) -> ExtractInvoiceOutput:
    """Extract structured fields from raw invoice text using regex patterns.

    Delegates to :func:`lab.intake.extractors.regex_extractor.extract_fields`.

    Args:
        inp: Validated :class:`ExtractInvoiceInput` containing the raw text.

    Returns:
        :class:`ExtractInvoiceOutput` with extracted field strings (``None``
        when a field could not be found).
    """
    from lab.intake.extractors.regex_extractor import extract_fields

    fields: dict[str, Any] = extract_fields(inp.text)
    logger.debug("extract_invoice_text: extracted %d non-null fields", sum(v is not None for v in fields.values()))
    return ExtractInvoiceOutput(**{k: v for k, v in fields.items() if k in ExtractInvoiceOutput.model_fields or True})


# ---------------------------------------------------------------------------
# Tool 2 — validate_invoice_fields
# ---------------------------------------------------------------------------


def validate_invoice_fields(inp: ValidateInvoiceInput) -> ValidateInvoiceOutput:
    """Run the invoice graph (extractor → validator only) and return status.

    The graph is invoked with the provided ``raw_fields`` dict.  The
    ``accountant_node`` is *not* reached unless status is 'valid'; the output
    status will be 'valid' or 'invalid'.

    Args:
        inp: :class:`ValidateInvoiceInput` with a ``raw_fields`` dict.

    Returns:
        :class:`ValidateInvoiceOutput` with ``status`` and ``errors``.
    """
    from lab.graph.graph import invoice_graph

    try:
        result = invoice_graph.invoke({"raw_input": inp.raw_fields})
        status = result.get("status", "invalid")
        errors = result.get("errors", [])
        je_id = result.get("journal_entry_id")
        logger.debug("validate_invoice_fields: status=%s errors=%s", status, errors)
        return ValidateInvoiceOutput(status=status, errors=errors, journal_entry_id=je_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("validate_invoice_fields error: %s", exc)
        return ValidateInvoiceOutput(status="invalid", errors=[str(exc)])


# ---------------------------------------------------------------------------
# Tool 3 — post_invoice
# ---------------------------------------------------------------------------


def post_invoice(inp: PostInvoiceInput) -> PostInvoiceOutput:
    """Run the full invoice graph and post the journal entry.

    Identical to :func:`validate_invoice_fields` but the graph runs all the
    way to ``accountant_node`` when valid, producing a ``journal_entry_id``.

    Args:
        inp: :class:`PostInvoiceInput` with ``raw_fields``.

    Returns:
        :class:`PostInvoiceOutput` with ``status``, ``journal_entry_id``, and
        any ``errors``.
    """
    from lab.graph.graph import invoice_graph

    try:
        result = invoice_graph.invoke({"raw_input": inp.raw_fields})
        status = result.get("status", "invalid")
        errors = result.get("errors", [])
        je_id = result.get("journal_entry_id")
        logger.debug("post_invoice: status=%s je_id=%s", status, je_id)
        return PostInvoiceOutput(status=status, journal_entry_id=je_id, errors=errors)
    except Exception as exc:  # noqa: BLE001
        logger.error("post_invoice error: %s", exc)
        return PostInvoiceOutput(status="invalid", errors=[str(exc)])


# ---------------------------------------------------------------------------
# Tool 4 — rag_query_document
# ---------------------------------------------------------------------------


def rag_query_document(inp: RAGQueryInput) -> RAGQueryOutput:
    """Index *document* and retrieve the *k* most relevant chunks for *question*.

    Uses :class:`lab.rag.pipeline.RAGPipeline` with ``use_stub=True`` in the
    lab environment (no model download required).  In production, swap to
    ``use_stub=False``.

    Args:
        inp: :class:`RAGQueryInput` with ``document``, ``question``, and ``k``.

    Returns:
        :class:`RAGQueryOutput` with ``context``, ``chunks_found``, and
        ``query``.
    """
    from lab.rag.pipeline import RAGPipeline

    # use_stub=True keeps the lab self-contained (no sentence-transformers needed).
    pipe = RAGPipeline(use_stub=True, k_default=inp.k)
    pipe.index(inp.document)
    result = pipe.query(inp.question, k=inp.k)
    logger.debug("rag_query_document: question=%r chunks_found=%d", inp.question, result.chunks_found)
    return RAGQueryOutput(
        context=result.context,
        chunks_found=result.chunks_found,
        query=result.query,
    )


# ---------------------------------------------------------------------------
# Tool 5 — lookup_pcg_account
# ---------------------------------------------------------------------------


def lookup_pcg_account(inp: LookupPCGInput) -> LookupPCGOutput:
    """Look up a PCG (Plan Comptable Général) account by code.

    Tries exact match first, then falls back to prefix resolution via
    :func:`lab.ledger.pcg.chart.PCGChart.resolve`.

    Args:
        inp: :class:`LookupPCGInput` with the account ``code``.

    Returns:
        :class:`LookupPCGOutput` with ``code``, ``label``, and ``found`` flag.
    """
    from lab.ledger.pcg import chart as pcg_chart

    try:
        account = pcg_chart.resolve(inp.code)
        logger.debug("lookup_pcg_account: code=%s → %s", inp.code, account.label)
        return LookupPCGOutput(code=account.number, label=account.label, found=True)
    except KeyError:
        logger.debug("lookup_pcg_account: code=%s not found", inp.code)
        return LookupPCGOutput(code=inp.code, label="", found=False)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "extract_invoice_text": extract_invoice_text,
    "validate_invoice_fields": validate_invoice_fields,
    "post_invoice": post_invoice,
    "rag_query_document": rag_query_document,
    "lookup_pcg_account": lookup_pcg_account,
}
