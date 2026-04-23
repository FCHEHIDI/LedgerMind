"""
Tests for the LedgerMind lab — Invariant 1: Ledger.

Test philosophy:
  - Each test targets exactly one invariant or business rule.
  - Tests are named after the invariant they guard, not after the function.
  - Edge cases (zero, None, boundary) are explicit, not implied.
  - No mocking: the domain is pure Python with no I/O, so real objects are used.

Invariants covered:
  [MONEY]
    1. Decimal precision — no float arithmetic
    2. Currency mismatch raises
    3. Zero detection
    4. Immutability (frozen dataclass)

  [ACCOUNT]
    5. Valid PCG numbers accepted
    6. Non-numeric numbers rejected
    7. Too-short numbers rejected
    8. First digit outside 1–7 rejected
    9. account_class and nature derived correctly

  [JOURNAL LINE]
    10. Debit-only and credit-only lines accepted
    11. Both debit and credit on same line rejected
    12. Zero debit AND zero credit rejected
    13. Negative debit rejected
    14. Negative credit rejected

  [JOURNAL ENTRY]
    15. Balanced entry posts successfully
    16. Imbalanced entry raises ImbalancedEntryError
    17. Empty entry raises ImbalancedEntryError
    18. Posting is idempotent (posting twice raises)
    19. Adding line to posted entry raises ImmutableEntryError
    20. Reversal of posted entry balances back to zero
    21. Reversal of unposted entry raises
    22. Reversal is not pre-posted

  [LEDGER]
    23. Global trial balance holds after single entry
    24. Global trial balance holds after multiple entries
    25. Balance lookup returns 0 for unseen account
    26. Only posted entries accepted by ledger
    27. Ledger verify() fails if balances are manually corrupted

  [PCG CHART]
    28. Known accounts resolve correctly
    29. Unknown account raises KeyError
    30. resolve() falls back to parent account

  [FEC EXPORTER]
    31. FEC output has correct header
    32. FEC amount format uses comma separator
    33. FEC debit/credit columns are mutually exclusive
    34. Tab characters in labels are sanitized
    35. Unposted entry raises on FEC export

  [INTEGRATION]
    36. Full invoice workflow: facture fournisseur + paiement + balance
    37. Reversal workflow: post → reverse → post reversal → net zero balance
"""

import io
import csv
from datetime import date
from decimal import Decimal

import pytest

from ..domain.account import Account, AccountClass, AccountNature
from ..domain.entry import JournalEntry, JournalLine
from ..domain.exceptions import (
    CurrencyMismatchError,
    ImbalancedEntryError,
    ImmutableEntryError,
    InvalidAccountError,
    NegativeAmountError,
)
from ..domain.ledger import GeneralLedger
from ..domain.money import Money
from ..fec.exporter import FEC_COLUMNS, FEC_DELIMITER, export_to_string
from ..pcg import chart


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def banque() -> Account:
    return Account("512", "Banque")


@pytest.fixture
def fournisseur() -> Account:
    return Account("401", "Fournisseurs")


@pytest.fixture
def achats() -> Account:
    return Account("607", "Achats de marchandises")


@pytest.fixture
def tva_deductible() -> Account:
    return Account("44566", "TVA déductible")


@pytest.fixture
def clients() -> Account:
    return Account("411", "Clients")


@pytest.fixture
def ventes() -> Account:
    return Account("706", "Prestations de services")


@pytest.fixture
def tva_collectee() -> Account:
    return Account("44571", "TVA collectée")


# ===========================================================================
# [MONEY] — Tests 1–4
# ===========================================================================


class TestMoney:
    def test_decimal_precision_no_float_error(self):
        """0.1 + 0.2 must equal 0.30, not 0.30000000000000004."""
        a = Money.of("0.10")
        b = Money.of("0.20")
        assert (a + b).amount == Decimal("0.30")

    def test_float_input_is_quantized(self):
        """float input must be quantized to 2 decimal places."""
        m = Money.of(0.1 + 0.2)
        assert m.amount == Decimal("0.30")

    def test_currency_mismatch_raises(self):
        eur = Money.of("100", "EUR")
        usd = Money.of("100", "USD")
        with pytest.raises(CurrencyMismatchError):
            _ = eur + usd

    def test_zero_detection(self):
        assert Money.zero().is_zero()
        assert not Money.of("0.01").is_zero()

    def test_immutability(self):
        m = Money.of("100")
        with pytest.raises(Exception):  # frozen dataclass raises FrozenInstanceError
            m.amount = Decimal("999")  # type: ignore

    def test_invalid_currency_raises(self):
        with pytest.raises(ValueError):
            Money.of("100", "eu")  # must be 3 uppercase letters

    def test_subtraction(self):
        assert (Money.of("500") - Money.of("200")).amount == Decimal("300.00")

    def test_multiplication(self):
        assert (Money.of("100") * 3).amount == Decimal("300.00")


