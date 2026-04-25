"""
apps/agents/state.py — État partagé entre les nœuds LangGraph.

AgentState est le TypedDict passé de nœud en nœud dans le graphe.
Toutes les données identifiantes sont des UUIDs opaques — jamais de
données métier brutes dans l'état (ADR-005).

ADR-007 — Architecture des agents.
"""
import logging
from typing import Any, Optional
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """État partagé entre tous les nœuds du graphe d'agents.

    Le flux principal est :
      upload → doc_intake → accounting_reasoner → [human_review]

    Attributes:
        org_id: UUID de l'organisation (tenant isolé — ADR-001).
        user_id: UUID de l'utilisateur déclencheur.
        invoice_id: UUID de la facture en cours de traitement.
        job_id: UUID du ProcessingJob Celery associé.
        source_key: Clé MinIO du fichier PDF (format: {org_id}/{uuid}.pdf).
        extracted_data: Données structurées extraites par Agent 1.
            Keys: vendor_name, vendor_siren, invoice_date,
                  ht_amount, tva_amount, ttc_amount, tva_rate.
        journal_entry_id: UUID de l'écriture créée par Agent 2.
        reconciliation_result: Résultat du rapprochement (Agent 3).
        current_step: Nœud courant du graphe (pour observabilité).
        errors: Liste des codes d'erreur rencontrés.
        warnings: Avertissements non bloquants.
        requires_human_review: True si validation humaine requise.
        raw_text: Texte brut extrait du PDF (jamais loggé — ADR-005).
    """

    # Contexte tenant
    org_id: str
    user_id: str

    # Document en cours
    invoice_id: Optional[str]
    job_id: Optional[str]
    source_key: Optional[str]

    # Données extraites (sortie Agent 1)
    extracted_data: Optional[dict[str, Any]]
    raw_text: Optional[str]

    # Écriture comptable (sortie Agent 2)
    journal_entry_id: Optional[str]

    # Rapprochement bancaire (sortie Agent 3)
    reconciliation_result: Optional[dict[str, Any]]

    # Contrôle de flux
    current_step: str
    errors: list[str]
    warnings: list[str]
    requires_human_review: bool


def make_initial_state(
    org_id: str,
    user_id: str,
    invoice_id: str,
    job_id: str,
    source_key: str,
) -> AgentState:
    """Crée l'état initial pour un pipeline de traitement de facture.

    Args:
        org_id: UUID de l'organisation.
        user_id: UUID de l'utilisateur.
        invoice_id: UUID de la facture.
        job_id: UUID du ProcessingJob.
        source_key: Clé MinIO du PDF.

    Returns:
        AgentState initialisé avec les valeurs par défaut.
    """
    return AgentState(
        org_id=org_id,
        user_id=user_id,
        invoice_id=invoice_id,
        job_id=job_id,
        source_key=source_key,
        extracted_data=None,
        raw_text=None,
        journal_entry_id=None,
        reconciliation_result=None,
        current_step="start",
        errors=[],
        warnings=[],
        requires_human_review=False,
    )
