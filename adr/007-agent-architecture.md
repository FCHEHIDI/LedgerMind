# ADR-007 — Architecture des agents IA (LangGraph)

| Champ       | Valeur                      |
|-------------|------------------------------|
| Date        | 2026-04-25                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

LedgerMind repose sur un graphe d'agents spécialisés qui collaborent pour automatiser
les workflows comptables. Chaque agent est un nœud LangGraph avec un rôle précis,
des outils définis, et des transitions d'état explicites.

La complexité des workflows comptables (OCR → extraction → écriture → rapprochement →
conformité → rapport) rend un agent monolithique inadapté : il serait trop large pour
un modèle 7B, difficile à tester, et impossible à observer en cas d'erreur.

---

## Décision

### Principe général

**Un agent = une responsabilité = un modèle LLM adapté à sa tâche.**

Tous les agents partagent :
- Un **état commun** (`AgentState` TypedDict) passé de nœud en nœud
- Des **outils MCP** pour interagir avec le système (DB, MinIO, PDF)
- Un **LLM local Ollama** — jamais d'appel cloud (ADR-003)
- Un **traçage OpenTelemetry** — chaque appel agent est un span observable

### Graphe d'agents

```
                    ┌───────────────────────┐
                    │  Conversation          │
                    │  Orchestrator (8)      │
                    │  mistral:7b-instruct   │
                    └──────────┬────────────┘
                               │ routing
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ Doc Intake   │    │ Accounting   │    │ Admin        │
  │ Agent (1)    │    │ Reasoner (2) │    │ Workflow (4) │
  │ qwen2.5:7b   │    │ mistral:7b   │    │ mistral:7b   │
  └──────┬───────┘    └──────┬───────┘    └──────────────┘
         │                   │
         ▼                   ▼
  ┌──────────────┐    ┌──────────────┐
  │ Knowledge    │    │ Bank Recon.  │
  │ Graph (7)    │    │ Agent (3)    │
  │ qwen2.5:3b   │    │ qwen2.5:7b   │
  └──────────────┘    └──────┬───────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
             ┌──────────────┐  ┌──────────────┐
             │ Compliance & │  │ Scheduler    │
             │ Audit (6)    │  │ Agent (9)    │
             │ mistral:7b   │  │ (no LLM)     │
             └──────────────┘  └──────────────┘
```

### Les 9 agents — spécification

#### Agent 1 — Document Intake
- **Déclencheur** : nouveau `ProcessingJob` (status=queued)
- **Responsabilité** : OCR, extraction structurée, validation SIREN
- **Modèle** : `qwen2.5:7b` (fort en extraction structurée JSON)
- **Outils MCP** :
  - `read_document(invoice_id)` → PDF bytes depuis MinIO
  - `update_invoice(invoice_id, data)` → mise à jour champs extraits
  - `update_job_status(job_id, status, error_code?)` → traçabilité
- **Sortie** : `Invoice` enrichi (status=extracted) → déclenche Agent 2
- **Prompt strategy** : few-shot avec 10 exemples de factures françaises
  (format Factur-X, PDF natif, scan)

#### Agent 2 — Accounting Reasoner
- **Déclencheur** : `Invoice` status=extracted
- **Responsabilité** : déduction des comptes PCG, génération écriture équilibrée
- **Modèle** : `mistral:7b-instruct` (meilleur raisonnement logique)
- **Outils MCP** :
  - `get_invoice(invoice_id)` → données facture
  - `get_account_plan(org_id)` → plan comptable de l'org (ADR-008)
  - `create_journal_entry(entry)` → crée JournalEntry + AccountEntry
  - `lookup_counterpart(siren_hash)` → trouve/crée compte auxiliaire fournisseur
- **Règles hardcodées** (non LLM) :
  - TVA 20% → 44566, TVA 10% → 44567, TVA 5.5% → 44568
  - Achat matériel → 2154, achat marchandises → 60700, services → 604
  - Vente → 70xxx (à préciser selon nature)
- **Sortie** : `JournalEntry` (status=draft) lié à l'Invoice

#### Agent 3 — Bank Reconciliation
- **Déclencheur** : import relevé bancaire ou scheduled (quotidien)
- **Responsabilité** : matching écriture ↔ mouvement bancaire
- **Modèle** : `qwen2.5:7b` (matching fuzzy avec contexte)
- **Algorithme** :
  1. Matching exact : même montant ± 0.01€ + même date ± 3 jours
  2. Matching LLM : si étape 1 échoue, LLM décide sur libellé + montant
  3. Non réconcilié : flag dans dashboard
- **Outils MCP** :
  - `list_bank_movements(org_id, date_range)` → mouvements compte 512
  - `list_unreconciled_entries(org_id)` → écritures non lettrées
  - `reconcile(entry_id, movement_id)` → lettrage

