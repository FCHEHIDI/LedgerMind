# ADR-009 — Workflow de validation des écritures comptables

| Champ       | Valeur                      |
|-------------|------------------------------|
| Date        | 2026-04-25                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

Les agents IA (ADR-007) génèrent des écritures comptables automatiquement, mais
**aucune écriture ne peut être définitivement enregistrée sans validation humaine**.

Ce principe est non-négociable pour deux raisons :
1. **Légale** : le Code de commerce (art. L123-22) impose que les livres comptables
   soient tenus par une personne responsable. Une IA ne peut pas signer une écriture.
2. **Qualité** : les LLM 7B font des erreurs d'affectation de comptes. Un double
   regard humain est obligatoire avant de "poster" une écriture.

---

## Décision

### Machine d'états des écritures

```
                    ┌─────────────┐
                    │   DRAFT     │ ← Créée par Agent 2 ou manuellement
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │ Validation humaine      │
              │ (rôle: accountant+)     │
              ▼                         ▼
       ┌─────────────┐          ┌─────────────┐
       │   POSTED    │          │  CANCELLED  │
       │  (définitif)│          │  (annulée)  │
       └──────┬──────┘          └─────────────┘
              │
              │ Si erreur détectée après posting
              ▼
       ┌─────────────┐
       │  POSTED     │ ← écriture d'extourne créée (nouvelle écriture DRAFT)
       │  (inchangé) │   La correction passe par une contre-écriture
       └─────────────┘
```

**Règle fondamentale : une écriture `posted` est immuable.**
Les erreurs post-posting sont corrigées par **extourne** (écriture inverse + nouvelle
écriture correcte), jamais par modification de l'écriture originale.

### Transitions autorisées par rôle RBAC

| Transition | Rôles autorisés |
|------------|----------------|
| `draft` → `posted` | `accountant`, `org_admin`, `org_owner` |
| `draft` → `cancelled` | `accountant`, `org_admin`, `org_owner` |
| `posted` → extourne (création) | `org_admin`, `org_owner` |
| Créer écriture `draft` | `accountant`, `org_admin`, `org_owner` |
| Lire toutes les écritures | `auditor`, `accountant`, `org_admin`, `org_owner` |

(Rôles définis dans ADR-002)

### Préconditions à la validation (draft → posted)

L'API **refuse** la transition si :
1. **Déséquilibre** : `∑ débits ≠ ∑ crédits` sur l'écriture
2. **Compte invalide** : un `account_code` n'est pas dans l'`AccountPlan` actif
   de l'organisation (si la validation stricte est activée — ADR-008)
3. **Date hors exercice ouvert** : si l'exercice comptable est clôturé
4. **Invoice liée non vérifiée** : si `requires_human_review=True` sur le `ProcessingJob`
   associé (doublon détecté, extraction incertaine)

L'API **autorise** mais émet un **warning** (non-bloquant) si :
- Le compte n'est pas standard PCG (avertissement, pas un refus)
- La date est dans le futur (écriture d'antidatage probable)

### Interface de validation

**Page `/app/ledger`** — Tableau des écritures :
- Badge `DRAFT` en jaune visible → incitation à valider
- Colonne "Alertes" avec icône si `requires_human_review=True`
- Filtre rapide "À valider" (status=draft)

**Page `/app/ledger/[id]`** — Détail de l'écriture :
- Bouton **"Valider l'écriture"** visible si `status=draft` et rôle suffisant
- Bouton **"Annuler"** visible si `status=draft`
- Confirmation modale avant action (irréversible pour `posted`)
- Si validation OK → badge passe en vert `VALIDÉE`, boutons disparaissent
- Si validation KO → message d'erreur explicite (déséquilibre, compte inconnu…)

### Endpoint API

```
PATCH /api/v1/journal/{id}/validate/
Content-Type: application/json
Authorization: Bearer <token>

# Body : aucun (ou optionnellement un commentaire)
{}

# Réponse 200 :
{
  "id": "...",
  "status": "posted",
  "validated_at": "2026-04-25T14:32:00Z",
  "validated_by": "user-uuid"
}

# Réponse 400 (exemples) :
{
  "error": "UNBALANCED_ENTRY",
  "detail": "Débit total (1200.00) ≠ Crédit total (1000.00)"
}
{
  "error": "CLOSED_PERIOD",
  "detail": "L'exercice 2025 est clôturé. Aucune écriture ne peut être postée."
}
```

### Audit trail

Chaque transition de statut est enregistrée dans une table `JournalEntryAudit` :

```python
class JournalEntryAudit(models.Model):
    entry       = models.ForeignKey(JournalEntry, on_delete=models.CASCADE)
    action      = models.CharField(max_length=20)   # "validated", "cancelled", "created"
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)
    # Jamais de données métier (ADR-005)
```

Cette table est incluse dans l'export FEC comme preuve de validation (ADR-010).

### Extourne (correction d'une écriture postée)

```
POST /api/v1/journal/{id}/reverse/
{
  "reason": "Facture annulée par le fournisseur",
  "reversal_date": "2026-04-30"
}

# Crée automatiquement :
# 1. Une écriture DRAFT avec les débits/crédits inversés
# 2. Le lien extourne_of = {id} sur la nouvelle écriture
# L'opérateur doit valider la contre-écriture (workflow standard)
```

---

## Alternatives rejetées

**Validation automatique des écritures générées par les agents** : rejetée pour des
raisons légales (responsabilité comptable) et de qualité (les LLM 7B ne sont pas
fiables à 100% sur les comptes PCG complexes).

**Modification d'une écriture postée** : rejetée pour conformité FEC — le DGFiP
exige que le fichier FEC représente l'état définitif des livres au moment de la
clôture. Des modifications rétroactives rendraient le FEC incohérent.

---

## Conséquences

**Positives :**
- Conformité légale (responsabilité humaine maintenue)
- Audit trail complet pour contrôle fiscal
- L'extourne est le pattern standard en comptabilité française

**Négatives / risques :**
- L'UX doit rendre la validation rapide (pas de friction excessive) pour
  que les utilisateurs ne "postent" pas en masse sans vérifier
- Le volume d'écritures draft peut s'accumuler si les agents tournent
  plus vite que les validations humaines (mitigation : dashboard avec
  compteur d'écritures en attente)