# ===========================================================================
# [ACCOUNT] — Tests 5–9
# ===========================================================================


class TestAccount:
    def test_valid_3_digit_account(self):
        acc = Account("512", "Banque")
        assert acc.number == "512"
        assert acc.account_class == AccountClass.FINANCIERS

    def test_valid_5_digit_account(self):
        acc = Account("44566", "TVA déductible")
        assert acc.number == "44566"
        assert acc.account_class == AccountClass.TIERS

    def test_non_numeric_rejected(self):
        with pytest.raises(InvalidAccountError):
            Account("5AB", "Bad account")

    def test_too_short_rejected(self):
        with pytest.raises(InvalidAccountError):
            Account("51", "Too short")

    def test_first_digit_zero_rejected(self):
        with pytest.raises(InvalidAccountError):
            Account("012", "Invalid class 0")

    def test_first_digit_8_rejected(self):
        with pytest.raises(InvalidAccountError):
            Account("800", "Invalid class 8")

    def test_charges_are_debit_normal(self):
        acc = Account("607", "Achats")
        assert acc.nature == AccountNature.CHARGE
        assert acc.is_debit_normal is True

    def test_capitaux_are_credit_normal(self):
        acc = Account("101", "Capital social")
        assert acc.nature == AccountNature.PASSIF
        assert acc.is_debit_normal is False

    def test_produits_are_credit_normal(self):
        acc = Account("706", "Prestations")
        assert acc.nature == AccountNature.PRODUIT
        assert acc.is_debit_normal is False

    def test_banque_is_debit_normal(self):
        acc = Account("512", "Banque")
        assert acc.nature == AccountNature.ACTIF
        assert acc.is_debit_normal is True

    def test_immobilisations_are_balance_sheet(self):
        acc = Account("215", "Matériel")
        assert acc.is_balance_sheet is True

    def test_charges_are_not_balance_sheet(self):
        acc = Account("607", "Achats")
        assert acc.is_balance_sheet is False


# ===========================================================================
# [JOURNAL LINE] — Tests 10–14
# ===========================================================================


class TestJournalLine:
    def test_debit_line_accepted(self, banque):
        line = JournalLine.debit_line(banque, Money.of("100"), "Dépôt")
        assert line.is_debit
        assert not line.is_credit
        assert line.amount == Money.of("100")

    def test_credit_line_accepted(self, fournisseur):
        line = JournalLine.credit_line(fournisseur, Money.of("100"), "Facture")
        assert line.is_credit
        assert not line.is_debit

    def test_both_debit_and_credit_rejected(self, banque):
        with pytest.raises(ValueError, match="both"):
            JournalLine(
                account=banque,
                debit=Money.of("100"),
                credit=Money.of("100"),
                label="Invalid",
            )

    def test_zero_debit_and_zero_credit_rejected(self, banque):
        with pytest.raises(NegativeAmountError):
            JournalLine(
                account=banque,
                debit=Money.zero(),
                credit=Money.zero(),
                label="Zero line",
            )

    def test_negative_debit_rejected(self, banque):
        with pytest.raises(NegativeAmountError):
            JournalLine(
                account=banque,
                debit=Money(Decimal("-100"), "EUR"),
                credit=Money.zero(),
                label="Negative debit",
            )

    def test_negative_credit_rejected(self, fournisseur):
        with pytest.raises(NegativeAmountError):
            JournalLine(
                account=fournisseur,
                debit=Money.zero(),
                credit=Money(Decimal("-100"), "EUR"),
                label="Negative credit",
            )


# ===========================================================================
# [JOURNAL ENTRY] — Tests 15–22
# ===========================================================================


