"""
Account — value object representing a PCG account.

The Plan Comptable Général (PCG 2025) organises accounts by their first digit:

    1 — Capitaux (passif long terme: capital, réserves, emprunts LT)
    2 — Immobilisations (actif immobilisé: matériel, brevets, dépôts)
    3 — Stocks (actif circulant)
    4 — Tiers (clients 411, fournisseurs 401, État/TVA 445x)
    5 — Financiers (banque 512, caisse 530, emprunts CT)
    6 — Charges (résultat: achats, salaires, loyers)
    7 — Produits (résultat: ventes, prestations)

Business rules enforced here:
  - Account number must be purely numeric (no letters, no spaces).
  - Minimum 3 digits (e.g., 512 is valid; 51 is not a leaf account).
  - First digit must be 1–7 (PCG classes only).

The "debit-normal" convention:
  - Actif (1…5) and Charges (6): normal balance is DEBIT.
  - Passif (1) and Produits (7): normal balance is CREDIT.
  Note: class 4 contains both debit-normal (411 Clients) and
  credit-normal (401 Fournisseurs) accounts. At this level of abstraction
  we classify the whole class as ACTIF/debit-normal; specific accounts
  can override via subclass or metadata in the PCG chart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .exceptions import InvalidAccountError


class AccountClass(Enum):
    """The 7 PCG classes."""
    CAPITAUX = 1
    IMMOBILISATIONS = 2
    STOCKS = 3
    TIERS = 4
    FINANCIERS = 5
    CHARGES = 6
    PRODUITS = 7


class AccountNature(Enum):
    """High-level accounting nature used for balance-sheet classification."""
    ACTIF = auto()
    PASSIF = auto()
    CHARGE = auto()
    PRODUIT = auto()


# Default nature per PCG class (simplified; specific accounts may differ)
_NATURE_BY_CLASS: dict[AccountClass, AccountNature] = {
    AccountClass.CAPITAUX: AccountNature.PASSIF,
    AccountClass.IMMOBILISATIONS: AccountNature.ACTIF,
    AccountClass.STOCKS: AccountNature.ACTIF,
    AccountClass.TIERS: AccountNature.ACTIF,    # 411 Clients (debit-normal)
    AccountClass.FINANCIERS: AccountNature.ACTIF,
    AccountClass.CHARGES: AccountNature.CHARGE,
    AccountClass.PRODUITS: AccountNature.PRODUIT,
}


@dataclass(frozen=True)
class Account:
    """An immutable accounting account (compte du PCG).

    Args:
        number: PCG account number (numeric string, min 3 digits, first digit 1–7).
        label: Human-readable account label (e.g., "Banque").

    Raises:
        InvalidAccountError: If number fails PCG validation rules.
    """

    number: str
    label: str

    def __post_init__(self) -> None:
        self._validate_number(self.number)

    @staticmethod
    def _validate_number(number: str) -> None:
        """Validate a PCG account number.

        Args:
            number: The account number string to validate.

        Raises:
            InvalidAccountError: On any validation failure.
        """
        if not isinstance(number, str) or not number:
            raise InvalidAccountError(
                f"Account number must be a non-empty string, got {number!r}"
            )
        if not number.isdigit():
            raise InvalidAccountError(
                f"Account number must contain only digits, got {number!r}"
            )
        if len(number) < 3:
            raise InvalidAccountError(
                f"Account number must have at least 3 digits, got {number!r}"
            )
        first_digit = int(number[0])
        if first_digit < 1 or first_digit > 7:
            raise InvalidAccountError(
                f"First digit must be 1–7 (PCG classes), got {number!r}"
            )

    # ------------------------------------------------------------------
    # Derived properties — computed from the account number
    # ------------------------------------------------------------------

    @property
    def account_class(self) -> AccountClass:
        """PCG class (1–7) derived from the first digit.

        Returns:
            The AccountClass enum value.

        Raises:
            InvalidAccountError: If the first digit is not a valid PCG class.
        """
        first_digit = int(self.number[0])
        try:
            return AccountClass(first_digit)
        except ValueError:
            raise InvalidAccountError(
                f"No PCG class for account {self.number!r} (first digit: {first_digit})"
            )

    @property
    def nature(self) -> AccountNature:
        """Accounting nature (ACTIF, PASSIF, CHARGE, PRODUIT).

        Returns:
            The AccountNature for this account's class.
        """
        return _NATURE_BY_CLASS[self.account_class]

    @property
    def is_debit_normal(self) -> bool:
        """True when the positive (natural) balance is a debit balance.

        Debit-normal accounts: Actif (2, 3, 4, 5) and Charges (6).
        Credit-normal accounts: Passif (1) and Produits (7).

        Returns:
            bool
        """
        return self.nature in (AccountNature.ACTIF, AccountNature.CHARGE)

    @property
    def is_balance_sheet(self) -> bool:
        """True for classes 1–5 (bilan), False for 6–7 (résultat).

        Returns:
            bool
        """
        return self.account_class.value <= 5

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.number} — {self.label}"

    def __repr__(self) -> str:
        return f"Account(number={self.number!r}, label={self.label!r})"
