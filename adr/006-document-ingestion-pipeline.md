# ADR-006 — Pipeline d'ingestion documentaire

| Champ       | Valeur                      |
|-------------|------------------------------|
| Date        | 2026-04-25                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

Le cœur de la proposition de valeur de LedgerMind est la transformation automatique
d'un document brut (PDF facture, scan papier, export CSV bancaire) en écriture comptable
validée dans le journal. Ce pipeline doit être :

- **Traçable** : chaque étape est auditée (qui, quand, quel résultat)
- **Réversible** : une erreur d'extraction peut être corrigée manuellement sans
  perdre le document source
- **Asynchrone** : les PDFs volumineux ou les LLM locaux (ADR-003) peuvent prendre
  plusieurs secondes — pas de blocage HTTP
- **Isolé par tenant** : aucune donnée d'un tenant ne transite vers un autre (ADR-001)

---

## Décision

### Étapes du pipeline

```
[Document entrant]
       │  POST /api/v1/documents/upload/
       ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE 1 — INGESTION                               │
│  • Création Invoice (status=pending)               │
│  • Création ProcessingJob (status=queued)          │
│  • Stockage fichier : MinIO → {org_id}/{uuid}.pdf  │
│  • Tâche Celery déclenchée (job_id)                │
└──────────────────────────┬──────────────────────────┘
                           │ Celery worker (async)
                           ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE 2 — OCR + EXTRACTION (Agent: DocIntake)     │
│  • OCR via pymupdf (texte natif) ou tesseract      │
│    (scan image) → raw_text (EncryptedTextField)    │
│  • Appel LLM local Ollama qwen2.5:7b               │
│    → extraction structurée Pydantic :              │
│      vendor_name, vendor_siren, ht_amount,         │
│      tva_amount, ttc_amount, invoice_date,         │
│      invoice_reference                             │
│  • Validation SIREN via API SIRENE (INSEE)         │
│    → champ vendor_siren_verified: bool             │
│  • ProcessingJob status → processing               │
└──────────────────────────┬──────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE 3 — COMPTABILISATION (Agent: AccountReas.)  │
│  • Déduction des comptes PCG depuis le type de     │
│    document (ACH/VTE/OD) et le régime TVA          │
│  • Génération JournalEntry (status=draft)          │
│    + lignes AccountEntry équilibrées               │
│    (débit = crédit = ttc_amount)                  │
│  • Compte auxiliaire fournisseur : 401 + suffix    │
│    dérivé du SIREN hash (ex. 401A3F2) — ADR-008   │
│  • Lien Invoice ↔ JournalEntry                    │
│  • Invoice status → extracted                      │
└──────────────────────────┬──────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE 4 — DÉTECTION DE DOUBLONS                   │
│  • Hash HMAC(vendor_siren + ttc_amount + date)     │
│    comparé aux Invoice existantes du tenant        │
│  • Si doublon détecté : ProcessingJob status →     │
│    warning + flag Invoice.is_duplicate = True      │
│  • L'écriture est quand même créée (draft) mais    │
│    signalée pour validation humaine                │
└──────────────────────────┬──────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE 5 — VALIDATION HUMAINE (Interface)          │
│  • Tableau de bord : écritures draft à valider     │
│  • Opérateur révise / corrige comptes              │
│  • Action "Valider" → status posted                │
│  • Action "Rejeter" → status cancelled             │
│  • ProcessingJob status → completed                │
└──────────────────────────┬──────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE 6 — RAPPROCHEMENT BANCAIRE (Agent: BankRec) │
│  • Matching automatique avec relevés bancaires     │
│    (import OFX/CSV compte 512)                     │
│  • Règles : montant exact ± 0.01€ + fenêtre J±3   │
│  • Si match : lettre l'écriture (flag reconciled)  │
│  • Si pas de match : alerte dans le dashboard      │
└─────────────────────────────────────────────────────┘
```

### Modèles de statut

**Invoice.status**
```
pending → extracted → reconciled
              ↓
           rejected (si doublon confirmé ou rejet manuel)
```

**ProcessingJob.status**
```
queued → processing → completed
                   → failed (avec error_code, sans données métier — ADR-005)
                   → warning (doublon détecté, validation requise)
```

**JournalEntry.status**
```
draft → posted
     → cancelled
```

### Stockage des fichiers

- **Dev** : MinIO (`lm-documents` bucket, réseau Docker interne)
- **Prod** : AWS S3 `eu-west-3`, SSE-KMS, versioning activé (ADR-004)
- **Nommage** : `{org_id}/{invoice_uuid}.pdf` — jamais le nom original
- **Rétention** : 10 ans minimum (obligation légale archivage comptable français)
- **Accès** : URLs présignées à durée limitée (15 min) — pas d'accès public

### Gestion des erreurs

| Erreur | Comportement |
|--------|-------------|
| OCR échoue (PDF illisible) | ProcessingJob status=failed, error_code=OCR_FAILED |
| LLM retourne JSON invalide | Retry x3 avec prompt différent, puis status=failed |
| SIREN invalide (checksum Luhn) | vendor_siren_verified=False, pipeline continue |
| SIREN inexistant (SIRENE API) | warning + flag, pipeline continue |
| Montants incohérents (HT+TVA≠TTC) | status=warning, erreur affichée en dashboard |
| Écriture déséquilibrée | Bloquant — pipeline s'arrête à l'étape 3 |

---

## Alternatives rejetées

**Pipeline synchrone (HTTP)** : inacceptable car l'inférence LLM locale peut prendre
10-30s sur CPU. Le client ne peut pas attendre dans une requête HTTP.

**Stockage local filesystem** : non scalable, non redondant, incompatible avec
déploiement multi-instance.

**OCR cloud (AWS Textract, Google Vision)** : violation ADR-003 — les PDFs contiennent
des données clients qui ne doivent pas quitter l'infrastructure.

---

## Conséquences

**Positives :**
- Traçabilité complète de chaque document (audit trail)
- Résilience : les erreurs LLM ne perdent pas le document source
- Scalable : les workers Celery sont horizontalement scalables

**Négatives / risques :**
- Latence pipeline complet : 10-60s selon CPU/GPU disponible
- Dépendance Celery + Redis en production
- La qualité de l'extraction LLM détermine la qualité des écritures comptables —
  nécessite des tests de régression sur corpus de factures réels
