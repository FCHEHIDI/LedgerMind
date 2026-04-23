"""Intake pipeline — orchestrates PDF parsing → extraction → validation.

Entry point for Invariant 3. Accepts a PDF file path and returns either a
validated RawInvoice ready for the LangGraph invoice graph, or a structured
error describing what went wrong.

Pipeline stages:
  1. PDFParser.parse()        — extract selectable text (digital PDF)
  2. OCRParser.parse()        — fallback when pages are empty (scanned PDF)
  3. extract_fields()         — regex extraction of all invoice fields
  4. RawInvoice(**fields)     — Pydantic validation + type coercion
  5. .to_graph_input()        — serialise to graph-compatible dict

Error handling: each stage returns an IntakeResult — callers never deal
with exceptions directly. This keeps the pipeline composable and testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .extractors.regex_extractor import extract_fields
from .extractors.schema import RawInvoice
from .parsers.pdf_parser import PDFParser

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    """Result of processing one PDF invoice through the intake pipeline.

    Attributes:
        success: True when all stages completed without error.
        invoice: Validated RawInvoice on success, None on failure.
        raw_text: Full extracted text (available even on extraction failure).
        errors: Human-readable list of errors (empty on success).
        graph_input: Dict ready for ``InvoiceState["raw_input"]`` on success.
    """

    success: bool
    invoice: Optional[RawInvoice]
    raw_text: str
    errors: list[str] = field(default_factory=list)
    graph_input: Optional[dict] = field(default=None)


class IntakePipeline:
    """Process a PDF invoice through parsing, extraction, and validation.

    Instantiate once and call ``process()`` for each file. The pipeline
    automatically falls back to OCR when pdfplumber returns no selectable
    text (scanned documents).

    Args:
        use_ocr_fallback: Enable OCR fallback for scanned PDFs.
                          Requires pytesseract + pdf2image + Tesseract.
                          Defaults to False for the lab (avoids hard dep).

    Example::

        pipeline = IntakePipeline()
        result = pipeline.process(Path("facture.pdf"))
        if result.success:
            graph_result = invoice_graph.invoke({
                "raw_input": result.graph_input,
                ...
            })
    """

    def __init__(self, use_ocr_fallback: bool = False) -> None:
        self._pdf_parser = PDFParser()
        self._use_ocr_fallback = use_ocr_fallback
        logger.debug("IntakePipeline: init (ocr_fallback=%s)", use_ocr_fallback)

    def process(self, path: Path) -> IntakeResult:
        """Process a single PDF invoice file.

        Args:
            path: Path to the PDF file.

        Returns:
            IntakeResult with success flag, validated invoice, and any errors.
            Never raises — all errors are captured in IntakeResult.errors.
        """
        logger.info("IntakePipeline.process: %s", path)

        # Stage 1 — PDF text extraction
        try:
            parse_result = self._pdf_parser.parse(path)
        except (FileNotFoundError, ValueError) as exc:
            return IntakeResult(
                success=False,
                invoice=None,
                raw_text="",
                errors=[f"Erreur lecture PDF: {exc}"],
            )

        raw_text = parse_result.full_text

        # Stage 2 — OCR fallback for scanned PDFs
        if parse_result.has_empty_pages and not raw_text.strip():
            if self._use_ocr_fallback:
                raw_text = self._run_ocr(path)
            else:
                return IntakeResult(
                    success=False,
                    invoice=None,
                    raw_text="",
                    errors=[
                        "PDF scanné détecté (aucun texte sélectionnable). "
                        "Activez use_ocr_fallback=True pour utiliser l'OCR."
                    ],
                )

        if not raw_text.strip():
            return IntakeResult(
                success=False,
                invoice=None,
                raw_text=raw_text,
                errors=["Aucun texte extrait du PDF"],
            )

        # Stage 3 — Regex extraction
        raw_fields = extract_fields(raw_text)

        missing = [k for k, v in raw_fields.items() if v is None]
        if missing:
            logger.warning(
                "IntakePipeline.process: champs manquants après extraction: %s",
                missing,
            )

        # Stage 4 — Pydantic validation
        try:
            invoice = RawInvoice(**{k: v for k, v in raw_fields.items() if v is not None})
        except ValidationError as exc:
            errors = [f"{e['loc'][0]}: {e['msg']}" for e in exc.errors()]
            return IntakeResult(
                success=False,
                invoice=None,
                raw_text=raw_text,
                errors=errors,
            )
        except TypeError as exc:
            return IntakeResult(
                success=False,
                invoice=None,
                raw_text=raw_text,
                errors=[f"Champs insuffisants pour construire la facture: {exc}"],
            )

        # Stage 5 — serialise for graph
        graph_input = invoice.to_graph_input()
        logger.info(
            "IntakePipeline.process: succès ref=%s vendor=%s",
            invoice.reference, invoice.vendor,
        )
        return IntakeResult(
            success=True,
            invoice=invoice,
            raw_text=raw_text,
            graph_input=graph_input,
        )

    def _run_ocr(self, path: Path) -> str:
        """Run OCR fallback and return concatenated text.

        Args:
            path: Path to the scanned PDF.

        Returns:
            Full extracted text, or empty string on OCR failure.
        """
        try:
            from .parsers.ocr_parser import OCRParser
            ocr_result = OCRParser().parse(path)
            return ocr_result.full_text
        except (ImportError, RuntimeError, ValueError) as exc:
            logger.error("IntakePipeline._run_ocr: %s", exc)
            return ""
