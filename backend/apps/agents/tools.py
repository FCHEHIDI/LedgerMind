"""
apps/agents/tools.py — Outils MCP/DB utilisés par les agents.

Chaque outil est une fonction pure appelée par les nœuds du graphe.
Aucun outil ne logge de données métier (ADR-005) — uniquement des UUIDs.

ADR-007 — Architecture des agents.
ADR-004 — Chiffrement des données sensibles.
"""
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outil 1 — Lecture du PDF depuis MinIO
# ---------------------------------------------------------------------------

def read_document(source_key: str) -> bytes:
    """Télécharge un PDF depuis MinIO par sa clé de stockage.

    Args:
        source_key: Clé objet MinIO (format: {org_id}/{uuid}.pdf).
            Ne contient jamais le nom de fichier original (ADR-004).

    Returns:
        Contenu binaire du PDF.

    Raises:
        ClientError: Si la clé n'existe pas ou accès refusé.
        ValueError: Si source_key est vide.
    """
    if not source_key:
        raise ValueError("source_key ne peut pas être vide")

    client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    bucket = settings.AWS_STORAGE_BUCKET_NAME

    logger.debug("agent.tools.read_document key=%s", source_key)
    try:
        response = client.get_object(Bucket=bucket, Key=source_key)
        return response["Body"].read()
    except ClientError as exc:
        logger.error(
            "agent.tools.read_document.error key=%s code=%s",
            source_key,
            exc.response["Error"]["Code"],
        )
        raise


# ---------------------------------------------------------------------------
# Outil 2 — Mise à jour du statut du ProcessingJob
# ---------------------------------------------------------------------------

def update_job_status(
    job_id: str,
    status: str,
    error_code: Optional[str] = None,
) -> None:
    """Met à jour le statut d'un ProcessingJob.

    Args:
        job_id: UUID du job.
        status: Nouveau statut (queued/started/success/failure/retry).
        error_code: Code d'erreur court (sans détails métier) si failure.

    Raises:
        ValueError: Si status n'est pas une valeur valide.
        ProcessingJob.DoesNotExist: Si le job n'existe pas.
    """
    from apps.documents.models import ProcessingJob
    import django.utils.timezone as tz

    valid_statuses = {"queued", "started", "success", "failure", "retry"}
    if status not in valid_statuses:
        raise ValueError(f"Statut invalide: {status!r}. Attendu: {valid_statuses}")

    job = ProcessingJob.objects.get(id=job_id)

    update_fields = ["status"]
    job.status = status

    if status == "started" and job.started_at is None:
        job.started_at = tz.now()
        update_fields.append("started_at")

    if status in {"success", "failure"}:
        job.finished_at = tz.now()
        update_fields.append("finished_at")

    if error_code:
        job.error_code = error_code[:50]  # Max 50 chars — ADR-005 pas de détails
        update_fields.append("error_code")

    job.save(update_fields=update_fields)
    logger.info("agent.tools.update_job_status job_id=%s status=%s", job_id, status)


# ---------------------------------------------------------------------------
# Outil 3 — Mise à jour de la facture
# ---------------------------------------------------------------------------

def update_invoice(invoice_id: str, data: dict[str, Any]) -> None:
    """Met à jour les champs extraits d'une Invoice.

    Seuls les champs autorisés sont mis à jour. Les champs chiffrés
    (ADR-004) sont écrits tels quels — la couche Fernet chiffre
    automatiquement au save().

    Args:
        invoice_id: UUID de la facture.
        data: Dict avec les clés autorisées :
            - vendor_name (str)
            - vendor_siren (str, 9 chiffres)
            - vendor_siren_hash (str, HMAC hex)
            - ht_amount (str représentant un Decimal)
            - tva_amount (str représentant un Decimal)
            - ttc_amount (str représentant un Decimal)
            - invoice_date (date)
            - status (str)
            - raw_text (str)

    Raises:
        Invoice.DoesNotExist: Si la facture n'existe pas.
        ValueError: Si un montant n'est pas convertible en Decimal.
    """
    from apps.documents.models import Invoice

    ALLOWED_FIELDS = {
        "vendor_name", "vendor_siren", "vendor_siren_hash",
        "ht_amount", "tva_amount", "ttc_amount",
        "invoice_date", "status", "raw_text",
    }
    AMOUNT_FIELDS = {"ht_amount", "tva_amount", "ttc_amount"}

    invoice = Invoice.objects.get(id=invoice_id)
    update_fields: list[str] = ["updated_at"]

    for field, value in data.items():
        if field not in ALLOWED_FIELDS:
            logger.warning(
                "agent.tools.update_invoice.ignored_field field=%s invoice_id=%s",
                field, invoice_id,
            )
            continue

        if field in AMOUNT_FIELDS and value is not None:
            try:
                Decimal(str(value))  # validation seulement
            except InvalidOperation as exc:
                raise ValueError(
                    f"Montant invalide pour {field}: {value!r}"
                ) from exc
            value = str(value)

        setattr(invoice, field, value)
        update_fields.append(field)

    invoice.save(update_fields=update_fields)
    logger.info("agent.tools.update_invoice invoice_id=%s fields=%s", invoice_id, update_fields)


