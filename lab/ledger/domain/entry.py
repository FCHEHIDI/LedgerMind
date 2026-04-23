"""
JournalLine and JournalEntry — core transactional objects.

Key invariants enforced here:

  1. BALANCE INVARIANT (hard constraint):
       sum(line.debit for line in entry) == sum(line.credit for line in entry)
     Violated → ImbalancedEntryError. Entry is rejected atomically.

  2. IMMUTABILITY AFTER POSTING:
     Once entry.post() is called, no lines can be added or removed.
     Corrections must be made via entry.reverse() — an "extourne" — which
     creates a new counter-entry. This is required by French accounting law
     (Code de commerce art. L123-22, PCG art. 911-1).

  3. SINGLE-COLUMN LINES:
     A JournalLine carries either a debit amount OR a credit amount, never
     both and never zero. This mirrors the physical journal format.

  4. POSITIVE AMOUNTS ONLY:
     Debit and credit amounts must be strictly positive. Signed arithmetic
     (negative debits to represent a credit) is forbidden at this level.
     Risk: allowing negatives would let a single line silently flip its
     accounting polarity.

  5. CURRENCY CONSISTENCY:
     All lines in an entry must share the same currency. Cross-currency
     entries require a separate currency-conversion entry.

  6. ATOMICITY:
     post() validates all invariants in one pass before setting _posted.
     No partial posting is possible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterator

from .account import Account
from .exceptions import (
    CurrencyMismatchError,
    ImbalancedEntryError,
    ImmutableEntryError,
    NegativeAmountError,
)
from .money import Money


# ---------------------------------------------------------------------------
# JournalLine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JournalLine:
    """One line (imputation) in a journal entry.

    Exactly one of debit or credit must be non-zero.

    Args:
        account: The PCG account being debited or credited.
        debit: Debit amount (Money.zero if this is a credit line).
        credit: Credit amount (Money.zero if this is a debit line).
        label: Short description of this line (e.g., "Achat marchandises").

    Raises:
        NegativeAmountError: If debit or credit is negative, or both are zero.
        ValueError: If both debit and credit are non-zero.
    """

    account: Account
    debit: Money
    credit: Money
    label: str

    def __post_init__(self) -> None:
        zero = Decimal("0.00")

        if self.debit.amount < zero:
            raise NegativeAmountError(
                f"Debit amount cannot be negative on account {self.account.number}: "
                f"{self.debit}"
            )
        if self.credit.amount < zero:
            raise NegativeAmountError(
                f"Credit amount cannot be negative on account {self.account.number}: "
                f"{self.credit}"
            )
        if self.debit.amount > zero and self.credit.amount > zero:
            raise ValueError(
                f"A line cannot carry both a debit and a credit simultaneously "
                f"(account {self.account.number}). Use two separate lines."
            )
        if self.debit.amount == zero and self.credit.amount == zero:
            raise NegativeAmountError(
                f"A line must carry either a debit or a credit amount "
                f"(account {self.account.number})."
            )

    # ------------------------------------------------------------------
    # Named constructors — explicit intent, no ambiguity
    # ------------------------------------------------------------------

    @classmethod
    def debit_line(cls, account: Account, amount: Money, label: str) -> JournalLine:
        """Create a debit line.

        Args:
            account: Account to debit.
            amount: Amount to debit (must be positive).
            label: Line description.

        Returns:
            A JournalLine with the given debit and zero credit.
        """
        return cls(
            account=account,
            debit=amount,
            credit=Money.zero(amount.currency),
            label=label,
        )

    @classmethod
    def credit_line(cls, account: Account, amount: Money, label: str) -> JournalLine:
        """Create a credit line.

        Args:
            account: Account to credit.
            amount: Amount to credit (must be positive).
            label: Line description.

        Returns:
            A JournalLine with zero debit and the given credit.
        """
        return cls(
            account=account,
            debit=Money.zero(amount.currency),
            credit=amount,
            label=label,
        )

    @property
    def is_debit(self) -> bool:
        """True if this line carries a debit amount."""
        return self.debit.amount > Decimal("0.00")

    @property
    def is_credit(self) -> bool:
        """True if this line carries a credit amount."""
        return self.credit.amount > Decimal("0.00")

    @property
    def amount(self) -> Money:
        """The non-zero amount on this line (debit or credit)."""
        return self.debit if self.is_debit else self.credit

    def __str__(self) -> str:
        side = f"D {self.debit}" if self.is_debit else f"C {self.credit}"
        return f"{self.account.number:<10} {self.label:<40} {side}"


# ---------------------------------------------------------------------------
# JournalEntry
# ---------------------------------------------------------------------------


@dataclass
class JournalEntry:
    """A balanced journal entry (écriture comptable).

    An entry groups multiple JournalLines that together satisfy the
    fundamental accounting equation:

        sum(debits) == sum(credits)

    Workflow:
        entry = JournalEntry(date=..., reference=...)
        entry.add_line(JournalLine.debit_line(...))
        entry.add_line(JournalLine.credit_line(...))
        entry.post()   ← validates and freezes

    After post(), the entry is immutable. To correct it, use reverse().

    Args:
        date: Transaction date.
        reference: Unique reference (e.g., invoice number, "FACT-2024-001").
        journal_code: Journal identifier ("AC" achats, "VT" ventes, "BQ" banque…).
        description: Optional human-readable description.
    """

    date: date
    reference: str
    journal_code: str = "OD"      # Opérations Diverses by default
    description: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    _lines: list[JournalLine] = field(default_factory=list, repr=False)
    _posted: bool = field(default=False, repr=False)

    # ------------------------------------------------------------------
    # Mutation (only allowed before posting)
    # ------------------------------------------------------------------

    def add_line(self, line: JournalLine) -> None:
        """Append a line to this entry.

        Args:
            line: The JournalLine to add.

        Raises:
            ImmutableEntryError: If the entry is already posted.
            CurrencyMismatchError: If the line's currency differs from the
                                   currency of existing lines.
        """
        if self._posted:
            raise ImmutableEntryError(
                f"Entry {self.reference!r} is posted and immutable. "
                "Use reverse() to create a counter-entry."
            )
        if self._lines:
            existing_currency = self._lines[0].debit.currency or self._lines[0].credit.currency
            line_currency = line.debit.currency if line.is_debit else line.credit.currency
            if line_currency != existing_currency:
                raise CurrencyMismatchError(
                    f"Entry {self.reference!r} uses {existing_currency} "
                    f"but this line uses {line_currency}."
                )
        self._lines.append(line)

    def post(self) -> None:
        """Validate the balance invariant and make the entry immutable.

        This is an atomic operation: either all invariants pass and the
        entry is posted, or it is rejected entirely and remains unchanged.

        Raises:
            ImmutableEntryError: If already posted.
            ImbalancedEntryError: If sum(debits) != sum(credits).
        """
        if self._posted:
            raise ImmutableEntryError(
                f"Entry {self.reference!r} is already posted."
            )
        self._validate_balance()
        self._posted = True  # Only set after all checks pass

    # ------------------------------------------------------------------
    # Reversal (extourne) — the only way to "undo" a posted entry
    # ------------------------------------------------------------------

    def reverse(self, reversal_date: date, reversal_ref: str) -> JournalEntry:
        """Create a counter-entry (extourne) that cancels this entry.

        The reversal swaps every debit line to a credit line and vice versa,
        producing an entry that, when posted to the ledger, nets all balances
        back to zero.

        Args:
            reversal_date: Date for the reversal entry.
            reversal_ref: Reference for the reversal entry.

        Returns:
            A new, unposted JournalEntry that is the mirror image of this one.

        Raises:
            ValueError: If this entry is not yet posted (can't reverse a draft).
        """
        if not self._posted:
            raise ValueError(
                f"Entry {self.reference!r} must be posted before it can be reversed."
            )
        reversal = JournalEntry(
            date=reversal_date,
            reference=reversal_ref,
            journal_code=self.journal_code,
            description=f"Extourne de {self.reference}: {self.description}",
        )
        for line in self._lines:
            if line.is_debit:
                reversal.add_line(
                    JournalLine.credit_line(
                        line.account, line.debit, f"Extourne — {line.label}"
                    )
                )
            else:
                reversal.add_line(
                    JournalLine.debit_line(
                        line.account, line.credit, f"Extourne — {line.label}"
                    )
                )
        return reversal

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_balance(self) -> None:
        """Check that sum(debits) == sum(credits).

        Raises:
            ImbalancedEntryError: On imbalance or empty entry.
        """
        if not self._lines:
            raise ImbalancedEntryError(
                f"Entry {self.reference!r} has no lines."
            )
        total_debit = sum(
            (line.debit.amount for line in self._lines), Decimal("0")
        )
        total_credit = sum(
            (line.credit.amount for line in self._lines), Decimal("0")
        )
        if total_debit != total_credit:
            diff = abs(total_debit - total_credit)
            raise ImbalancedEntryError(
                f"Entry {self.reference!r} is imbalanced: "
                f"debits={total_debit:.2f}  credits={total_credit:.2f}  "
                f"difference={diff:.2f}"
            )

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------

    @property
    def lines(self) -> list[JournalLine]:
        """Read-only view of the entry's lines.

        Returns:
            A copy of the internal line list.
        """
        return list(self._lines)

    @property
    def is_posted(self) -> bool:
        """True if the entry has been posted (and is therefore immutable)."""
        return self._posted

    @property
    def total_debit(self) -> Decimal:
        """Sum of all debit amounts on this entry."""
        return sum((line.debit.amount for line in self._lines), Decimal("0"))

    @property
    def total_credit(self) -> Decimal:
        """Sum of all credit amounts on this entry."""
        return sum((line.credit.amount for line in self._lines), Decimal("0"))

    def __iter__(self) -> Iterator[JournalLine]:
        return iter(self._lines)

    def __len__(self) -> int:
        return len(self._lines)

    def __str__(self) -> str:
        header = (
            f"[{self.journal_code}] {self.date}  "
            f"Ref: {self.reference}  "
            f"{'[POSTED]' if self._posted else '[DRAFT]'}"
        )
        lines = "\n".join(f"  {line}" for line in self._lines)
        footer = (
            f"  {'':10} {'TOTAL':40} D {self.total_debit:.2f}  "
            f"C {self.total_credit:.2f}"
        )
        return f"{header}\n{lines}\n{footer}"
