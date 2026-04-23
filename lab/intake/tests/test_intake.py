"""Invariant 3 — Intake: test suite.

No real PDFs, no OCR, no network. Fixtures synthesise the text that a real
PDF parser would extract. This keeps tests fast, deterministic, and free of
system dependencies (Tesseract, Poppler, etc.).

Test groups:
  TestRegexExtractor   (9 tests) — field-level pattern coverage
  TestRawInvoiceSchema (7 tests) — Pydantic validation rules
  TestPDFParser        (3 tests) — file handling (no real PDF needed)
  TestIntakePipeline   (7 tests) — end-to-end with injected text
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from lab.intake.extractors.regex_extractor import extract_fields, _normalise_amount, _normalise_date
from lab.intake.extractors.schema import RawInvoice
from lab.intake.parsers.pdf_parser import PDFParser, PDFParseResult, PageText
from lab.intake.pipeline import IntakePipeline, IntakeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_INVOICE_TEXT = """\
ACME SAS
12 rue de la Paix, 75001 Paris

SIREN : 123 456 789

Facture n° FA-2024-001
Date : 15/01/2024

Prestation de services

Total HT               1 000,00 €
TVA 20 %                 200,00 €
Total TTC              1 200,00 €
"""

INVOICE_TVA_EXEMPT = """\
Micro Conseil
SIREN: 987654321

Facture N° MC-2024-042
Date: 2024-03-10

Prestation conseil         500,00 €

HT                         500,00
TVA 0 %                      0,00
TTC                        500,00
"""

INVOICE_ISO_DATE = """\
TechCorp SARL
SIREN : 111222333

Ref: TC-001
Date: 2024-06-01

HT   800,00
TVA  160,00
TTC  960,00
"""


# ---------------------------------------------------------------------------
# TestRegexExtractor
# ---------------------------------------------------------------------------

class TestRegexExtractor:
    def test_extracts_siren(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        assert fields["siren"] == "123456789"

    def test_extracts_reference(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        assert fields["reference"] == "FA-2024-001"

    def test_extracts_date_dd_mm_yyyy(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        assert fields["date"] == "2024-01-15"

    def test_extracts_date_iso(self):
        fields = extract_fields(INVOICE_ISO_DATE)
        assert fields["date"] == "2024-06-01"

    def test_extracts_ttc(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        assert fields["ttc_amount"] == "1200.00"

    def test_extracts_ht(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        assert fields["ht_amount"] == "1000.00"

    def test_extracts_tva_amount(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        assert fields["tva_amount"] == "200.00"

    def test_extracts_tva_rate(self):
        fields = extract_fields(SAMPLE_INVOICE_TEXT)
        # Decimal("20") / 100 → "0.2" — numeric equality is what matters
        assert fields["tva_rate"] is not None
        assert Decimal(fields["tva_rate"]) == Decimal("0.2")

    def test_normalise_amount_french_format(self):
        assert _normalise_amount("1 200,50") == "1200.50"

    def test_normalise_amount_dot_decimal(self):
        assert _normalise_amount("1200.50") == "1200.50"

    def test_normalise_date_literal(self):
        assert _normalise_date("le 15 janvier 2024") == "2024-01-15"

    def test_missing_fields_return_none(self):
        fields = extract_fields("Texte sans aucun champ reconnu.")
        assert fields["siren"] is None
        assert fields["ttc_amount"] is None


# ---------------------------------------------------------------------------
# TestRawInvoiceSchema
# ---------------------------------------------------------------------------

class TestRawInvoiceSchema:
    def _base(self, **overrides) -> dict:
        data = {
            "vendor": "ACME SAS",
            "siren": "123456789",
            "date": date(2024, 1, 15),
            "reference": "FA-2024-001",
            "ht_amount": Decimal("1000.00"),
            "tva_rate": Decimal("0.20"),
            "tva_amount": Decimal("200.00"),
            "ttc_amount": Decimal("1200.00"),
        }
        data.update(overrides)
        return data

    def test_valid_invoice_builds_successfully(self):
        inv = RawInvoice(**self._base())
        assert inv.vendor == "ACME SAS"
        assert inv.siren == "123456789"

    def test_siren_with_spaces_is_cleaned(self):
        inv = RawInvoice(**self._base(siren="123 456 789"))
        assert inv.siren == "123456789"

    def test_invalid_siren_raises(self):
        with pytest.raises(ValidationError):
            RawInvoice(**self._base(siren="12345"))

    def test_negative_ht_raises(self):
        with pytest.raises(ValidationError):
            RawInvoice(**self._base(ht_amount=Decimal("-100")))

    def test_tva_rate_computed_when_absent(self):
        data = self._base()
        del data["tva_rate"]
        inv = RawInvoice(**data)
        assert inv.tva_rate == Decimal("0.2000")

    def test_currency_normalised_to_uppercase(self):
        inv = RawInvoice(**self._base(currency="eur"))
        assert inv.currency == "EUR"

    def test_to_graph_input_returns_dict(self):
        inv = RawInvoice(**self._base())
        result = inv.to_graph_input()
        assert result["vendor"] == "ACME SAS"
        assert result["currency"] == "EUR"
        assert isinstance(result["date"], date)
        assert isinstance(result["ht_amount"], str)

    def test_extra_fields_are_forbidden(self):
        with pytest.raises(ValidationError):
            RawInvoice(**self._base(unknown_field="bad"))


# ---------------------------------------------------------------------------
# TestPDFParser
# ---------------------------------------------------------------------------

class TestPDFParser:
    def test_missing_file_raises_file_not_found(self):
        parser = PDFParser()
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/facture.pdf"))

    def test_parse_result_has_full_text(self):
        """Simulate pdfplumber returning text via mock."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Ligne 1\nLigne 2"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            # Create a dummy file so exists() passes
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp = Path(f.name)
            try:
                result = PDFParser().parse(tmp)
                assert "Ligne 1" in result.full_text
                assert result.has_empty_pages is False
            finally:
                os.unlink(tmp)

    def test_empty_page_sets_has_empty_pages(self):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: mock_pdf
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                tmp = Path(f.name)
            try:
                result = PDFParser().parse(tmp)
                assert result.has_empty_pages is True
            finally:
                os.unlink(tmp)


