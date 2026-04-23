"""PDF text extraction via pdfplumber.

Responsibility: open a PDF file (digital or hybrid) and return the raw text
content page by page. This is the fast path — no OCR involved. Falls back
gracefully when a page yields no text (scanned page), signalling the caller
to escalate to the OCR parser.

Dependencies: pdfplumber (wraps pdfminer.six under the hood).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PageText:
    """Text extracted from a single PDF page.

    Args:
        page_number: 1-based page number.
        text: Raw extracted text, stripped of leading/trailing whitespace.
        is_empty: True when the page yielded no selectable text (likely scanned).
    """

    page_number: int
    text: str
    is_empty: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_empty = not self.text.strip()


@dataclass
class PDFParseResult:
    """Full result of parsing a PDF file.

    Args:
        path: Absolute path to the source PDF.
        pages: Ordered list of PageText, one per page.
        full_text: Concatenation of all page texts, separated by newlines.
        has_empty_pages: True if any page returned no selectable text.
    """

    path: Path
    pages: list[PageText]
    full_text: str
    has_empty_pages: bool


class PDFParser:
    """Extract selectable text from a digital PDF using pdfplumber.

    This parser is instantiated once and reused across multiple files.
    Thread-safety: each call to ``parse`` opens and closes its own file handle.

    Example::

        parser = PDFParser()
        result = parser.parse(Path("facture.pdf"))
        print(result.full_text)
    """

    def parse(self, path: Path) -> PDFParseResult:
        """Extract text from every page of a PDF file.

        Args:
            path: Path to the PDF file. Must exist and be readable.

        Returns:
            PDFParseResult with per-page text and aggregated full_text.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            ValueError: If the file is not a valid PDF.
        """
        try:
            import pdfplumber  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "pdfplumber is required for PDF parsing. "
                "Install it with: pip install pdfplumber"
            ) from exc

        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        logger.debug("PDFParser.parse: opening %s", path)

        pages: list[PageText] = []
        try:
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    raw = page.extract_text() or ""
                    pages.append(PageText(page_number=i, text=raw.strip()))
        except Exception as exc:
            raise ValueError(f"Cannot parse PDF '{path}': {exc}") from exc

        full_text = "\n\n".join(p.text for p in pages if not p.is_empty)
        has_empty = any(p.is_empty for p in pages)

        logger.info(
            "PDFParser.parse: %s — %d page(s), has_empty=%s, chars=%d",
            path.name, len(pages), has_empty, len(full_text),
        )
        return PDFParseResult(
            path=path,
            pages=pages,
            full_text=full_text,
            has_empty_pages=has_empty,
        )
