"""
GeneralLedger — in-memory ledger (Grand Livre).

Responsibilities:
  1. Accept posted JournalEntries and update per-account running balances.
  2. Enforce the trial balance invariant at any point:
       sum(all debit totals) == sum(all credit totals)
  3. Expose T-account views for individual accounts.
  4. Enforce that only posted entries are accepted (draft entries are rejected).

The GeneralLedger does NOT own the balance invariant of individual entries —
that is JournalEntry.post()'s responsibility. The ledger's job is:
  - accumulate posted facts,
  - remain queryable and consistent at all times.

Design:
  - Append-only: entries are never removed or modified once posted to the ledger.
    Corrections happen via reversal entries appended on top.
  - O(1) balance lookup per account via _balances dict.
  - O(n) trial balance verification across all accounts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .entry import JournalEntry


# ---------------------------------------------------------------------------
# AccountBalance — running T-account totals
# ---------------------------------------------------------------------------


@dataclass
class AccountBalance:
    """Running debit/credit totals for a single account.

    Args:
        account_number: PCG account number.
        account_label: Human-readable label (from first entry seen).

    Note:
        balance = debit_total - credit_total
          positive → debit balance (normal for actif and charges)
          negative → credit balance (normal for passif and produits)
    """

    account_number: str
    account_label: str
    debit_total: Decimal = field(default=Decimal("0"))
    credit_total: Decimal = field(default=Decimal("0"))

    @property
    def balance(self) -> Decimal:
        """Net balance (positive = debit balance, negative = credit balance).

        Returns:
            debit_total - credit_total.
        """
        return self.debit_total - self.credit_total

    def __str__(self) -> str:
        bal = self.balance
        side = "D" if bal >= Decimal("0") else "C"
        return (
            f"{self.account_number:<10} {self.account_label:<40} "
            f"D:{self.debit_total:>12.2f}  C:{self.credit_total:>12.2f}  "
            f"Solde: {abs(bal):>12.2f} {side}"
        )


# ---------------------------------------------------------------------------
# GeneralLedger
# ---------------------------------------------------------------------------


class GeneralLedger:
    """Append-only in-memory general ledger.

    Usage:
        ledger = GeneralLedger()
        ledger.post(entry)              # add a posted JournalEntry
        bal = ledger.balance("512")     # get account 512 balance
        ok  = ledger.verify()           # True if ledger is internally consistent
    """

    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []
        self._balances: dict[str, AccountBalance] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def post(self, entry: JournalEntry) -> None:
        """Post a JournalEntry to the ledger and update all account balances.

        Args:
            entry: A posted JournalEntry (entry.is_posted must be True).

        Raises:
            ValueError: If the entry has not been posted yet.
        """
        if not entry.is_posted:
            raise ValueError(
                f"Entry {entry.reference!r} must be posted (call entry.post()) "
                "before adding it to the ledger."
            )

        self._entries.append(entry)

        for line in entry.lines:
            acc_num = line.account.number
            if acc_num not in self._balances:
                self._balances[acc_num] = AccountBalance(
                    account_number=acc_num,
                    account_label=line.account.label,
                )
            bal = self._balances[acc_num]
            bal.debit_total += line.debit.amount
            bal.credit_total += line.credit.amount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def balance(self, account_number: str) -> Decimal:
        """Return the net balance of a single account.

        Positive means debit balance, negative means credit balance.

        Args:
            account_number: PCG account number string.

        Returns:
            Decimal balance (0 if the account has never been posted to).
        """
        if account_number not in self._balances:
            return Decimal("0")
        return self._balances[account_number].balance

    def account_balance(self, account_number: str) -> AccountBalance | None:
        """Return the full AccountBalance object for an account.

        Args:
            account_number: PCG account number string.

        Returns:
            AccountBalance or None if not found.
        """
        return self._balances.get(account_number)

    def trial_balance(self) -> dict[str, AccountBalance]:
        """Return the trial balance (balance de vérification).

        Returns:
            Dict mapping account_number → AccountBalance, sorted by account.
        """
        return dict(sorted(self._balances.items()))

    @property
    def entries(self) -> list[JournalEntry]:
        """Defensive copy of all posted entries.

        Returns:
            List of JournalEntry objects.
        """
        return list(self._entries)

    # ------------------------------------------------------------------
    # Invariant verification
    # ------------------------------------------------------------------

    def verify(self) -> bool:
        """Verify the global trial balance invariant.

        The fundamental accounting equation requires that across the entire
        ledger, the sum of all debit totals equals the sum of all credit totals.
        If this returns False, the ledger has been corrupted.

        Returns:
            True if sum(all debits) == sum(all credits), False otherwise.
        """
        total_debit = sum(
            b.debit_total for b in self._balances.values()
        )
        total_credit = sum(
            b.credit_total for b in self._balances.values()
        )
        return total_debit == total_credit

    def verify_or_raise(self) -> None:
        """Like verify(), but raises on failure.

        Raises:
            RuntimeError: If the global trial balance is broken.
        """
        total_debit = sum(b.debit_total for b in self._balances.values())
        total_credit = sum(b.credit_total for b in self._balances.values())
        if total_debit != total_credit:
            raise RuntimeError(
                f"LEDGER INTEGRITY ERROR: global trial balance is broken. "
                f"total_debit={total_debit:.2f}  total_credit={total_credit:.2f}  "
                f"diff={abs(total_debit - total_credit):.2f}"
            )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_trial_balance(self) -> None:
        """Print the trial balance to stdout in tabular form."""
        print(f"\n{'BALANCE DE VERIFICATION':=^80}")
        print(
            f"{'Compte':<10} {'Libellé':<40} "
            f"{'Débit':>14} {'Crédit':>14} {'Solde':>14}"
        )
        print("-" * 96)

        total_d = Decimal("0")
        total_c = Decimal("0")

        for _, ab in sorted(self._balances.items()):
            bal = ab.balance
            side = "D" if bal >= Decimal("0") else "C"
            print(
                f"{ab.account_number:<10} {ab.account_label:<40} "
                f"{ab.debit_total:>14.2f} {ab.credit_total:>14.2f} "
                f"{abs(bal):>12.2f} {side}"
            )
            total_d += ab.debit_total
            total_c += ab.credit_total

        print("-" * 96)
        diff = total_d - total_c
        ok = "✓ EQUILIBRE" if diff == Decimal("0") else "✗ DESEQUILIBRE"
        print(
            f"{'TOTAUX':<51} "
            f"{total_d:>14.2f} {total_c:>14.2f} "
            f"  {ok}"
        )
        print()

    def __repr__(self) -> str:
        return (
            f"GeneralLedger("
            f"entries={len(self._entries)}, "
            f"accounts={len(self._balances)}, "
            f"balanced={self.verify()})"
        )
