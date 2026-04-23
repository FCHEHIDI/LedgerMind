# ADR-001 — Modèle de multi-tenancy : Row-Level Security PostgreSQL

| Champ       | Valeur                      |
|-------------|-----------------------------|
| Date        | 2026-04-23                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

LedgerMind est une plateforme SaaS B2B : plusieurs organisations (cabinets comptables,
PME) partagent la même infrastructure. Les données comptables (écritures, factures,
journaux) sont strictement confidentielles — une fuite inter-tenant serait une faute
grave (RGPD, responsabilité civile professionnelle des experts-comptables).

Trois approches existent pour l'isolation tenant :

| Approche | Isolation | Complexité ops | Coût infra |
|----------|-----------|----------------|------------|
| Base de données séparée par tenant | Maximale | Très haute | Élevé |
| Schéma PostgreSQL séparé (django-tenants) | Haute | Haute (migrations x N) | Moyen |
| **Row-Level Security (RLS) + colonne `org_id`** | **Bonne** | **Faible** | **Faible** |

---

## Décision

**Isolation par Row-Level Security PostgreSQL + colonne `org_id` sur toutes les tables
de données métier.**

### Mise en œuvre

1. **Toutes les tables métier** portent une colonne `org_id UUID NOT NULL REFERENCES tenants_organization(id)`.

2. **RLS activé au niveau PostgreSQL** sur chacune de ces tables :
   ```sql
   ALTER TABLE documents_invoice ENABLE ROW LEVEL SECURITY;

   CREATE POLICY tenant_isolation ON documents_invoice
     USING (org_id = current_setting('app.current_org_id')::uuid);
   ```

3. **Middleware Django** (`core/middleware.py`) injecte `app.current_org_id` à chaque
   requête via le rôle de connexion :
   ```python
   connection.cursor().execute(
       "SET LOCAL app.current_org_id = %s", [str(request.org.id)]
   )
   ```

4. **TenantManager Django** (`core/managers.py`) filtre automatiquement les QuerySets
   par `org_id` — double protection applicative + base de données.

5. **Superadmin** utilise un rôle PostgreSQL `ledger_admin` exempté du RLS
   (`BYPASSRLS`) — jamais exposé via l'API.

### Tables exemptées du RLS

- `tenants_organization` — référentiel tenant
- `tenants_tenantmembership` — association utilisateur ↔ org
- `auth_user` — utilisateurs globaux (filtrés au niveau app)

---

## Alternatives rejetées

**Schema-per-tenant (django-tenants)** : chaque migration doit être appliquée N fois
(une par tenant actif). Avec 50 tenants et des déploiements fréquents, l'opération
devient un goulot d'étranglement inacceptable. Risque de partial migration lors d'un
crash.

**Base séparée par tenant** : opérationnellement inenvisageable sans équipe DevOps
dédiée. Hors scope MVP.

---

## Conséquences

**Positives :**
- Une seule migration pour tous les tenants
- Coût infrastructure minimal (une seule DB)
- PostgreSQL applique l'isolation même si le code applicatif a un bug

**Négatives / risques :**
- `SET LOCAL app.current_org_id` doit être appelé **avant chaque query** — oubli =
  accès cross-tenant. Mitigation : tests d'intégration spécifiques + lint rule.
- Pas adapté si un tenant requiert un schéma de données personnalisé. Acceptable au
  stade MVP.

**Non-réversible** : activer RLS après coup sur une table pleine de données nécessite
une migration complexe. Cette décision doit être prise à J1.
