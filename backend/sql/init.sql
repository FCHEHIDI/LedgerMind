"""
SQL d'initialisation PostgreSQL pour LedgerMind.

Exécuté au premier démarrage du conteneur postgres via le volume
docker-entrypoint-initdb.d/ (voir docker-compose.dev.yml).

Opérations:
  1. Extensions PostgreSQL (uuid-ossp, pgcrypto)
  2. Rôles PostgreSQL (ledger_app, ledger_admin)
  3. Activation Row-Level Security sur toutes les tables métier
  4. Politiques RLS d'isolation par org_id (ADR-001)

ADR-001: ledger_admin a BYPASSRLS pour les opérations de superadmin.
ADR-001: SET LOCAL app.current_org_id = '<uuid>' appelé par TenantMiddleware
         avant chaque requête ORM.
"""

-- =============================================================================
-- 1. Extensions
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 2. Rôles applicatifs
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ledger_app') THEN
        CREATE ROLE ledger_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ledger_admin') THEN
        -- ledger_admin bypasses RLS — for superadmin operations only (ADR-001)
        CREATE ROLE ledger_admin LOGIN BYPASSRLS;
    END IF;
END
$$;

-- =============================================================================
-- 3. Row-Level Security — activé après les migrations Django
-- =============================================================================
-- Ces commandes doivent être exécutées APRÈS les migrations Django
-- (les tables doivent exister). Utiliser comme script de post-migration
-- ou via une migration Django RunSQL.

-- Template de politique d'isolation par org_id (ADR-001):
--
-- ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
--
-- CREATE POLICY tenant_isolation ON <table>
--   USING (org_id = current_setting('app.current_org_id', TRUE)::uuid);
--
-- Les tables concernées (à activer après chaque migration de nouveau modèle):
--   documents_invoice
--   documents_processingjob
--   ledger_journalentry
--   ledger_accountentry

-- =============================================================================
-- 4. Grants pour ledger_app (connexion applicative Django)
-- =============================================================================
-- GRANT CONNECT ON DATABASE ledgermind TO ledger_app;
-- GRANT USAGE ON SCHEMA public TO ledger_app;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO ledger_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ledger_app;
