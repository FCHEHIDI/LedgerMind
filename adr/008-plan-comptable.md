# ADR-008 — Plan Comptable Général (PCG) et comptes auxiliaires

| Champ       | Valeur                      |
|-------------|------------------------------|
| Date        | 2026-04-25                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

La comptabilité française est régie par le **Plan Comptable Général (PCG)**, normalisé
par l'Autorité des Normes Comptables (ANC). LedgerMind doit :

1. Imposer les comptes PCG comme base (numérotation obligatoire)
2. Permettre la création de **sous-comptes analytiques** par les cabinets
3. Gérer les **comptes auxiliaires de tiers** (fournisseurs 401, clients 411)
4. Permettre à l'agent de comptabilisation (ADR-007, Agent 2) de déduire
   automatiquement les bons comptes

---

## Décision

### Structure de numérotation des comptes

La France utilise un plan à **chiffres décimaux** avec les classes suivantes :

| Classe | Nature |
|--------|--------|
| 1 | Capitaux propres, emprunts |
| 2 | Immobilisations |
| 3 | Stocks |
| 4 | Tiers (fournisseurs, clients, État) |
| 5 | Financiers (banque, caisse) |
| 6 | Charges |
| 7 | Produits |

**Comptes collectifs** (présents dans le PCG officiel) :
- Minimum 2 chiffres, typiquement 3-5 : `401`, `41100`, `60700`
- Tronqués à gauche si la classe suffit : `401` pour "Fournisseurs"