# ---------------------------------------------------------------------------
# TestIntakePipeline
# ---------------------------------------------------------------------------

class TestIntakePipeline:
    """Tests inject text directly by patching PDFParser.parse."""

    def _pipeline_with_text(self, text: str) -> IntakeResult:
        """Run the intake pipeline using ``text`` as the PDF content."""
        mock_result = PDFParseResult(
            path=Path("test.pdf"),
            pages=[PageText(page_number=1, text=text)],
            full_text=text,
            has_empty_pages=False,
        )
        pipeline = IntakePipeline()
        with patch.object(pipeline._pdf_parser, "parse", return_value=mock_result):
            return pipeline.process(Path("test.pdf"))

    def test_happy_path_succeeds(self):
        result = self._pipeline_with_text(SAMPLE_INVOICE_TEXT)
        assert result.success is True
        assert result.invoice is not None
        assert result.invoice.vendor == "ACME SAS"

    def test_happy_path_graph_input_is_complete(self):
        result = self._pipeline_with_text(SAMPLE_INVOICE_TEXT)
        gi = result.graph_input
        for key in ("vendor", "siren", "date", "reference", "ht_amount", "tva_amount", "ttc_amount"):
            assert key in gi, f"Missing key: {key}"

    def test_tva_exempt_invoice_succeeds(self):
        result = self._pipeline_with_text(INVOICE_TVA_EXEMPT)
        assert result.success is True
        assert result.invoice.tva_amount == Decimal("0.00")

    def test_missing_siren_returns_failure(self):
        text = SAMPLE_INVOICE_TEXT.replace("SIREN : 123 456 789", "")
        result = self._pipeline_with_text(text)
        assert result.success is False
        assert len(result.errors) > 0

    def test_scanned_pdf_without_ocr_returns_failure(self):
        mock_result = PDFParseResult(
            path=Path("scan.pdf"),
            pages=[PageText(page_number=1, text="")],
            full_text="",
            has_empty_pages=True,
        )
        pipeline = IntakePipeline(use_ocr_fallback=False)
        with patch.object(pipeline._pdf_parser, "parse", return_value=mock_result):
            result = pipeline.process(Path("scan.pdf"))
        assert result.success is False
        assert "OCR" in result.errors[0]

    def test_missing_pdf_returns_failure(self):
        pipeline = IntakePipeline()
        result = pipeline.process(Path("/no/such/file.pdf"))
        assert result.success is False
        assert "PDF" in result.errors[0]

    def test_pipeline_connects_to_graph(self):
        """End-to-end: intake result feeds directly into invoice_graph."""
        from lab.graph.graph import invoice_graph

        result = self._pipeline_with_text(SAMPLE_INVOICE_TEXT)
        assert result.success is True

        graph_state = invoice_graph.invoke({
            "raw_input": result.graph_input,
            "invoice": None,
            "errors": [],
            "status": "pending",
            "journal_entry_id": None,
        })
        assert graph_state["status"] == "posted"
        assert graph_state["journal_entry_id"] is not None
