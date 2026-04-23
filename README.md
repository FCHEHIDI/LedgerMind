# LedgerMind

> Plateforme SaaS B2B de comptabilité automatisée, LLM-native, conçue pour les cabinets comptables et les PME françaises.

---

## Vision

LedgerMind transforme le traitement des factures en workflow entièrement automatisé : OCR → extraction structurée → validation PCG → écriture comptable → export FEC — le tout piloté par des agents IA locaux (Ollama) sans aucun envoi de données sensibles vers des API tierces.

---

## Architecture cible

```
Frontend (Next.js)
        │
Backend API (Django 5 + DRF)
        │
Agent Orchestrator (LangGraph)
    │   │   │   │
  Intake RAG Graph MCP
        │
  Ollama (Mistral 7B — local)
        │
PostgreSQL · MinIO · Redis
```

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Backend API | Django 5.x + Django REST Framework |
| Orchestration IA | LangGraph + LangChain |
| LLM | Ollama — Mistral 7B / Qwen2.5 (local only) |
| Base de données | PostgreSQL 16 + RLS (Row Level Security) |
| File de tâches | Celery + Redis |
| Stockage fichiers | MinIO (dev) → AWS S3 eu-west-3 (prod) |
| Auth | SimpleJWT (API) + Django session (Admin) |
| Chiffrement PII | django-fernet-fields (SIREN, montants) |
| Multi-tenant | Row-level tenancy via `TenantManager` |

---

## Structure du projet

```
LedgerMind/
  lab/          # Moteur comptable Python — 222 tests ✅
    ledger/     # Inv.1 — Double-entry, PCG, FEC export
    graph/      # Inv.2 — LangGraph invoice validation
    intake/     # Inv.3 — PDF/OCR → extraction structurée
    rag/        # Inv.4 — RAG StubEmbedder + NumpyVectorStore
    mcp/        # Inv.5 — MCP JSON-RPC 2.0, 5 outils
    workflow/   # Inv.6 — Orchestration LangGraph complète
  backend/      # Django SaaS — à venir
  adr/          # Architecture Decision Records — à venir
```

---

## Lab — état des invariants

| Invariant | Module | Tests | Statut |
|-----------|--------|-------|--------|
| Inv.1 | `lab/ledger` | 55/55 | ✅ |
| Inv.2 | `lab/graph` | 27/27 | ✅ |
| Inv.3 | `lab/intake` | 30/30 | ✅ |
| Inv.4 | `lab/rag` | 37/37 | ✅ |
| Inv.5 | `lab/mcp` | 40/40 | ✅ |
| Inv.6 | `lab/workflow` | 33/33 | ✅ |
| **Total** | | **222/222** | **✅** |

---

## Lancer les tests

```bash
python -m pytest lab/ -v
```

---

## Décisions d'architecture clés

- **LLM local uniquement** — Ollama, zéro donnée client envoyée vers OpenAI/Anthropic/Google
- **PostgreSQL RLS** — isolation tenant au niveau base de données, activé dès J1
- **Chiffrement applicatif** — `django-fernet-fields` sur tous les champs PII (SIREN, montants)
- **Zéro donnée sensible dans les logs** — UUIDs opaques seulement, règle de lint
- **Hébergement EU uniquement** — OVH / Scaleway / AWS eu-west-3 (Paris)

---

## Licence

Propriétaire — tous droits réservés.
