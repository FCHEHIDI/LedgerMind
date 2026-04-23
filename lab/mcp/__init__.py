"""Invariant 5 — MCP: public re-exports."""

from lab.mcp.server import MCPServer, run_stdio
from lab.mcp.tools import TOOL_REGISTRY
from lab.mcp.schemas import (
    ExtractInvoiceInput, ExtractInvoiceOutput,
    ValidateInvoiceInput, ValidateInvoiceOutput,
    PostInvoiceInput, PostInvoiceOutput,
    RAGQueryInput, RAGQueryOutput,
    LookupPCGInput, LookupPCGOutput,
    MCPRequest, MCPResponse, MCPError, ToolDescriptor,
)

__all__ = [
    "MCPServer", "run_stdio", "TOOL_REGISTRY",
    "ExtractInvoiceInput", "ExtractInvoiceOutput",
    "ValidateInvoiceInput", "ValidateInvoiceOutput",
    "PostInvoiceInput", "PostInvoiceOutput",
    "RAGQueryInput", "RAGQueryOutput",
    "LookupPCGInput", "LookupPCGOutput",
    "MCPRequest", "MCPResponse", "MCPError", "ToolDescriptor",
]
