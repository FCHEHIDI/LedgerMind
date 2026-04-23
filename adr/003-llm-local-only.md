# ADR-003 — LLM local uniquement (Ollama, zéro API externe pour les données)

| Champ       | Valeur                      |
|-------------|-----------------------------|
| Date        | 2026-04-23                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

LedgerMind traite des factures contenant des données strictement confidentielles :
SIREN/SIRET, raisons sociales, montants, TVA, coordonnées bancaires (à terme).
Ces données sont soumises au RGPD, au secret professionnel comptable (art. 226-13 CP)
et potentiellement au secret des affaires.

Les LLM SaaS (OpenAI, Anthropic, Google, Mistral API cloud) traitent les prompts
sur leurs infrastructures. Même avec des engagements contractuels sur la non-rétention,
l'envoi de données clients vers des serveurs tiers est :

1. Juridiquement risqué (base légale RGPD incertaine, transferts hors UE)
2. Commercialement disqualifiant pour les cabinets comptables (devoir de confidentialité)
3. Opérationnellement dépendant (rate limits, coûts variables, indisponibilité)

---

## Décision

**Tous les appels LLM impliquant du contenu de factures ou de données clients
passent EXCLUSIVEMENT par Ollama en local.**

### Modèles retenus

| Usage | Modèle | Taille | Contexte |
|-------|--------|--------|----------|
| Extraction structurée (factures) | `qwen2.5:7b` | 4.7 GB | 32k tokens |
| Raisonnement comptable | `mistral:7b-instruct` | 4.1 GB | 8k tokens |
| Classification documents | `qwen2.5:3b` | 1.9 GB | 32k tokens |

### Architecture Ollama dans LedgerMind

```
Celery worker (réseau ai)
    │
    ▼
ollama:11434  (réseau ai, internal — pas d'accès Internet)
    │
    ├── /api/generate  (streaming)
    └── /api/chat      (JSON structured output)
```

Ollama est sur le réseau Docker `ai` marqué `internal: true` — il n'a **physiquement
pas accès à Internet**, même si un bug applicatif tentait un appel externe.

### Seules exceptions autorisées (sans données clients)

- Téléchargement des modèles Ollama en phase de setup (`ollama pull`) — déclenché
  manuellement par l'opérateur, jamais de manière automatique en production
- Embeddings anonymisés pour le RAG (vecteurs uniquement, pas de texte brut source)
  → acceptable uniquement si le fournisseur signe un DPA conforme RGPD Art.28

### Règle de code — linter

Un check CI vérifie l'absence d'imports `openai`, `anthropic`, `google.generativeai`
dans `backend/` et `lab/` :

```yaml
# .github/workflows/ci.yml — job séparé "llm-policy-check"
- name: No external LLM imports
  run: |
    if grep -r "import openai\|import anthropic\|from openai\|from anthropic" \
       backend/ lab/ --include="*.py"; then
      echo "VIOLATION: external LLM API import detected"
      exit 1
    fi
```

---

## Alternatives rejetées

**Mistral API cloud** : géré en UE (Paris), mais données quittent notre infrastructure.
Option de migration acceptable post-MVP si le client signe un DPA et consent
explicitement.

**Azure OpenAI (EU)** : même problématique + coût + vendor lock-in Microsoft.

**Hébergement GPU dédié (RunPod, Lambda Labs)** : viable en prod avancée si Ollama
local devient insuffisant. Requiert audit de sécurité supplémentaire.

---

## Conséquences

**Positives :**
- Conformité RGPD native — les données ne quittent jamais le datacenter client
- Aucun coût variable LLM (prévisibilité budgétaire)
- Fonctionnement offline complet
- Argument commercial fort pour les cabinets comptables

**Négatives / risques :**
- Inférence plus lente que GPT-4 sur CPU (mitigation : GPU en prod, async Celery)
- Modèles 7B moins performants sur des raisonnements complexes
- Mises à jour des modèles manuelles (pas de "latest" automatique)
- RAM/VRAM requises sur le serveur de production (minimum 16 GB RAM, 8 GB VRAM recommandé)
