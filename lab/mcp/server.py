"""Invariant 5 — MCP: minimal JSON-RPC 2.0 server.

Implements the subset of the Model Context Protocol (MCP) needed for the lab:

    tools/list  — enumerate available tools with JSON Schema descriptors
    tools/call  — invoke a tool by name with validated arguments

Transport
---------
The :class:`MCPServer` is transport-agnostic: it works on any ``dict`` input
and returns a ``dict`` output.  The :func:`run_stdio` helper wires it to
``stdin`` / ``stdout`` for a real server process.

Protocol reference: https://spec.modelcontextprotocol.io/specification/
(JSON-RPC 2.0, error codes from https://www.jsonrpc.org/specification)

Error codes
-----------
* ``-32700`` ParseError      — malformed JSON
* ``-32600`` InvalidRequest  — not a valid JSON-RPC object
* ``-32601`` MethodNotFound  — unknown method
* ``-32602`` InvalidParams   — tool arguments fail Pydantic validation
* ``-32603`` InternalError   — unhandled exception inside a tool
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from pydantic import ValidationError

from lab.mcp.schemas import (
    ExtractInvoiceInput,
    LookupPCGInput,
    MCPError,
    MCPRequest,
    MCPResponse,
    PostInvoiceInput,
    RAGQueryInput,
    ToolDescriptor,
    ValidateInvoiceInput,
)
from lab.mcp.tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC error codes
# ---------------------------------------------------------------------------

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

# ---------------------------------------------------------------------------
# Input schema map: tool_name → Pydantic input model
# ---------------------------------------------------------------------------

_INPUT_MODELS: dict[str, type] = {
    "extract_invoice_text": ExtractInvoiceInput,
    "validate_invoice_fields": ValidateInvoiceInput,
    "post_invoice": PostInvoiceInput,
    "rag_query_document": RAGQueryInput,
    "lookup_pcg_account": LookupPCGInput,
}

# Human-readable descriptions for each tool (used in tools/list).
_TOOL_DESCRIPTIONS: dict[str, str] = {
    "extract_invoice_text": (
        "Extract structured fields (vendor, SIREN, date, amounts…) from raw "
        "French invoice text using compiled regex patterns."
    ),
    "validate_invoice_fields": (
        "Run business-rule validation on extracted invoice fields and return "
        "status ('valid' | 'invalid') plus a list of validation errors."
    ),
    "post_invoice": (
        "Validate invoice fields and, if valid, post the corresponding journal "
        "entry to the general ledger.  Returns status and journal_entry_id."
    ),
    "rag_query_document": (
        "Chunk and embed a document, then retrieve the k most relevant passages "
        "for a natural-language question.  Returns a context string."
    ),
    "lookup_pcg_account": (
        "Look up a French PCG (Plan Comptable Général) account by its numeric "
        "code.  Supports exact match and prefix resolution."
    ),
}


class MCPServer:
    """Stateless JSON-RPC 2.0 MCP server.

    Handles two methods:
    * ``tools/list`` — returns :class:`ToolDescriptor` list.
    * ``tools/call`` — dispatches to a registered tool.

    Args:
        tool_registry: Mapping of tool name → callable.  Defaults to the
            module-level :data:`lab.mcp.tools.TOOL_REGISTRY`.

    Example::

        server = MCPServer()
        response = server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
    """

    def __init__(self, tool_registry: dict[str, Any] | None = None) -> None:
        self._tools = tool_registry if tool_registry is not None else TOOL_REGISTRY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Dispatch one JSON-RPC request and return a JSON-RPC response dict.

        Args:
            raw: Parsed JSON-RPC 2.0 request as a Python dict.

        Returns:
            JSON-serialisable dict (either ``result`` or ``error`` key).
        """
        # Validate envelope
        try:
            req = MCPRequest.model_validate(raw)
        except ValidationError as exc:
            return self._error(None, _INVALID_REQUEST, f"Invalid request: {exc}").model_dump()

        req_id = req.id

        if req.method == "tools/list":
            return self._handle_tools_list(req_id)
        elif req.method == "tools/call":
            return self._handle_tools_call(req_id, req.params)
        else:
            return self._error(req_id, _METHOD_NOT_FOUND, f"Unknown method: {req.method!r}").model_dump()

    def handle_json(self, json_str: str) -> str:
        """Parse *json_str*, dispatch, and return a JSON string response.

        Args:
            json_str: Raw JSON-encoded request string.

        Returns:
            JSON-encoded response string (always valid JSON).
        """
        try:
            raw = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return json.dumps(self._error(None, _PARSE_ERROR, str(exc)).model_dump())
        return json.dumps(self.handle(raw))

    # ------------------------------------------------------------------
    # Method handlers
    # ------------------------------------------------------------------

    def _handle_tools_list(self, req_id: Any) -> dict[str, Any]:
        """Return descriptors for all registered tools."""
        descriptors: list[dict[str, Any]] = []
        for name, input_model in _INPUT_MODELS.items():
            schema = input_model.model_json_schema()
            td = ToolDescriptor(
                name=name,
                description=_TOOL_DESCRIPTIONS.get(name, ""),
                input_schema=schema,
            )
            descriptors.append(td.model_dump())
        logger.debug("tools/list: returned %d descriptors", len(descriptors))
        return MCPResponse(id=req_id, result={"tools": descriptors}).model_dump()

    def _handle_tools_call(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Validate params, dispatch to tool function, return result."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name or tool_name not in self._tools:
            return self._error(
                req_id, _METHOD_NOT_FOUND, f"Tool not found: {tool_name!r}"
            ).model_dump()

        input_model_cls = _INPUT_MODELS.get(tool_name)
        if input_model_cls is None:
            return self._error(req_id, _INTERNAL_ERROR, f"No input model for {tool_name!r}").model_dump()

        # Validate arguments
        try:
            inp = input_model_cls.model_validate(arguments)
        except ValidationError as exc:
            return self._error(req_id, _INVALID_PARAMS, str(exc)).model_dump()

        # Call tool
        try:
            tool_fn = self._tools[tool_name]
            output = tool_fn(inp)
            result = output.model_dump() if hasattr(output, "model_dump") else output
            logger.debug("tools/call %s → success", tool_name)
            return MCPResponse(id=req_id, result=result).model_dump()
        except Exception as exc:  # noqa: BLE001
            logger.error("tools/call %s raised: %s", tool_name, exc)
            return self._error(req_id, _INTERNAL_ERROR, str(exc)).model_dump()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> MCPError:
        """Build a :class:`MCPError` envelope."""
        return MCPError(id=req_id, error={"code": code, "message": message})


# ---------------------------------------------------------------------------
# stdio transport (for running as a real MCP server process)
# ---------------------------------------------------------------------------


def run_stdio(server: MCPServer | None = None) -> None:
    """Read newline-delimited JSON-RPC requests from stdin, write responses to stdout.

    Each line must be a complete JSON-RPC request.  Responses are written as
    single lines to stdout.  This implements the stdio transport used by MCP
    host applications (e.g. Claude Desktop).

    Args:
        server: Optional pre-built :class:`MCPServer`.  Creates a default one
            if not provided.
    """
    if server is None:
        server = MCPServer()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = server.handle_json(line)
        sys.stdout.write(response + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_stdio()
