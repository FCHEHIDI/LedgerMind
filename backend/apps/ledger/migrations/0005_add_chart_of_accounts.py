"""Migration 0005 — Ajout du plan de comptes (ChartOfAccounts).

Table: ledger_chartofaccounts
Contrainte unique: (org_id, account_code)
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0004_add_bank_reconciliation"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChartOfAccounts",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        db_column="org_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chart_of_accounts",
                        to="tenants.organization",
                    ),
                ),
                ("account_code", models.CharField(db_index=True, max_length=20)),
                ("account_label", models.CharField(max_length=255)),
                (
                    "account_class",
                    models.PositiveSmallIntegerField(
                        help_text="Classe comptable 1-9 (premier chiffre du compte)."
                    ),
                ),
                (
                    "account_type",
                    models.CharField(
                        choices=[
                            ("actif", "Actif"),
                            ("passif", "Passif"),
                            ("charge", "Charge"),
                            ("produit", "Produit"),
                            ("tiers", "Comptes de tiers"),
                            ("tresorerie", "Trésorerie"),
                        ],
                        default="tiers",
                        max_length=20,
                    ),
                ),
                (
                    "is_system",
                    models.BooleanField(
                        default=False,
                        help_text="Compte PCG standard non supprimable.",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "parent_code",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Code du compte parent pour l'arborescence.",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "ledger_chartofaccounts",
                "ordering": ["account_code"],
            },
        ),
        migrations.AddConstraint(
            model_name="chartofaccounts",
            constraint=models.UniqueConstraint(
                fields=["org", "account_code"],
                name="unique_chart_org_code",
            ),
        ),
    ]
