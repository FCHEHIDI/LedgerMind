"""Regex-based field extractor for French invoice text.

Responsibility: scan raw text from a PDF and extract all invoice fields
using compiled regex patterns. Returns a dict of raw string values — type
coercion and validation happen in the Pydantic schema (schema.py).

French invoice conventions covered:
  - Amounts: "1 200,00 €", "1200.00", "1 200,00"
  - Dates:   "15/01/2024", "15 janvier 2024", "2024-01-15"
  - SIREN:   "SIREN : 123 456 789", "Siren: 123456789"
  - Refs:    "Facture n° FA-2024-001", "N° facture : FA-2024-001"
  - Vendor:  first non-empty line heuristic (fallback)

Design: all patterns are compiled once at module level. The extractor is a
pure function — same input always produces the same output. No I/O.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Amounts: capture digits with optional space-thousands and comma/dot decimal
# Examples: 1 200,00  |  1200.00  |  1.200,00
_AMOUNT_RE = re.compile(
    r"(?:[\d]{1,3}(?:[\s\u00a0]?\d{3})*(?:[,\.]\d{1,2})?|\d+(?:[,\.]\d{1,2})?)"
)

# TTC — most explicit label first
_TTC_RE = re.compile(
    r"(?:montant\s+)?(?:total\s+)?(?:ttc|t\.t\.c\.?|toutes\s+taxes\s+comprises)"
    r"[^\d\n]*?([\d\s\u00a0]{1,10}[,\.]\d{2})",
    re.IGNORECASE,
)

# HT
_HT_RE = re.compile(
    r"(?:montant\s+)?(?:total\s+)?(?:ht|h\.t\.?|hors\s+taxes?)"
    r"[^\d\n]*?([\d\s\u00a0]{1,10}[,\.]\d{2})",
    re.IGNORECASE,
)

# TVA amount
_TVA_AMOUNT_RE = re.compile(
    r"(?:montant\s+)?(?:tva|t\.v\.a\.?)"
    r"(?:\s+\d{1,2}\s*%)?"
    r"[^\d\n]*?([\d\s\u00a0]{1,10}[,\.]\d{2})",
    re.IGNORECASE,
)

# TVA rate: "TVA 20 %", "20%"
_TVA_RATE_RE = re.compile(
    r"tva\s+(\d{1,2}(?:[,\.]\d{1,2})?)\s*%",
    re.IGNORECASE,
)

# SIREN: 9 digits, possibly spaced as "123 456 789"
_SIREN_RE = re.compile(
    r"(?:siren|siret)\s*[:\-]?\s*(\d{3}[\s\u00a0]?\d{3}[\s\u00a0]?\d{3})",
    re.IGNORECASE,
)

# Invoice reference
_REF_RE = re.compile(
    r"(?:facture\s+n[o°]?|n[o°]?\s+facture|r[eé]f[eé]rence|ref\.?)\s*[:\-]?\s*"
    r"([A-Z0-9][A-Z0-9\-_/\.]{2,30})",
    re.IGNORECASE,
)

# Dates: DD/MM/YYYY or YYYY-MM-DD or "15 janvier 2024"
_DATE_NUMERIC_RE = re.compile(
    r"\b(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})\b"  # DD/MM/YYYY or DD-MM-YYYY
)
_DATE_ISO_RE = re.compile(
    r"\b(\d{4})[/\-\.](\d{2})[/\-\.](\d{2})\b"  # YYYY-MM-DD
)
_FRENCH_MONTHS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12",
}
_DATE_LITERAL_RE = re.compile(
    r"\b(\d{1,2})\s+("
    + "|".join(_FRENCH_MONTHS.keys())
    + r")\s+(\d{4})\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Amount normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_amount(raw: str) -> str | None:
    """Convert a French-formatted amount string to a dot-decimal string.

    Handles:
      "1 200,50" → "1200.50"
      "1200.50"  → "1200.50"
      "1.200,50" → "1200.50"

    Args:
        raw: Raw string captured by a regex group.

    Returns:
        Normalised string suitable for ``Decimal()``, or None on failure.
    """
    # Remove spaces and non-breaking spaces (thousands separator in FR)
    s = re.sub(r"[\s\u00a0]", "", raw)
    # European: 1.200,50 → comma is decimal, dot is thousands
    if re.search(r"\d\.\d{3},", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        # Simple comma decimal: 1200,50 → 1200.50
        s = s.replace(",", ".")
    try:
        Decimal(s)
        return s
    except InvalidOperation:
        return None


def _normalise_date(text: str) -> str | None:
    """Extract and normalise the first date found in text to ISO format.

    Tries DD/MM/YYYY, YYYY-MM-DD, then "15 janvier 2024" patterns in order.

    Args:
        text: Raw text to search.

    Returns:
        ISO date string "YYYY-MM-DD", or None if no date found.
    """
    # ISO first (unambiguous)
    m = _DATE_ISO_RE.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # DD/MM/YYYY
    m = _DATE_NUMERIC_RE.search(text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # "15 janvier 2024"
    m = _DATE_LITERAL_RE.search(text)
    if m:
        month = _FRENCH_MONTHS.get(m.group(2).lower())
        if month:
            day = m.group(1).zfill(2)
            return f"{m.group(3)}-{month}-{day}"

    return None


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_fields(text: str) -> dict[str, str | None]:
    """Extract invoice fields from raw text using regex patterns.

    This function is pure — no I/O, no side effects. All values are raw
    strings or None. The caller (pipeline.py) feeds these into RawInvoice
    for validation and type coercion.

    Args:
        text: Full text content of the invoice (from PDF parser or OCR).

    Returns:
        Dict with keys: vendor, siren, date, reference,
        ht_amount, tva_rate, tva_amount, ttc_amount.
        Any field that could not be extracted is None.
    """
    fields: dict[str, str | None] = {
        "vendor": None,
        "siren": None,
        "date": None,
        "reference": None,
        "ht_amount": None,
        "tva_rate": None,
        "tva_amount": None,
        "ttc_amount": None,
    }

    # SIREN
    m = _SIREN_RE.search(text)
    if m:
        fields["siren"] = re.sub(r"\s", "", m.group(1))

    # Reference
    m = _REF_RE.search(text)
    if m:
        fields["reference"] = m.group(1).strip()

    # Date — search whole text
    fields["date"] = _normalise_date(text)

    # Amounts
    m = _TTC_RE.search(text)
    if m:
        fields["ttc_amount"] = _normalise_amount(m.group(1))

    m = _HT_RE.search(text)
    if m:
        fields["ht_amount"] = _normalise_amount(m.group(1))

    m = _TVA_AMOUNT_RE.search(text)
    if m:
        fields["tva_amount"] = _normalise_amount(m.group(1))

    # TVA rate
    m = _TVA_RATE_RE.search(text)
    if m:
        raw_rate = m.group(1).replace(",", ".")
        try:
            rate = Decimal(raw_rate) / 100
            fields["tva_rate"] = str(rate)
        except InvalidOperation:
            pass

    # Vendor heuristic: first non-empty, non-numeric, ≥ 3-char line
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3 and not re.fullmatch(r"[\d\s\W]+", line):
            fields["vendor"] = line
            break

    logger.debug("extract_fields: extracted %s", {k: v for k, v in fields.items() if v})
    return fields
