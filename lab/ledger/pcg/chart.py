"""
Plan Comptable Général (PCG 2025) — chart of accounts.

This module provides:
  - CHART: dict[str, Account] mapping account number → Account object
  - get(number): retrieve an account by number (raises if unknown)
  - resolve(number): fuzzy lookup — exact match first, then parent lookup

Only the most commonly used accounts are listed here for the lab.
The production version will load from a PostgreSQL table.

Source: PCG annexé au règlement ANC n°2014-03, mis à jour 2025.
"""

from __future__ import annotations

from ..domain.account import Account

# ---------------------------------------------------------------------------
# Raw account definitions: (number, label)
# ---------------------------------------------------------------------------

_RAW: list[tuple[str, str]] = [
    # ------------------------------------------------------------------ Classe 1
    ("101", "Capital social"),
    ("104", "Primes liées au capital social"),
    ("106", "Réserves"),
    ("110", "Report à nouveau (solde créditeur)"),
    ("119", "Report à nouveau (solde débiteur)"),
    ("120", "Résultat de l'exercice (bénéfice)"),
    ("129", "Résultat de l'exercice (perte)"),
    ("163", "Emprunts obligataires"),
    ("164", "Emprunts auprès des établissements de crédit"),
    ("165", "Dépôts et cautionnements reçus"),
    # ------------------------------------------------------------------ Classe 2
    ("211", "Terrains"),
    ("213", "Constructions"),
    ("215", "Installations techniques, matériel et outillage industriels"),
    ("218", "Autres immobilisations corporelles"),
    ("281", "Amortissements des immobilisations corporelles"),
    ("205", "Concessions, brevets, licences, marques"),
    ("206", "Droit au bail"),
    ("280", "Amortissements des immobilisations incorporelles"),
    # ------------------------------------------------------------------ Classe 3
    ("310", "Stocks de matières premières et fournitures"),
    ("350", "Stocks de produits intermédiaires et finis"),
    ("370", "Stocks de marchandises"),
    # ------------------------------------------------------------------ Classe 4
    ("401", "Fournisseurs"),
    ("404", "Fournisseurs d'immobilisations"),
    ("408", "Fournisseurs — factures non parvenues"),
    ("411", "Clients"),
    ("413", "Clients — effets à recevoir"),
    ("418", "Clients — produits non encore facturés"),
    ("421", "Personnel — rémunérations dues"),
    ("431", "Sécurité sociale"),
    ("437", "Autres organismes sociaux"),
    ("441", "État — subventions à recevoir"),
    ("444", "État — impôt sur les bénéfices"),
    ("445", "État — taxes sur le chiffre d'affaires"),
    ("44566", "TVA déductible sur ABS et services"),
    ("44571", "TVA collectée"),
    ("44572", "TVA sur encaissements"),
    ("44576", "TVA sur acquisitions intracommunautaires"),
    ("447", "Autres impôts, taxes et versements assimilés"),
    ("455", "Associés — comptes courants"),
    ("467", "Autres comptes débiteurs ou créditeurs"),
    # ------------------------------------------------------------------ Classe 5
    ("511", "Valeurs à l'encaissement"),
    ("512", "Banque"),
    ("514", "Chèques postaux"),
    ("516", "Titres de placement"),
    ("530", "Caisse"),
    ("580", "Virements internes"),
    # ------------------------------------------------------------------ Classe 6
    ("601", "Achats de matières premières"),
    ("607", "Achats de marchandises"),
    ("608", "Frais accessoires d'achat"),
    ("611", "Sous-traitance générale"),
    ("613", "Locations"),
    ("614", "Charges locatives et de copropriété"),
    ("615", "Entretien et réparations"),
    ("616", "Primes d'assurances"),
    ("617", "Études et recherches"),
    ("618", "Divers"),
    ("621", "Personnel extérieur à l'entreprise"),
    ("622", "Rémunérations d'intermédiaires et honoraires"),
    ("623", "Publicité, publications, relations publiques"),
    ("624", "Transports de biens et transports collectifs du personnel"),
    ("625", "Déplacements, missions et réceptions"),
    ("626", "Frais postaux et de télécommunications"),
    ("627", "Services bancaires et assimilés"),
    ("628", "Divers"),
    ("631", "Impôts, taxes et versements assimilés sur rémunérations"),
    ("635", "Autres impôts, taxes et versements assimilés"),
    ("641", "Rémunérations du personnel"),
    ("645", "Charges de sécurité sociale et de prévoyance"),
    ("648", "Autres charges de personnel"),
    ("651", "Redevances pour concessions, brevets, licences"),
    ("661", "Charges d'intérêts"),
    ("671", "Charges exceptionnelles sur opérations de gestion"),
    ("681", "Dotations aux amortissements, dépréciations et provisions — charges d'exploitation"),
    ("695", "Impôts sur les bénéfices"),
    # ------------------------------------------------------------------ Classe 7
    ("701", "Ventes de produits finis"),
    ("706", "Prestations de services"),
    ("707", "Ventes de marchandises"),
    ("708", "Produits des activités annexes"),
    ("709", "Rabais, remises et ristournes accordés"),
    ("741", "Subventions d'exploitation"),
    ("751", "Redevances pour concessions, brevets, licences"),
    ("761", "Produits de participations"),
    ("764", "Revenus des valeurs mobilières de placement"),
    ("771", "Produits exceptionnels sur opérations de gestion"),
    ("781", "Reprises sur amortissements, dépréciations et provisions"),
    ("791", "Transferts de charges d'exploitation"),
]

# ---------------------------------------------------------------------------
# Build the chart
# ---------------------------------------------------------------------------

CHART: dict[str, Account] = {
    number: Account(number=number, label=label)
    for number, label in _RAW
}


def get(number: str) -> Account:
    """Retrieve an account by its exact PCG number.

    Args:
        number: Exact PCG account number (e.g., "512", "44566").

    Returns:
        The Account object.

    Raises:
        KeyError: If the account number is not in the chart.
    """
    try:
        return CHART[number]
    except KeyError:
        raise KeyError(
            f"Account {number!r} not found in PCG chart. "
            "Check the number or add it to lab/ledger/pcg/chart.py."
        ) from None


def resolve(number: str) -> Account:
    """Resolve an account number, falling back to the nearest parent account.

    Tries the exact number first, then progressively shorter prefixes.
    This lets callers use a 6-digit sub-account number even if only the
    3-digit root is defined.

    Args:
        number: PCG account number (may be more specific than chart).

    Returns:
        The most specific Account found.

    Raises:
        KeyError: If no match is found even for the 3-digit prefix.
    """
    for length in range(len(number), 2, -1):
        candidate = number[:length]
        if candidate in CHART:
            return CHART[candidate]
    raise KeyError(
        f"Account {number!r} could not be resolved in the PCG chart "
        "(no match for any prefix of length ≥ 3)."
    )
