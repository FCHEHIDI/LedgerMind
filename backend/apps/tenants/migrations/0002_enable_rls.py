"""
Migration Django pour activer Row-Level Security sur les tables métier.

ADR-001: RLS activé sur toutes les tables portant org_id.
Politique: org_id = current_setting('app.current_org_id', TRUE)::uuid

Cette migration est non-réversible (FORCE ROW LEVEL SECURITY).
"""
from django.db import migrations


# Tables métier portant org_id — à étendre si nouveaux modèles
TENANT_TABLES = [
    "documents_invoice",
    "documents_processingjob",
    "ledger_journalentry",
    "ledger_accountentry",
]


def enable_rls(apps, schema_editor):
    """Active RLS et crée les politiques d'isolation tenant.

    Args:
        apps: Registre d'applications Django.
        schema_editor: Éditeur de schéma.
    """
    for table in TENANT_TABLES:
        schema_editor.execute(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"
        )
        schema_editor.execute(
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"
        )
        schema_editor.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                org_id = current_setting('app.current_org_id', TRUE)::uuid
            );
            """
        )


def disable_rls(apps, schema_editor):
    """Désactive RLS (migration inverse — dev seulement, ADR-001 dit non-réversible).

    Args:
        apps: Registre d'applications Django.
        schema_editor: Éditeur de schéma.
    """
    for table in TENANT_TABLES:
        schema_editor.execute(
            f"DROP POLICY IF EXISTS tenant_isolation ON {table};"
        )
        schema_editor.execute(
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )


class Migration(migrations.Migration):
    """Migration d'activation RLS — exécutée après toutes les migrations de modèles."""

    # Dépend des migrations initiales de chaque app métier
    dependencies = [
        ("documents", "0001_initial"),
        ("ledger", "0001_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_rls, disable_rls),
    ]