**Comptes analytiques** (optionnels, définis par l'org) :
- Extension du compte collectif : `6070001` (sous-compte de `60700`)
- Conservent la hiérarchie PCG

### Convention des comptes auxiliaires de tiers

Les comptes 401 (fournisseurs) et 411 (clients) sont des **comptes collectifs** qui
doivent être **subdivisés par tiers** dans les journaux auxiliaires.

**Règle LedgerMind** : `{compte_collectif}{code_auxiliaire}`

| Compte collectif | Suffixe | Exemple complet |
|------------------|---------|-----------------|
| `401` | `ACME` | `401ACME` |
| `401` | `001` | `401001` |
| `411` | `DUPONT` | `411DUPONT` |

**Règles de formation du suffixe :**
- Alphanumérique uniquement, majuscules
- 2 à 8 caractères
- Pas d'espaces ni de caractères spéciaux
- Dérivé soit : du nom commercial tronqué, soit d'un identifiant interne

**Génération automatique par l'Agent 2 :**
- Source : `HMAC-SHA256(FERNET_KEY, vendor_siren)[:6].upper()`
  → garantit déterminisme (même fournisseur = même code), même sans stocker le SIREN
  en clair dans le code du compte
- L'opérateur peut remplacer par un code lisible (`ACME`) dans l'interface

### Modèle de données

```python
class AccountPlan(TenantModel):
    """Compte du plan comptable de l'organisation."""
    code        = models.CharField(max_length=20)    # "401ACME"
    label       = models.CharField(max_length=255)   # "Fournisseurs - ACME Corp"
    account_type = models.CharField(
        max_length=20,
        choices=[
            ("collective", "Compte collectif"),      # 401, 411, 512…
            ("auxiliary",  "Compte auxiliaire"),     # 401ACME, 411DUPONT…
            ("analytic",   "Compte analytique"),     # 60700001…
        ]
    )
    parent_code = models.CharField(max_length=20, blank=True)  # "401" pour "401ACME"
    is_active   = models.BooleanField(default=True)

    class Meta:
        unique_together = [("org_id", "code")]


class Counterpart(TenantModel):
    """Tiers (fournisseur ou client) associé à un compte auxiliaire."""
    auxiliary_code  = models.CharField(max_length=20)   # "ACME" (sans le collectif)
    collective_code = models.CharField(max_length=10)   # "401" ou "411"
    legal_name      = EncryptedCharField(max_length=255)
    siren           = EncryptedCharField(max_length=14, blank=True)
    siren_hash      = models.CharField(max_length=64, db_index=True)  # HMAC recherche
    counterpart_type = models.CharField(
        max_length=10,
        choices=[("supplier", "Fournisseur"), ("customer", "Client")]
    )

    @property
    def full_account_code(self) -> str:
        return f"{self.collective_code}{self.auxiliary_code}"
```

### Comptes PCG pré-chargés (seed)

À la création d'une organisation, LedgerMind pré-charge les comptes PCG de niveau 3
les plus fréquents pour les PME françaises :

| Code | Libellé |
|------|---------|
| 101 | Capital social |
| 164 | Emprunts auprès des établissements de crédit |
| 215 | Installations, matériels et outillages industriels |
| 218 | Autres immobilisations corporelles |
| 401 | Fournisseurs |
| 404 | Fournisseurs d'immobilisations |
| 411 | Clients |
| 419 | Clients créditeurs |
| 421 | Personnel – Rémunérations dues |
| 431 | Sécurité sociale |
| 437 | Autres organismes sociaux |
| 441 | État – Impôts sur les bénéfices |
| 4456 | TVA déductible |
| 4457 | TVA collectée |
| 44566 | TVA déductible sur autres biens et services (20%) |
| 44567 | TVA déductible sur autres biens et services (10%) |
| 44568 | TVA déductible sur autres biens et services (5.5%) |
| 512 | Banques |
| 530 | Caisse |
| 601 | Achats de matières premières |
| 604 | Achats d'études et prestations de services |
| 606 | Achats non stockés de matières et fournitures |
| 607 | Achats de marchandises |
| 613 | Locations |
| 615 | Entretien et réparations |
| 616 | Primes d'assurances |
| 622 | Rémunérations d'intermédiaires et honoraires |
| 623 | Publicité, publications, relations publiques |
| 625 | Déplacements, missions et réceptions |
| 626 | Frais postaux et frais de télécommunications |
| 627 | Services bancaires et assimilés |
| 641 | Rémunérations du personnel |
| 645 | Charges de sécurité sociale et de prévoyance |
| 671 | Charges exceptionnelles sur opérations de gestion |
| 701 | Ventes de produits finis |
| 706 | Prestations de services |
| 707 | Ventes de marchandises |
| 771 | Produits exceptionnels sur opérations de gestion |

### Règles de déduction automatique (Agent 2)

L'Agent de comptabilisation utilise ces règles en priorité décroissante :

1. **Règle historique** : si le même fournisseur (siren_hash) a déjà été comptabilisé
   avec un compte spécifique → réutiliser (apprentissage par l'exemple)
2. **Règle TVA** : taux TVA détecté → compte 4456x correspondant
3. **Règle de nature** :

| Mots-clés facture | Compte débit suggéré |
|-------------------|---------------------|
| "loyer", "location" | 613 |
| "honoraires", "consultant" | 622 |
| "assurance" | 616 |
| "téléphone", "internet" | 626 |
| "voyages", "transport" | 625 |
| "matériel", "équipement" | 2154 (si > seuil amortissement) ou 606 |
| "marchandises" | 607 |
| défaut | 604 (prestations de services) |

4. **Fallback** : si aucune règle ne correspond, écriture draft avec compte `604`
   et flag `requires_human_review=True`

---

## Phase MVP — Validation souple

Pour le MVP, la validation des codes de compte est **souple** :
- L'API accepte n'importe quel `account_code` de 2 à 20 caractères alphanumériques
- Un warning (non-bloquant) est retourné si le code n'est pas dans l'`AccountPlan`
  de l'organisation
- Le contrôle strict (refus) ne sera activé que lorsque le modèle `AccountPlan`
  sera complètement implémenté et peuplé

---

## Alternatives rejetées

**Numérotation libre sans PCG** : incompatible avec l'export FEC (ADR-010) qui
impose la numérotation PCG. Incompatible avec les contrôles DGFiP.

**Comptes auxiliaires numériques uniquement (401001, 401002)** : moins lisible pour
les comptables habitués aux codes courts (ACME, DUPONT). Les deux formats sont acceptés.

---

## Conséquences

**Positives :**
- Conformité PCG/ANC dès la conception
- Export FEC compatible DGFiP (ADR-010)
- Auto-complétion des comptes dans l'interface (meilleure UX)
- L'agent de comptabilisation peut apprendre de l'historique par organisation

**Négatives / risques :**
- La table `AccountPlan` doit être pré-peuplée à la création de l'org (migration)
- Les PME avec un plan comptable personnalisé devront importer leur plan
  (fonctionnalité future)
