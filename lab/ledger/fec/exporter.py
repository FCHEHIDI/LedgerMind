"""
FEC Exporter — Fichier des Écritures Comptables.

The FEC is a mandatory export format for French companies (Article L47 A du
Livre des Procédures Fiscales, arrêté du 29 juillet 2013). The tax authority
(DGFiP) requires it during a tax audit (contrôle fiscal).

Format specification:
  - Tab-separated values (\\t)
  - UTF-8 encoding
  - First row: header (18 column names)
  - One row per JournalLine (not per JournalEntry)
  - Dates: YYYYMMDD (no separators)
  - Amounts: decimal with comma separator ("1200,00"), never empty — use "0,00"
  - No quotes around fields
  - Debit and credit on separate columns (never negative values)

The 18 mandatory columns:
  1.  JournalCode      — Journal code (e.g., AC, VT, BQ, OD)
  2.  JournalLib       — Journal label
  3.  EcritureNum      — Entry reference (unique within the fiscal year)
  4.  EcritureDate     — Transaction date (YYYYMMDD)
  5.  CompteNum        — Account number
  6.  CompteLib        — Account label
  7.  CompAuxNum       — Auxiliary account number (empty if none)
  8.  CompAuxLib       — Auxiliary account label (empty if none)
  9.  PieceRef         — Source document reference (invoice number, etc.)
  10. PieceDate        — Source document date (YYYYMMDD)
  11. EcritureLib      — Line description
  12. Debit            — Debit amount ("0,00" if credit line)
  13. Credit           — Credit amount ("0,00" if debit line)
  14. EcritureLet      — Lettrage (matching code for reconciliation, optional)
  15. DateLet          — Lettrage date (YYYYMMDD, optional)
  16. ValidDate        — Validation date (YYYYMMDD)
  17. Montantdevise    — Amount in original currency if different from EUR
  18. Idevise          — Currency code if different from EUR

Security notes:
  - All field values are stripped of tab characters before writing to prevent
    TSV injection (a tab in an account label would corrupt the file structure).
  - Amounts are always formatted as non-negative decimals with comma separator.
    Negative amounts would signal data corruption.

Reference: https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000027774096
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from ..domain.entry import JournalEntry, JournalLine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEC_DELIMITER = "\t"

FEC_COLUMNS = [
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcritureLet",
    "DateLet",
    "ValidDate",
    "Montantdevise",
    "Idevise",
]

# Journal code → label mapping (extend as needed)
_JOURNAL_LABELS: dict[str, str] = {
    "AC": "Achats",
    "VT": "Ventes",
    "BQ": "Banque",
    "CA": "Caisse",
    "OD": "Opérations diverses",
    "AN": "À nouveaux",
    "NP": "Notes de paie",
    "IM": "Immobilisations",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize(value: str) -> str:
    """Remove tab and newline characters from a field value.

    This prevents TSV injection: if an account label contains a tab, it
    would silently add a spurious column and corrupt the FEC file.

    Args:
        value: Raw field value.

    Returns:
        Cleaned string with tabs and newlines replaced by spaces.
    """
    return value.replace("\t", " ").replace("\n", " ").replace("\r", "")


def _fmt_date(d: date) -> str:
    """Format a date as YYYYMMDD (FEC standard).

    Args:
        d: Python date object.

    Returns:
        String like "20240115".
    """
    return d.strftime("%Y%m%d")


def _fmt_amount(amount: Decimal) -> str:
    """Format a Decimal amount for FEC: comma decimal separator, 2 places.

    Args:
        amount: Non-negative Decimal.

    Returns:
        String like "1200,00".
    """
    return f"{amount:.2f}".replace(".", ",")


def _journal_label(code: str) -> str:
    return _JOURNAL_LABELS.get(code, code)


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------


def _entry_to_rows(
    entry: JournalEntry,
    validate_date: date | None = None,
) -> list[dict[str, str]]:
    """Convert a single JournalEntry to a list of FEC row dicts.

    Each JournalLine becomes one row. The debit and credit fields are
    mutually exclusive: one will be "0,00" and the other carries the amount.

    Args:
        entry: A posted JournalEntry.
        validate_date: Date to use as ValidDate (defaults to entry.date).

    Returns:
        List of dicts with one dict per line, keys = FEC column names.

    Raises:
        ValueError: If the entry is not posted.
    """
    if not entry.is_posted:
        raise ValueError(
            f"Entry {entry.reference!r} must be posted before FEC export."
        )

    v_date = validate_date or entry.date
    rows = []

    for line in entry.lines:
        debit_str = _fmt_amount(line.debit.amount)
        credit_str = _fmt_amount(line.credit.amount)

        row = {
            "JournalCode": _sanitize(entry.journal_code),
            "JournalLib": _sanitize(_journal_label(entry.journal_code)),
            "EcritureNum": _sanitize(entry.reference),
            "EcritureDate": _fmt_date(entry.date),
            "CompteNum": _sanitize(line.account.number),
            "CompteLib": _sanitize(line.account.label),
            "CompAuxNum": "",
            "CompAuxLib": "",
            "PieceRef": _sanitize(entry.reference),
            "PieceDate": _fmt_date(entry.date),
            "EcritureLib": _sanitize(line.label),
            "Debit": debit_str,
            "Credit": credit_str,
            "EcritureLet": "",
            "DateLet": "",
            "ValidDate": _fmt_date(v_date),
            "Montantdevise": "",
            "Idevise": "",
        }
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_to_string(
    entries: list[JournalEntry],
    validate_date: date | None = None,
) -> str:
    """Export a list of posted JournalEntries to a FEC string.

    Args:
        entries: List of posted JournalEntry objects.
        validate_date: Date to stamp as ValidDate on all rows. Defaults to
                       each entry's own date if None.

    Returns:
        UTF-8 FEC content as a string (tab-separated, header included).

    Raises:
        ValueError: If any entry is not posted.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=FEC_COLUMNS,
        delimiter=FEC_DELIMITER,
        lineterminator="\r\n",   # FEC spec requires CRLF
        quoting=csv.QUOTE_NONE,
        escapechar="\\",
    )
    writer.writeheader()

    for entry in entries:
        for row in _entry_to_rows(entry, validate_date):
            writer.writerow(row)

    return buf.getvalue()


def export_to_file(
    entries: list[JournalEntry],
    path: str,
    siren: str,
    fiscal_year_end: date,
    validate_date: date | None = None,
) -> str:
    """Export entries to a FEC file with the standard DGFiP filename.

    The mandatory filename format is: {SIREN}FEC{YYYYMMDD}
    e.g., 123456789FEC20241231

    Args:
        entries: List of posted JournalEntry objects.
        path: Directory path where the file will be written.
        siren: 9-digit SIREN number of the company.
        fiscal_year_end: Last day of the fiscal year (determines filename).
        validate_date: Optional ValidDate override.

    Returns:
        Full path of the written file.

    Raises:
        ValueError: If siren is not 9 digits, or any entry is not posted.
    """
    if not siren.isdigit() or len(siren) != 9:
        raise ValueError(
            f"SIREN must be exactly 9 digits, got {siren!r}"
        )

    filename = f"{siren}FEC{_fmt_date(fiscal_year_end)}"
    full_path = f"{path.rstrip('/')}/{filename}"

    content = export_to_string(entries, validate_date)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return full_path