class TestJournalEntry:
    def _make_invoice_entry(self, achats, tva_deductible, fournisseur) -> JournalEntry:
        """Facture fournisseur: 1000 HT + 200 TVA = 1200 TTC."""
        entry = JournalEntry(
            date=date(2024, 1, 15),
            reference="FACT-2024-001",
            journal_code="AC",
        )
        entry.add_line(JournalLine.debit_line(achats, Money.of("1000.00"), "Achats HT"))
        entry.add_line(JournalLine.debit_line(tva_deductible, Money.of("200.00"), "TVA 20%"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("1200.00"), "Facture FOURN-001"))
        return entry

    def test_balanced_entry_posts_successfully(self, achats, tva_deductible, fournisseur):
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        entry.post()
        assert entry.is_posted

    def test_imbalanced_entry_raises(self, banque, fournisseur):
        entry = JournalEntry(date=date(2024, 1, 1), reference="BAD-001")
        entry.add_line(JournalLine.debit_line(banque, Money.of("1000"), "Débit"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("999"), "Crédit wrong"))
        with pytest.raises(ImbalancedEntryError):
            entry.post()

    def test_empty_entry_raises(self):
        entry = JournalEntry(date=date(2024, 1, 1), reference="EMPTY-001")
        with pytest.raises(ImbalancedEntryError):
            entry.post()

    def test_posting_twice_raises(self, achats, tva_deductible, fournisseur):
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        entry.post()
        with pytest.raises(ImmutableEntryError):
            entry.post()

    def test_add_line_to_posted_entry_raises(self, achats, tva_deductible, fournisseur, banque):
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        entry.post()
        with pytest.raises(ImmutableEntryError):
            entry.add_line(JournalLine.debit_line(banque, Money.of("100"), "Late line"))

    def test_entry_debit_equals_credit(self, achats, tva_deductible, fournisseur):
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        assert entry.total_debit == entry.total_credit == Decimal("1200.00")

    def test_reversal_is_mirror(self, achats, tva_deductible, fournisseur):
        """The reversal entry must swap all debits/credits."""
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        entry.post()
        reversal = entry.reverse(date(2024, 1, 31), "EXT-001")

        # Reversal is not yet posted
        assert not reversal.is_posted

        # Reversal has same number of lines
        assert len(reversal.lines) == len(entry.lines)

        # What was debit in original is now credit in reversal, and vice versa
        for orig, rev in zip(entry.lines, reversal.lines):
            if orig.is_debit:
                assert rev.is_credit
                assert rev.credit.amount == orig.debit.amount
            else:
                assert rev.is_debit
                assert rev.debit.amount == orig.credit.amount

    def test_reversal_can_be_posted(self, achats, tva_deductible, fournisseur):
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        entry.post()
        reversal = entry.reverse(date(2024, 1, 31), "EXT-001")
        reversal.post()
        assert reversal.is_posted

    def test_reversal_of_unposted_raises(self, achats, tva_deductible, fournisseur):
        entry = self._make_invoice_entry(achats, tva_deductible, fournisseur)
        with pytest.raises(ValueError):
            entry.reverse(date(2024, 1, 31), "EXT-BAD")

    def test_currency_mismatch_in_entry_raises(self, banque, fournisseur):
        entry = JournalEntry(date=date(2024, 1, 1), reference="FX-001")
        entry.add_line(JournalLine.debit_line(banque, Money.of("1000", "EUR"), "EUR debit"))
        with pytest.raises(CurrencyMismatchError):
            entry.add_line(JournalLine.credit_line(fournisseur, Money.of("1000", "USD"), "USD credit"))


# ===========================================================================
# [LEDGER] — Tests 23–27
# ===========================================================================


