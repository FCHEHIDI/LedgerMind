# LedgerMind

> Plateforme d'orchestration comptable & administrative LLM-native.

Un mini cabinet comptable + un mini Terraform Cloud + un mini Datadog,
orchestres par des agents IA collaboratifs.

---

## Pitch

LedgerMind automatise les workflows comptables, administratifs et infrastructurels
via un graphe d'agents LangGraph, des MCP servers Rust, un RAG 2.0 et un
orchestrateur d'evenements.

Cas d'usage reels : factures, TVA, rapprochements bancaires, paie, contrats,
provisioning cloud, audit interne, conformite.

---

## Architecture

```
Frontend (Next.js)
    |
Backend API (FastAPI)
    |
Agent Orchestrator (LangGraph)
    |  |  |  |  |  |  |  |  |
  [9 agents specialises]
    |
MCP Servers (Rust) <-> PostgreSQL . MinIO . Redis . Neo4j
```

| Couche | Technologie |
|--------|-------------|
| Frontend | Next.js (dashboard + workflows) |
| Backend API | FastAPI (Python) |
| Orchestration IA | LangGraph + LangChain |
| MCP Servers | Rust (Axum) |
| RAG | vecteurs + graph DB + chunking semantique |
| Stockage | PostgreSQL . MinIO . Redis . Neo4j |
| Observabilite | Prometheus . Grafana . OpenTelemetry |
| Infra | Docker Compose -> Kubernetes |

---

## Les 9 agents (LangGraph)

| # | Agent | Responsabilite |
|---|-------|----------------|
| 1 | Document Intake | OCR, classification, extraction structuree (Pydantic + LLM), envoi RAG |
| 2 | Accounting Reasoner | Detection comptes PCG, generation ecritures, validation TVA/amortissements |
| 3 | Bank Reconciliation | Rapprochement automatique, detection anomalies, matching fuzzy + LLM |
| 4 | Admin Workflow | Generation contrats/attestations/relances/emails, gestion deadlines fiscales |
| 5 | Infrastructure | Provisioning cloud via MCP, backups, snapshots, rotation logs |
| 6 | Compliance & Audit | Coherence comptable, analyse risques, rapport PDF d'audit |
| 7 | Knowledge Graph | Graphe entites (clients, fournisseurs, transactions, contrats), memoire longue duree |
| 8 | Conversation Orchestrator | Interface utilisateur, reformulation, routing vers les bons agents |
| 9 | Scheduler | Orchestration temporelle, workflows recurrents, gestion dependances |

---

## Les 6 MCP Servers (Rust)

| # | Serveur | Responsabilite |
|---|---------|----------------|
| 1 | Filesystem & Document Store | CRUD MinIO, versioning, signatures cryptographiques |
| 2 | PostgreSQL Ledger | Transactions ACID, tables comptables, stored procedures (pgrx) |
| 3 | Bank Connector | Fichiers OFX/CSV, normalisation, webhooks bancaires |
| 4 | CloudOps | Provisioning AWS (IAM/S3/EC2), wrapper Terraform, monitoring hooks |
| 5 | PDF & Reporting | Generation PDF (typst/printpdf), templates dynamiques, export comptable |
| 6 | Compliance Engine | Regles metier, detection anomalies, audit logs |

---

## Les 5 services applicatifs

| Service | Responsabilite |
|---------|----------------|
| Ledger API | CRUD comptable, ecritures, rapprochements, exports FEC |
| AdminFlow | Generation documents, signatures electroniques, emails automatises |
| InfraOps | Provisioning, monitoring, backups |
| RAG Engine | Indexation, retrieval hybride, Graph RAG |
| Agent Orchestrator | LangGraph, state machine, observabilite agents |

---

## Les 3 workflows demonstrateurs

### Workflow 1 — Traitement d'une facture
```
Upload PDF -> OCR + extraction -> Classification -> Ecriture comptable
    -> Rapprochement bancaire -> Archivage -> Audit -> Rapport PDF
```

### Workflow 2 — Provisioning cloud
```
"Cree un env staging pour le client X"
    -> CloudOps genere plan Terraform
    -> Compliance valide
    -> InfraOps deploie
    -> Rapport final
```

### Workflow 3 — Audit comptable automatique
```
Analyse incoherences -> Verification TVA -> Detection anomalies -> Rapport PDF
```

---

## Plan de developpement (lab -> prod)

| Phase | Invariant | Ce qu'on construit dans le lab |
|-------|-----------|-------------------------------|
| 1 | Ledger | Double-entry accounting, PCG, ecritures ACID, balance, FEC |
| 2 | Graph | LangGraph state machine, nodes, tool routing, 2-3 agents |
| 3 | Intake | Pipeline PDF -> OCR -> extraction structuree Pydantic |
| 4 | RAG | Chunking, embeddings, retrieval hybride sur docs comptables |
| 5 | MCP | MCP server Rust minimaliste + agent Python qui l'appelle |
| 6 | Workflow | Workflow facture complet : les 5 invariants assembles |

Chaque invariant est explore dans lab/, compris, puis reproduit a l'echelle dans src/.
