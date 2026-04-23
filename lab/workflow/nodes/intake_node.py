"""Invariant 6 — Workflow: intake node.

Delegates to :func:`lab.intake.extractors.regex_extractor.extract_fields`
to turn raw invoice text into a structured field dict.
"""

from __future__ import annotations

import logging
from typing import Any

from lab.workflow.state import WorkflowState

logger = logging.getLogger(__name__)


def intake_node(state: WorkflowState) -> dict[str, Any]:
    """Extract invoice fields from raw text using compiled regex patterns.

    Args:
        state: Current workflow state.  Reads ``raw_text``.

    Returns:
        Partial state update: ``{"extracted_fields": dict[str, str | None]}``.
    """
    from lab.intake.extractors.regex_extractor import extract_fields

    text: str = state.get("raw_text", "")  # type: ignore[assignment]
    fields = extract_fields(text)
    non_null = sum(v is not None for v in fields.values())
    logger.info("intake_node: extracted %d/%d non-null fields", non_null, len(fields))
    return {"extracted_fields": fields}