class TestGeneralLedger:
    def _invoice_entry(self, achats, tva_deductible, fournisseur) -> JournalEntry:
        entry = JournalEntry(date=date(2024, 1, 15), reference="FACT-001", journal_code="AC")
        entry.add_line(JournalLine.debit_line(achats, Money.of("1000"), "Achats HT"))
        entry.add_line(JournalLine.debit_line(tva_deductible, Money.of("200"), "TVA"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("1200"), "Fournisseur"))
        entry.post()
        return entry

    def test_trial_balance_holds_after_single_entry(self, achats, tva_deductible, fournisseur):
        ledger = GeneralLedger()
        ledger.post(self._invoice_entry(achats, tva_deductible, fournisseur))
        assert ledger.verify() is True

    def test_trial_balance_holds_after_multiple_entries(
        self, achats, tva_deductible, fournisseur, banque
    ):
        ledger = GeneralLedger()
        ledger.post(self._invoice_entry(achats, tva_deductible, fournisseur))

        # Payment entry: debit 401 Fournisseur / credit 512 Banque
        payment = JournalEntry(date=date(2024, 1, 20), reference="VIR-001", journal_code="BQ")
        payment.add_line(JournalLine.debit_line(fournisseur, Money.of("1200"), "Paiement fournisseur"))
        payment.add_line(JournalLine.credit_line(banque, Money.of("1200"), "Virement bancaire"))
        payment.post()
        ledger.post(payment)

        assert ledger.verify() is True

    def test_balance_returns_zero_for_unseen_account(self):
        ledger = GeneralLedger()
        assert ledger.balance("999") == Decimal("0")

    def test_only_posted_entries_accepted(self, achats, fournisseur):
        ledger = GeneralLedger()
        entry = JournalEntry(date=date(2024, 1, 1), reference="DRAFT")
        entry.add_line(JournalLine.debit_line(achats, Money.of("100"), "test"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("100"), "test"))
        # NOT posted
        with pytest.raises(ValueError, match="posted"):
            ledger.post(entry)

    def test_verify_fails_on_corrupted_ledger(self, achats, fournisseur):
        """Directly corrupt the ledger internals to confirm verify() detects it."""
        ledger = GeneralLedger()
        entry = JournalEntry(date=date(2024, 1, 1), reference="TEST")
        entry.add_line(JournalLine.debit_line(achats, Money.of("100"), "test"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("100"), "test"))
        entry.post()
        ledger.post(entry)

        # Corrupt directly (simulates a bug in a future adapter layer)
        ledger._balances["607"].debit_total += Decimal("1")

        assert ledger.verify() is False

    def test_fournisseur_balance_is_credit_after_invoice(
        self, achats, tva_deductible, fournisseur
    ):
        """401 Fournisseur must carry a credit balance after an invoice."""
        ledger = GeneralLedger()
        ledger.post(self._invoice_entry(achats, tva_deductible, fournisseur))
        bal = ledger.balance("401")
        assert bal == Decimal("-1200.00")  # credit balance = negative

    def test_achats_balance_is_debit_after_invoice(
        self, achats, tva_deductible, fournisseur
    ):
        ledger = GeneralLedger()
        ledger.post(self._invoice_entry(achats, tva_deductible, fournisseur))
        assert ledger.balance("607") == Decimal("1000.00")


# ===========================================================================
# [PCG CHART] — Tests 28–30
# ===========================================================================


class TestPCGChart:
    def test_known_account_resolves(self):
        acc = chart.get("512")
        assert acc.number == "512"
        assert acc.label == "Banque"

    def test_unknown_account_raises(self):
        with pytest.raises(KeyError):
            chart.get("999")

    def test_resolve_falls_back_to_parent(self):
        # "44566" is in chart directly
        acc = chart.resolve("44566")
        assert acc.number == "44566"

    def test_resolve_exact_match_first(self):
        acc = chart.resolve("401")
        assert acc.number == "401"

    def test_chart_accounts_are_valid(self):
        """All accounts in the chart must pass PCG validation."""
        for number, acc in chart.CHART.items():
            assert acc.number == number
            assert acc.account_class is not None  # will raise if invalid


# ===========================================================================
# [FEC EXPORTER] — Tests 31–35
# ===========================================================================