# ---------------------------------------------------------------------------
# Outil 4 — Création d'une écriture comptable
# ---------------------------------------------------------------------------

def create_journal_entry(
    org_id: str,
    invoice_id: str,
    entry_date: str,
    reference: str,
    lines: list[dict[str, Any]],
) -> str:
    """Crée une JournalEntry + ses AccountEntry depuis les données Agent 2.

    Vérifie l'équilibre débit/crédit avant l'écriture en base.

    Args:
        org_id: UUID de l'organisation.
        invoice_id: UUID de la facture source.
        entry_date: Date au format YYYY-MM-DD.
        reference: Référence de l'écriture (ex: "FACTURE-001").
        lines: Liste de lignes, chacune avec :
            - account_code (str) : code PCG (ex: "604")
            - account_label (str) : libellé du compte
            - debit (str|float) : montant débit (0 si crédit)
            - credit (str|float) : montant crédit (0 si débit)

    Returns:
        UUID de l'écriture créée (str).

    Raises:
        ValueError: Si l'écriture n'est pas équilibrée ou si lines est vide.
        Organization.DoesNotExist: Si org_id est invalide.
    """
    from apps.ledger.models import JournalEntry, AccountEntry
    from apps.tenants.models import Organization

    if not lines:
        raise ValueError("Une écriture doit avoir au moins une ligne")

    total_debit = sum(Decimal(str(l["debit"])) for l in lines)
    total_credit = sum(Decimal(str(l["credit"])) for l in lines)
    if total_debit != total_credit:
        raise ValueError(
            f"Écriture déséquilibrée: débit={total_debit} crédit={total_credit}"
        )

    org = Organization.objects.get(id=org_id)

    from apps.documents.models import Invoice as InvoiceModel
    invoice_instance = None
    try:
        invoice_instance = InvoiceModel.objects.get(id=invoice_id)
    except InvoiceModel.DoesNotExist:
        pass

    entry = JournalEntry.objects.create(
        org=org,
        reference=reference,
        journal_code="ACH",
        entry_date=entry_date,
        status="draft",
        invoice=invoice_instance,
    )

    account_entries = [
        AccountEntry(
            org=org,
            journal_entry=entry,
            account_code=line["account_code"],
            account_label=line["account_label"],
            debit=Decimal(str(line["debit"])),
            credit=Decimal(str(line["credit"])),
        )
        for line in lines
    ]
    AccountEntry.objects.bulk_create(account_entries)

    # Ne pas auto-valider la facture : l'utilisateur valide manuellement via le drawer

    logger.info(
        "agent.tools.create_journal_entry entry_id=%s org_id=%s lines=%d",
        entry.id, org_id, len(lines),
    )
    return str(entry.id)


# ---------------------------------------------------------------------------
# Outil 5 — Récupération du plan comptable
# ---------------------------------------------------------------------------

def get_account_plan(org_id: str) -> dict[str, str]:
    """Retourne le plan comptable actif de l'organisation.

    Actuellement retourne le plan PCG standard (ADR-008 MVP).
    En prod : plan personnalisé par org stocké en base.

    Args:
        org_id: UUID de l'organisation (non utilisé en MVP).

    Returns:
        Dict {code_pcg: libellé} avec les comptes courants.
    """
    # PCG standard — ADR-008
    return {
        # Classe 2 — Immobilisations
        "2154": "Matériel industriel",
        "2183": "Matériel de bureau et informatique",
        # Classe 4 — Comptes de tiers
        "401": "Fournisseurs",
        "411": "Clients",
        "44566": "TVA déductible sur autres biens et services",
        "44567": "TVA déductible sur achats — taux intermédiaire",
        "44568": "TVA déductible sur achats — taux réduit",
        "44571": "TVA collectée",
        # Classe 6 — Charges
        "604": "Achats d'études et prestations de services",
        "606": "Achats non stockés de matières et fournitures",
        "60700": "Achats de marchandises",
        "613": "Locations",
        "615": "Entretien et réparations",
        "616": "Primes d'assurance",
        "622": "Rémunérations d'intermédiaires et honoraires",
        "623": "Publicité, publications, relations publiques",
        "625": "Déplacements, missions et réceptions",
        "626": "Frais postaux et frais de télécommunications",
        "627": "Services bancaires et assimilés",
        # Classe 7 — Produits
        "706": "Prestations de services",
        "707": "Ventes de marchandises",
        "708": "Produits des activités annexes",
    }
