# ADR-010 — Export FEC (Fichier des Écritures Comptables)

| Champ       | Valeur                      |
|-------------|------------------------------|
| Date        | 2026-04-25                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

Le **Fichier des Écritures Comptables (FEC)** est une obligation légale française
imposée par l'article **L47 A du Livre des Procédures Fiscales (LPF)**, applicable
à toute entreprise soumise à l'impôt sur les bénéfices (IS ou BIC) qui tient une
comptabilité informatisée.

En cas de vérification de comptabilité, l'entreprise doit remettre son FEC à
l'administration fiscale (DGFiP) dans les **15 jours** suivant la demande.

**Un FEC invalide (format incorrect, données manquantes, déséquilibres) est
passible d'une amende de 5 000 € par exercice contrôlé.**

LedgerMind doit produire un FEC conforme à la norme DGFiP à la demande.

---

## Décision

### Format FEC — Spécification DGFiP

Le FEC est un **fichier texte** avec :
- **Encodage** : ISO-8859-1 (latin-1) ou UTF-8 avec BOM — LedgerMind produit UTF-8
- **Séparateur** : pipe `|` (caractère 0x7C)
- **Terminateur de ligne** : CRLF (`\r\n`)
- **Première ligne** : en-tête avec les 18 noms de colonnes
- **Nom du fichier** : `{SIREN}FEC{AAAAMMJJ}.txt` (ex: `000000001FEC20261231.txt`)

### Les 18 colonnes obligatoires

| # | Nom | Description | Type | Exemple |
|---|-----|-------------|------|---------|
| 1 | JournalCode | Code du journal | Alphanum. 6 | ACH |
| 2 | JournalLib | Libellé du journal | Alphanum. 99 | Achats |
| 3 | EcritureNum | Numéro de l'écriture | Alphanum. 10 | 2026-001 |
| 4 | EcritureDate | Date de l'écriture | AAAAMMJJ | 20260425 |
| 5 | CompteNum | Numéro de compte | Alphanum. 20 | 401ACME |
| 6 | CompteLib | Libellé du compte | Alphanum. 99 | Fournisseurs - ACME |
| 7 | CompAuxNum | Numéro compte auxiliaire | Alphanum. 20 | ACME (ou vide) |
| 8 | CompAuxLib | Libellé compte auxiliaire | Alphanum. 99 | ACME Corp (ou vide) |
| 9 | PieceRef | Référence pièce justificative | Alphanum. 99 | FACT-2026-001 |
| 10 | PieceDate | Date de la pièce | AAAAMMJJ | 20260420 |
| 11 | EcritureLib | Libellé de l'écriture | Alphanum. 99 | Facture ACME avril |
| 12 | Debit | Montant débit | Décimal | 1200.00 |
| 13 | Credit | Montant crédit | Décimal | 0.00 |
| 14 | EcritureLet | Lettrage de l'écriture | Alphanum. 3 | AA1 (ou vide) |
| 15 | DateLet | Date du lettrage | AAAAMMJJ | (ou vide) |
| 16 | ValidDate | Date de validation | AAAAMMJJ | 20260425 |
| 17 | Montantdevise | Montant en devise | Décimal | (ou vide) |
| 18 | Idevise | Identifiant devise | Alphanum. 3 | (ou vide) |

**Notes importantes :**
- Colonnes 7-8 (CompAuxNum/CompAuxLib) : obligatoires si le compte collectif (CompteNum)
  a des sous-comptes tiers (401, 411). Vides pour les autres comptes.
- Colonnes 12 (Debit) et 13 (Credit) : **jamais les deux à zéro** sur la même ligne.
  Le zéro est représenté par `0.00`, pas vide.
- Colonne 16 (ValidDate) : date à laquelle l'écriture est passée en `posted`.

### Exemples de lignes FEC

```
JournalCode|JournalLib|EcritureNum|EcritureDate|CompteNum|CompteLib|CompAuxNum|CompAuxLib|PieceRef|PieceDate|EcritureLib|Debit|Credit|EcritureLet|DateLet|ValidDate|Montantdevise|Idevise
ACH|Achats|2026-001|20260425|401ACME|Fournisseurs - ACME Corp|ACME|ACME Corp|FACT-2026-001|20260420|Facture ACME avril 2026|0.00|1200.00|||20260425||
ACH|Achats|2026-001|20260425|44566|TVA déductible 20%|||FACT-2026-001|20260420|Facture ACME avril 2026|200.00|0.00|||20260425||
ACH|Achats|2026-001|20260425|604|Prestations de services|||FACT-2026-001|20260420|Facture ACME avril 2026|1000.00|0.00|||20260425||
```

