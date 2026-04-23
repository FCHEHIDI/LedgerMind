"""OCR fallback parser for scanned PDFs via pytesseract + pdf2image.

This parser is only invoked when pdfplumber returns empty pages (scanned
documents). It converts PDF pages to images then runs Tesseract OCR.

Both pytesseract and pdf2image are optional dependencies — the module
imports them lazily so the rest of the intake pipeline works without them
(digital PDFs are far more common in practice).

System requirement: Tesseract must be installed and on PATH.
  Windows: https://github.com/UB-Mannheim/tesseract/wiki
  Ubuntu:  sudo apt install tesseract-ocr tesseract-ocr-fra
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Language codes for Tesseract — French first, English fallback
_TESSERACT_LANG = "fra+eng"


class OCRParser:
    """Extract text from scanned PDFs using Tesseract OCR.

    Converts each page to a PIL image at 300 DPI then runs OCR.
    Results are returned in the same ``PDFParseResult`` format as
    ``PDFParser`` so callers are agnostic to which parser ran.

    Example::

        from lab.intake.parsers.pdf_parser import PDFParseResult
        parser = OCRParser()
        result = parser.parse(Path("facture_scannee.pdf"))
    """

    def parse(self, path: Path) -> "PDFParseResult":  # noqa: F821
        """Run OCR on every page of a scanned PDF.

        Args:
            path: Path to the scanned PDF. Must exist and be readable.

        Returns:
            PDFParseResult with OCR-extracted text per page.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            ImportError: If pytesseract or pdf2image are not installed.
            RuntimeError: If Tesseract is not found on PATH.
        """
        # Lazy imports — only fail if OCR is actually needed
        try:
            import pytesseract  # type: ignore[import]
            from pdf2image import convert_from_path  # type: ignore[import]
            from PIL import Image  # type: ignore[import]  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "OCR dependencies missing. Install with: "
                "pip install pytesseract pdf2image Pillow"
            ) from exc

        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        logger.info("OCRParser.parse: running OCR on %s", path)

        # Lazy import here to avoid circular reference in type hint above
        from lab.intake.parsers.pdf_parser import PageText, PDFParseResult

        try:
            images = convert_from_path(str(path), dpi=300)
        except Exception as exc:
            raise ValueError(f"Cannot convert PDF to images '{path}': {exc}") from exc

        pages: list[PageText] = []
        for i, image in enumerate(images, start=1):
            try:
                raw_text: str = pytesseract.image_to_string(
                    image, lang=_TESSERACT_LANG
                )
                pages.append(PageText(page_number=i, text=raw_text.strip()))
                logger.debug("OCRParser: page %d — %d chars", i, len(raw_text))
            except pytesseract.TesseractNotFoundError as exc:
                raise RuntimeError(
                    "Tesseract not found. Install Tesseract and ensure it is on PATH."
                ) from exc

        full_text = "\n\n".join(p.text for p in pages if not p.is_empty)
        logger.info(
            "OCRParser.parse: %s — %d page(s), chars=%d",
            path.name, len(pages), len(full_text),
        )
        return PDFParseResult(
            path=path,
            pages=pages,
            full_text=full_text,
            has_empty_pages=any(p.is_empty for p in pages),
        )
