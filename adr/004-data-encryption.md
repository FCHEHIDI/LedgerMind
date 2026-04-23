# ADR-004 — Stratégie de chiffrement des données

| Champ       | Valeur                      |
|-------------|-----------------------------|
| Date        | 2026-04-23                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

LedgerMind stocke des données financières et personnelles sensibles soumises au RGPD
et aux obligations comptables françaises :

- **SIREN/SIRET** — identifiant légal de l'entreprise (donnée personnelle si entreprise
  individuelle)
- **Montants comptables** — données commercialement sensibles
- **Coordonnées fournisseurs** — noms, emails, adresses
- **Fichiers PDF de factures** — contenu brut, très sensible

Le RGPD (Art. 32) impose des mesures techniques appropriées. La doctrine CNIL recommande
le chiffrement comme mesure de base pour les données financières.

---

## Décision

### Couche 1 — Chiffrement en transit : TLS 1.3

- **HTTPS obligatoire** en production (Traefik + Let's Encrypt, redirection 80→443)
- **Versions minimales** : TLS 1.2 minimum, TLS 1.3 préféré
- **Cipher suites** : configuration Traefik `seclevel=2` (pas de RC4, pas de 3DES)
- Communication interne Docker : réseau `backend` et `ai` marqués `internal` —
  trafic reste sur l'hôte, pas de chiffrement inter-container (acceptable, même hôte)

### Couche 2 — Chiffrement applicatif PII : django-fernet-fields

Les champs contenant des PII ou données financières utilisent `EncryptedCharField` /
`EncryptedDecimalField` de `django-fernet-fields` (AES-128-CBC + HMAC-SHA256) :

```python
from fernet_fields import EncryptedCharField, EncryptedTextField

class Invoice(TenantModel):
    vendor_name    = EncryptedCharField(max_length=255)
    vendor_siren   = EncryptedCharField(max_length=14)
    ht_amount      = EncryptedCharField(max_length=20)   # stocké comme string
    tva_amount     = EncryptedCharField(max_length=20)
    ttc_amount     = EncryptedCharField(max_length=20)
    raw_text       = EncryptedTextField(blank=True)      # texte extrait du PDF
```

**Champs NON chiffrés** (nécessaires pour les index/requêtes) :
- `id` (UUID), `org_id`, `created_at`, `status`, `reference` (ref interne opaque)

**Clé Fernet** : variable d'environnement `FERNET_KEY`, jamais en base.
Rotation de clé : procédure de re-chiffrement documentée dans `ops/key-rotation.md`.

### Couche 3 — Chiffrement au repos : fichiers PDF (MinIO/S3)

- **Dev (MinIO)** : volume Docker chiffré au niveau OS si Full Disk Encryption activé
- **Prod (AWS S3 eu-west-3)** : SSE-KMS avec clé gérée par AWS KMS, rotation annuelle
  automatique
- **Nommage des objets** : `{org_id}/{uuid}.pdf` — jamais le nom original du fichier

```python
# Pas : facture_ACME_janvier_2024.pdf
# Oui : 550e8400-e29b-41d4-a716-446655440000/3f2504e0-4f89-11d3-9a0c-0305e82c3301.pdf
```

### Couche 4 — Chiffrement base de données : PostgreSQL

- Chiffrement disque au niveau OS (Full Disk Encryption sur le serveur)
- `pg_hba.conf` : connexions locales uniquement (pas de connexions réseau directes
  depuis l'extérieur du réseau Docker)
- Mots de passe hashés : `PBKDF2 + SHA256` (Django default) pour `auth_user`

---

## Ce qui N'est PAS chiffré au niveau applicatif

- Métadonnées de traitement : `created_at`, `updated_at`, `status`, `job_id`
- Logs système (les logs ne contiennent pas de données sensibles — cf. ADR-005)

---

## Alternatives rejetées

**Chiffrement transparent PostgreSQL (pgcrypto)** : requiert des requêtes SQL modifiées
partout, pas transparent pour l'ORM Django. `django-fernet-fields` est plus maintenable.

**Chiffrement au niveau colonne PostgreSQL uniquement** : dépendant du moteur de DB,
moins portable, pas de protection si la base est exfiltrée avec les clés serveur.

---

## Conséquences

**Positives :**
- Conformité RGPD Art. 32 documentée et auditée
- Compromission de la DB sans la `FERNET_KEY` = données illisibles
- Argument de vente pour cabinets comptables (données chiffrées bout en bout)

**Négatives / risques :**
- `EncryptedCharField` ne supporte pas `filter()` sur valeur chiffrée — requêtes par
  `vendor_siren` impossibles directement. Mitigation : index sur un hash HMAC du SIREN
  pour les recherches (hash déterministe, non-réversible).
- Chiffrement applicatif + chiffrement disque = légère surcharge CPU (< 5% acceptable)
- **Non-réversible** : modifier le schéma après coup pour ajouter `EncryptedField`
  nécessite une migration avec re-chiffrement de toutes les lignes existantes.