#### Agent 4 — Admin Workflow
- **Déclencheur** : demande utilisateur via Conversation Orchestrator
- **Responsabilité** : génération documents administratifs
- **Cas d'usage** :
  - Relance fournisseur (email automatique)
  - Attestation de paiement
  - Déclaration TVA mensuelle
  - Rappel d'échéances fiscales (IS, CFE, TVA)
- **Modèle** : `mistral:7b-instruct`
- **Outils MCP** : `generate_pdf(template, data)`, `send_email(to, subject, body)`

#### Agent 6 — Compliance & Audit
- **Déclencheur** : scheduled (hebdomadaire) ou demande explicite
- **Responsabilité** : vérifications de cohérence comptable
- **Contrôles** :
  - Balance des comptes équilibrée (∑ débits = ∑ crédits)
  - TVA collectée vs TVA déductible (cohérence CA déclaré)
  - Détection d'écritures sans pièce justificative
  - Comptes fournisseurs/clients non lettrés > 90 jours
  - Contrôle FEC : format conforme DGFiP (ADR-010)
- **Sortie** : rapport PDF + alertes dashboard

#### Agent 7 — Knowledge Graph
- **Déclencheur** : après chaque Invoice extracté ou JournalEntry créé
- **Responsabilité** : maintenance du graphe entités (Neo4j)
- **Nœuds** : Organization, Supplier, Client, Invoice, JournalEntry, BankAccount
- **Arêtes** : ISSUED_BY, PAID_TO, LINKED_TO, RECONCILED_WITH
- **Usage** : détection de patterns (même fournisseur, montants récurrents),
  mémoire longue durée pour l'Orchestrateur

#### Agent 8 — Conversation Orchestrator
- **Déclencheur** : message utilisateur (interface chat)
- **Responsabilité** : comprendre l'intention, router vers le bon agent,
  synthétiser les réponses
- **Modèle** : `mistral:7b-instruct`
- **Pattern** : ReAct (Reasoning + Acting) avec outils de routing
- **Exemples de routing** :
  - "Montre-moi les factures impayées" → Agent 3 (rapprochement)
  - "Génère la déclaration TVA de mars" → Agent 4 (admin)
  - "Y a-t-il des anomalies dans la compta ?" → Agent 6 (conformité)

#### Agent 9 — Scheduler
- **Type** : Celery Beat (pas de LLM — orchestration temporelle pure)
- **Tâches récurrentes** :

| Fréquence | Tâche |
|-----------|-------|
| Quotidien | Import relevés bancaires, rapprochement auto |
| Hebdomadaire | Rapport conformité + alertes |
| Mensuel | Clôture TVA, rappels échéances |
| À la demande | Toutes les tâches ci-dessus |

### État partagé (AgentState)

```python
class AgentState(TypedDict):
    # Contexte tenant
    org_id: str
    user_id: str

    # Document en cours
    invoice_id: Optional[str]
    job_id: Optional[str]

    # Données extraites
    extracted_data: Optional[dict]       # sortie Agent 1
    journal_entry_id: Optional[str]      # sortie Agent 2
    reconciliation_result: Optional[dict] # sortie Agent 3

    # Contrôle de flux
    current_step: str
    errors: list[str]
    warnings: list[str]
    requires_human_review: bool
```

### Observabilité des agents

Chaque appel LLM est tracé via OpenTelemetry :
```
span: agent.doc_intake.extract
  ├── model: qwen2.5:7b
  ├── duration_ms: 4200
  ├── tokens_in: 1843
  ├── tokens_out: 312
  ├── invoice_id: <uuid>          # identifiant opaque
  └── success: true
```

**Jamais de données métier dans les traces** (ADR-005).

---

## Alternatives rejetées

**Agent unique monolithique** : trop large pour un modèle 7B (contexte limité),
impossible à déboguer, pas de spécialisation par tâche.

**AutoGPT / Agent loop infini** : imprévisible, impossible à auditer (requis pour
la conformité comptable).

**OpenAI Assistants API** : violation ADR-003.

---

## Conséquences

**Positives :**
- Chaque agent est testable indépendamment
- Le graphe LangGraph permet de visualiser et rejouer les workflows
- Spécialisation des modèles = meilleure qualité par tâche
- Observabilité fine via OpenTelemetry

**Négatives / risques :**
- Complexité opérationnelle accrue (9 agents à maintenir)
- Les erreurs de l'Agent 1 (extraction) se propagent à l'Agent 2 (écriture) —
  nécessité d'un mécanisme de correction humaine entre les étapes
- RAM requise : 3 modèles chargés simultanément = ~15 GB RAM (mitigation : chargement
  à la demande avec cache LRU sur Ollama)
