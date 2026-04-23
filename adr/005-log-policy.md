# ADR-005 — Politique de journalisation (logs)

| Champ       | Valeur                      |
|-------------|-----------------------------|
| Date        | 2026-04-23                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

Les logs applicatifs sont souvent le vecteur d'une fuite de données non intentionnelle :
un `logger.debug(invoice)` ou `logger.error(f"Failed to process {vendor_name}")` suffit
à exposer des données clients dans des systèmes de log centralisés (Loki, CloudWatch,
Datadog) accessibles à toute l'équipe technique ou à des tiers.

Dans le contexte de LedgerMind (données financières, secret professionnel comptable,
RGPD), cette fuite est inacceptable.

---

## Décision

### Règle absolue — Zéro donnée métier dans les logs

Les éléments suivants ne doivent **jamais** apparaître dans un message de log :

| Catégorie | Exemples interdits |
|-----------|-------------------|
| Identifiants légaux | SIREN, SIRET, numéro TVA, RCS |
| Données financières | montants HT/TTC/TVA, totaux, soldes |
| Identité fournisseur | raison sociale, nom, email, adresse |
| Contenu de facture | référence facture, texte extrait |
| Données utilisateur | email, nom, rôle métier |

### Ce qui est autorisé dans les logs

```python
# ✅ OK — identifiants opaques uniquement
logger.info("invoice.processing.started", extra={
    "invoice_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",  # UUID opaque
    "org_id": "550e8400-e29b-41d4-a716-446655440000",       # UUID opaque
    "job_id": "job_abc123",
    "duration_ms": 142,
})

# ✅ OK — statuts et codes d'erreur
logger.error("invoice.processing.failed", extra={
    "invoice_id": "3f2504e0...",
    "error_code": "REGEX_NO_MATCH",
    "field": "siren",        # nom du champ, pas la valeur
})

# ❌ INTERDIT
logger.debug(f"Processing invoice for {vendor_name}, SIREN: {siren}")
logger.error(f"Amount {ttc_amount} could not be parsed")
```

### Format de log : JSON structuré

```python
# config/settings/base.py
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},  # Pas de SQL en prod
        "lab": {"level": "INFO"},
        "backend": {"level": "INFO"},
    },
}
```

### Niveaux de log par environnement

| Niveau | Dev | Prod |
|--------|-----|------|
| DEBUG  | ✅ (sans données métier) | ❌ |
| INFO   | ✅ | ✅ |
| WARNING | ✅ | ✅ |
| ERROR  | ✅ | ✅ |
| `django.db.backends` (SQL) | WARNING | WARNING |

### Rétention des logs

| Environnement | Stockage | Rétention | Accès |
|---------------|----------|-----------|-------|
| Dev | stdout Docker | Session | Développeur local |
| Staging | Loki (Docker) | 7 jours | Équipe technique |
| Prod | Loki + S3 archivage | 90 jours actifs, 1 an archivé | Équipe technique + audit |

La rétention de 1 an en archivage correspond aux obligations légales de traçabilité
comptable (art. L123-22 Code de commerce).

### Enforcement CI — règle de lint

```yaml
# .github/workflows/ci.yml — job "log-policy-check"
- name: Check no PII in log statements
  run: |
    # Détecte les patterns suspects : logger.*(siren|vendor|amount|ttc|ht|tva)
    if grep -rn \
      -E "log(ger)?\.(debug|info|warning|error|critical).*\b(siren|siret|vendor|amount|ttc|ht_|tva|email|password)\b" \
      backend/ lab/ --include="*.py" -i; then
      echo "POTENTIAL PII IN LOG — review required"
      exit 1
    fi
```

Ce check est intentionnellement strict et peut générer des faux positifs (ex: variable
nommée `tva_rate_field_name`). En cas de faux positif, annoter la ligne avec
`# nocheck-log-policy` et documenter dans la PR.

---

## Alternatives rejetées

**Masquage automatique des PII dans les logs** (librairie scrubadub, etc.) : approche
réactive, la donnée transite quand même en mémoire dans le formateur de log.
Préférer l'approche préventive (ne jamais logger la donnée).

**Logs séparés "sécurisés" pour PII** : complexifie l'architecture, crée un faux
sentiment de sécurité. La règle simple "jamais de PII dans les logs" est plus robuste.

---

## Conséquences

**Positives :**
- Conformité RGPD documentée (Art. 5.1.f — intégrité et confidentialité)
- Logs analysables par toute l'équipe sans risque de voir des données clients
- Audit trail complet via UUIDs opaques sans exposition de données

**Négatives / risques :**
- Debugging plus difficile : on ne voit pas directement quelle facture a échoué.
  Mitigation : corrélation via `invoice_id` UUID dans les outils de monitoring.
- Le check CI peut bloquer sur des noms de variables légitimes — faux positifs
  gérés au cas par cas avec annotation `# nocheck-log-policy`.
