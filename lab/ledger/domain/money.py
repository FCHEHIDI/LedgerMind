"""
Money — immutable value object for monetary amounts.

Design decisions:
  - Uses decimal.Decimal, never float. Float arithmetic on money is a
    critical bug: 0.1 + 0.2 == 0.30000000000000004 in IEEE 754.
  - Quantized to 2 decimal places (centimes) on construction with
    ROUND_HALF_UP (standard French rounding rule).
  - Frozen dataclass: Money is a value object. Two Money instances with
    the same amount and currency are equal and interchangeable.
  - Currency is validated as a 3-letter ISO 4217 code.

Usage:
    m = Money.of("1200.00")          # EUR by default
    m = Money.of(1200, "USD")
    total = Money.of("1000") + Money.of("200")  # Money(1200.00, EUR)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .exceptions import CurrencyMismatchError, NegativeAmountError

# Quantization target: 2 decimal places
_CENT = Decimal("0.01")

# ISO 4217 currency code pattern
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Money:
    """Immutable monetary amount with currency.

    Args:
        amount: Decimal amount (quantized to 2 decimal places).
        currency: ISO 4217 currency code (default: "EUR").

    Raises:
        ValueError: If currency code is not a valid ISO 4217 format.
        TypeError: If amount cannot be converted to Decimal.
    """

    amount: Decimal
    currency: str = "EUR"

    def __post_init__(self) -> None:
        if not _CURRENCY_RE.match(self.currency):
            raise ValueError(
                f"Currency must be a 3-letter ISO 4217 code, got {self.currency!r}"
            )
        # Quantize using object.__setattr__ because dataclass is frozen
        quantized = self.amount.quantize(_CENT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def of(cls, amount: str | int | float | Decimal, currency: str = "EUR") -> Money:
        """Create a Money from any numeric type.

        Args:
            amount: The monetary amount. Strings like "1200.50" are preferred
                    over floats to avoid IEEE 754 precision issues.
            currency: ISO 4217 code (default: "EUR").

        Returns:
            A new Money instance.

        Raises:
            ValueError: If the string cannot be parsed as a Decimal.
        """
        return cls(Decimal(str(amount)), currency)

    @classmethod
    def zero(cls, currency: str = "EUR") -> Money:
        """Return a zero-valued Money for the given currency.

        Args:
            currency: ISO 4217 code (default: "EUR").

        Returns:
            Money(0.00, currency).
        """
        return cls(Decimal("0.00"), currency)

    # ------------------------------------------------------------------
    # Arithmetic — always returns a new Money (immutable)
    # ------------------------------------------------------------------

    def _check_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot combine {self.currency} and {other.currency}"
            )

    def __add__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: int | Decimal) -> Money:
        return Money(self.amount * Decimal(str(factor)), self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __abs__(self) -> Money:
        return Money(abs(self.amount), self.currency)

    # ------------------------------------------------------------------
    # Comparisons
    # ------------------------------------------------------------------

    def __lt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount >= other.amount

    def is_zero(self) -> bool:
        """Return True if the amount is exactly zero."""
        return self.amount == Decimal("0.00")

    def is_positive(self) -> bool:
        """Return True if the amount is strictly positive."""
        return self.amount > Decimal("0.00")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"

    def __repr__(self) -> str:
        return f"Money(amount={self.amount!r}, currency={self.currency!r})"