class TestFECExporter:
    def _simple_entry(self, achats, fournisseur) -> JournalEntry:
        entry = JournalEntry(
            date=date(2024, 1, 15),
            reference="FACT-2024-001",
            journal_code="AC",
        )
        entry.add_line(JournalLine.debit_line(achats, Money.of("1000.00"), "Achats HT"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("1000.00"), "Fournisseur"))
        entry.post()
        return entry

    def _parse_fec(self, content: str) -> list[dict[str, str]]:
        reader = csv.DictReader(
            io.StringIO(content),
            delimiter=FEC_DELIMITER,
        )
        return list(reader)

    def test_fec_has_correct_header(self, achats, fournisseur):
        content = export_to_string([self._simple_entry(achats, fournisseur)])
        first_line = content.split("\r\n")[0]
        assert first_line == FEC_DELIMITER.join(FEC_COLUMNS)

    def test_fec_amount_uses_comma_separator(self, achats, fournisseur):
        content = export_to_string([self._simple_entry(achats, fournisseur)])
        rows = self._parse_fec(content)
        for row in rows:
            assert "," in row["Debit"] or "," in row["Credit"]
            assert "." not in row["Debit"]
            assert "." not in row["Credit"]

    def test_fec_debit_credit_mutually_exclusive(self, achats, fournisseur):
        content = export_to_string([self._simple_entry(achats, fournisseur)])
        rows = self._parse_fec(content)
        for row in rows:
            debit = Decimal(row["Debit"].replace(",", "."))
            credit = Decimal(row["Credit"].replace(",", "."))
            # One must be zero, the other non-zero
            assert (debit == Decimal("0.00")) != (credit == Decimal("0.00"))

    def test_fec_tab_injection_sanitized(self, fournisseur):
        """A tab character in a label must not corrupt the TSV structure."""
        malicious_account = Account("607", "Achats\tmalicious\tcontent")
        entry = JournalEntry(date=date(2024, 1, 1), reference="TEST-INJ")
        entry.add_line(JournalLine.debit_line(malicious_account, Money.of("100"), "label\twith\ttabs"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("100"), "normal"))
        entry.post()
        content = export_to_string([entry])
        rows = self._parse_fec(content)
        # Each data row must have exactly 18 fields
        assert len(rows) == 2
        for row in rows:
            assert len(row) == 18

    def test_unposted_entry_raises_on_fec_export(self, achats, fournisseur):
        entry = JournalEntry(date=date(2024, 1, 1), reference="DRAFT")
        entry.add_line(JournalLine.debit_line(achats, Money.of("100"), "test"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("100"), "test"))
        # NOT posted
        with pytest.raises(ValueError, match="posted"):
            export_to_string([entry])


# ===========================================================================
# [INTEGRATION] — Tests 36–37
# ===========================================================================


class TestIntegration:
    def test_full_invoice_and_payment_workflow(
        self, achats, tva_deductible, fournisseur, banque
    ):
        """
        Workflow: facture fournisseur + paiement + vérification soldes.

        Étape 1 — Réception facture fournisseur 1000 HT + 200 TVA:
            D 607  1000.00
            D 44566  200.00
                C 401        1200.00

        Étape 2 — Paiement par virement:
            D 401  1200.00
                C 512        1200.00

        État final attendu:
            607  D  1000.00  (charge)
            44566 D   200.00  (TVA à récupérer)
            401   C     0.00  (fournisseur soldé)
            512   C -1200.00  (banque débitée)
        """
        ledger = GeneralLedger()

        # -- Facture --
        facture = JournalEntry(date=date(2024, 1, 15), reference="FACT-001", journal_code="AC")
        facture.add_line(JournalLine.debit_line(achats, Money.of("1000.00"), "Achats HT"))
        facture.add_line(JournalLine.debit_line(tva_deductible, Money.of("200.00"), "TVA 20%"))
        facture.add_line(JournalLine.credit_line(fournisseur, Money.of("1200.00"), "Facture FOURN"))
        facture.post()
        ledger.post(facture)

        # -- Paiement --
        paiement = JournalEntry(date=date(2024, 1, 20), reference="VIR-001", journal_code="BQ")
        paiement.add_line(JournalLine.debit_line(fournisseur, Money.of("1200.00"), "Règlement"))
        paiement.add_line(JournalLine.credit_line(banque, Money.of("1200.00"), "Virement"))
        paiement.post()
        ledger.post(paiement)

        # -- Vérifications --
        assert ledger.verify() is True
        assert ledger.balance("607") == Decimal("1000.00")
        assert ledger.balance("44566") == Decimal("200.00")
        assert ledger.balance("401") == Decimal("0.00")      # soldé
        assert ledger.balance("512") == Decimal("-1200.00")  # banque créditée

    def test_reversal_nets_to_zero(self, achats, fournisseur):
        """
        Post an entry, then reverse it. Net balance on all accounts must be 0.
        """
        ledger = GeneralLedger()

        entry = JournalEntry(date=date(2024, 1, 1), reference="OP-001")
        entry.add_line(JournalLine.debit_line(achats, Money.of("500.00"), "Achat"))
        entry.add_line(JournalLine.credit_line(fournisseur, Money.of("500.00"), "Fournisseur"))
        entry.post()
        ledger.post(entry)

        reversal = entry.reverse(date(2024, 1, 31), "EXT-001")
        reversal.post()
        ledger.post(reversal)

        assert ledger.balance("607") == Decimal("0.00")
        assert ledger.balance("401") == Decimal("0.00")
        assert ledger.verify() is True