### Endpoint API

```
GET /api/v1/journal/export/fec/
    ?from=2026-01-01
    &to=2026-12-31
    [&format=csv]          # csv (défaut) ou json (pour prévisualisation)

Authorization: Bearer <token>
Rôles requis : org_admin, org_owner, auditor

# Réponse (Content-Disposition: attachment):
Content-Type: text/plain; charset=utf-8
Content-Disposition: attachment; filename="000000001FEC20261231.txt"

# Le SIREN dans le nom de fichier = SIREN de l'organisation
# (décrypté depuis Invoice ou stocké en clair sur Organization)
```

### Règles de génération

1. **Seules les écritures `status=posted`** sont incluses (ADR-009)
   → jamais d'écriture `draft` ou `cancelled` dans le FEC
2. **Tri** : par `EcritureDate` ASC, puis `EcritureNum` ASC
3. **Numérotation** : `EcritureNum` = `reference` du `JournalEntry`
   → le format `YYYY-NNN` (ex: `2026-001`) doit être unique par exercice
4. **Comptes auxiliaires** : si `account_code` commence par `401` ou `411`,
   les colonnes 7-8 sont renseignées avec le suffixe et le nom du tiers
5. **Montants** : toujours 2 décimales, point comme séparateur (`1200.00`),
   jamais de signe négatif (débit/crédit sont sur des colonnes séparées)
6. **Période clôturée** : si l'exercice est clôturé, le FEC est figé
   (hash SHA-256 calculé et stocké pour intégrité)

### Contrôle d'intégrité FEC

Avant remise au DGFiP, vérifier :
- ∑ Debit = ∑ Credit sur l'ensemble du FEC (balance générale)
- Pas de ligne avec Debit=0.00 ET Credit=0.00
- EcritureNum unique par exercice comptable
- EcritureDate dans la plage déclarée
- Pas de caractère pipe `|` dans les libellés

L'API expose un endpoint de validation :
```
GET /api/v1/journal/export/fec/validate/
    ?from=2026-01-01&to=2026-12-31

# Réponse :
{
  "is_valid": true,
  "total_lines": 42,
  "total_debit": "156000.00",
  "total_credit": "156000.00",
  "balance_ok": true,
  "errors": []
}
```

### Stockage du FEC produit

- Les FEC générés sont **archivés sur MinIO/S3** : `{org_id}/fec/{YYYYMMDD}_{hash8}.txt`
- Durée de conservation : **10 ans** (obligation légale)
- Le hash SHA-256 du fichier est stocké en DB pour preuve d'intégrité
- Accès via URL présignée (15 min) — jamais de lien public permanent (ADR-004)

---

## Alternatives rejetées

**Format XLS/XLSX** : non conforme DGFiP — le format légal est obligatoirement
texte pipe-separated.

**Inclure les écritures draft** : rejeté — le FEC représente la comptabilité
définitivement validée. Des brouillons constitueraient une erreur comptable grave.

**Export à la volée sans stockage** : rejeté — l'archivage du FEC produit est
nécessaire pour prouver qu'aucune modification rétroactive n'a eu lieu après export.

---

## Conséquences

**Positives :**
- Conformité DGFiP garantie (format, contenu, archivage)
- Argument commercial fort : "FEC prêt en 1 clic pour le contrôle fiscal"
- Le hash d'intégrité prouve l'absence de modification post-export

**Négatives / risques :**
- Le SIREN de l'organisation doit être stocké (au moins en hash ou via une donnée
  vérifiable) pour nommer correctement le fichier FEC
- La génération du FEC déchiffre les montants (via django-fernet-fields) — opération
  CPU intensive pour les grandes organisations (> 100k lignes) → endpoint asynchrone
  à prévoir pour les gros volumes (retour job_id + webhook/polling)
- Les écritures doivent avoir une numérotation `EcritureNum` unique par exercice —
  la génération automatique de cette référence doit être définie dès la création
  (séquence DB par org+exercice)
