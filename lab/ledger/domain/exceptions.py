"""
Domain exceptions for the LedgerMind ledger.

Hierarchy:
    LedgerError
    ├── ImbalancedEntryError   — sum(debits) != sum(credits)
    ├── ImmutableEntryError    — attempt to mutate a posted entry
    ├── InvalidAccountError    — account number fails PCG validation
    ├── NegativeAmountError    — amount <= 0 where positive is required
    └── CurrencyMismatchError  — mixing currencies in the same entry
"""


class LedgerError(Exception):
    """Base class for all ledger domain errors."""


class ImbalancedEntryError(LedgerError):
    """
    Raised when a journal entry does not satisfy the fundamental invariant:

        sum(debits) == sum(credits)

    This is a hard invariant — an imbalanced entry must NEVER reach the ledger.
    """


class ImmutableEntryError(LedgerError):
    """
    Raised when code attempts to modify a journal entry that has already
    been posted.

    Accounting rule: posted entries are write-once. Corrections are made
    via reversal entries (extournes), never by editing existing entries.
    This preserves the audit trail required by French accounting law (PCG,
    article L123-22 Code de commerce).
    """


class InvalidAccountError(LedgerError):
    """
    Raised when an account number does not conform to PCG rules:
    - Must be purely numeric
    - Must have at least 3 digits
    - First digit must be 1–7

    Risk: accepting arbitrary strings as account numbers would silently
    corrupt the ledger classification (actif/passif/charges/produits).
    """


class NegativeAmountError(LedgerError):
    """
    Raised when a debit or credit amount is negative or zero.

    Risk: negative amounts on individual lines would silently invert the
    accounting polarity of a transaction (e.g., turning a charge into a
    product). All signed arithmetic must happen at the ledger level via
    the debit/credit columns, never by using negative amounts.
    """


class CurrencyMismatchError(LedgerError):
    """
    Raised when two Money values of different currencies are combined in an
    operation that requires them to be the same.

    Risk: implicit currency conversion would introduce exchange-rate errors
    and break the balance invariant silently.
    """
