"""
apps/agents/nodes.py — Nœuds LangGraph pour le pipeline de traitement facture.

Agent 1 — DocIntake  : OCR + extraction structurée (qwen2.5:7b)
Agent 2 — Accounting : déduction PCG + création écriture (mistral:7b)

Chaque nœud reçoit et retourne un AgentState.
Les erreurs sont capturées dans state["errors"] — jamais de raise
qui couperait le graphe (le graphe route vers "human_review" sur erreur).

ADR-005 : aucune donnée métier dans les logs — uniquement UUIDs.
ADR-007 : architecture agents.
"""
import io
import json
import logging
import re
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

DOC_INTAKE_SYSTEM_PROMPT = """Tu es un expert en comptabilité française spécialisé dans l'extraction
de données de factures. Tu extrais les informations structurées d'une facture fournisseur.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après.
Le JSON doit avoir exactement ces clés :
{
  "vendor_name": "Nom du fournisseur",
  "vendor_siren": "123456789",
  "invoice_date": "YYYY-MM-DD",
  "invoice_number": "REF-001",
  "ht_amount": "100.00",
  "tva_amount": "20.00",
  "tva_rate": "20",
  "ttc_amount": "120.00",
  "description": "Description courte des services/biens"
}

Règles :
- vendor_siren : 9 chiffres uniquement, ou "" si absent
- Tous les montants en string décimal avec 2 décimales (ex: "1234.56")
- invoice_date au format ISO 8601 (YYYY-MM-DD)
- Si une valeur est absente, utilise ""
- tva_rate : "20", "10", "5.5", ou "0"
"""

DOC_INTAKE_USER_PROMPT = """Extrais les informations de cette facture :

{text}"""

ACCOUNTING_SYSTEM_PROMPT = """Tu es un expert-comptable français. Tu génères les écritures comptables
au format PCG (Plan Comptable Général) à partir des données d'une facture fournisseur.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après.
Le JSON doit avoir cette structure :
{
  "journal_code": "ACH",
  "lines": [
    {"account_code": "604", "account_label": "Prestations de services", "debit": "100.00", "credit": "0.00"},
    {"account_code": "44566", "account_label": "TVA déductible", "debit": "20.00", "credit": "0.00"},
    {"account_code": "401", "account_label": "Fournisseur", "debit": "0.00", "credit": "120.00"}
  ]
}

Règles PCG obligatoires :
- Somme des débits = Somme des crédits (écriture équilibrée)
- Achat de services/prestations → débit 604
- Achat de marchandises → débit 60700
- Achat matériel informatique → débit 2183
- TVA 20% → débit 44566
- TVA 10% → débit 44567
- TVA 5.5% → débit 44568
- Fournisseur → crédit 401 (TTC total)
- Tous les montants en string décimal avec 2 décimales
"""

ACCOUNTING_USER_PROMPT = """Génère l'écriture comptable PCG pour cette facture :

Fournisseur: {vendor_name}
Date: {invoice_date}
Référence: {invoice_number}
Montant HT: {ht_amount} €
TVA ({tva_rate}%): {tva_amount} €
Montant TTC: {ttc_amount} €
Description: {description}

Plan comptable disponible :
{account_plan}"""


# ---------------------------------------------------------------------------
# Nœud 1 — Document Intake (Agent 1)
# ---------------------------------------------------------------------------

def node_doc_intake(state: dict[str, Any]) -> dict[str, Any]:
    """Nœud Agent 1 : OCR + extraction structurée depuis le PDF.

    Lit le PDF depuis MinIO, extrait le texte avec pdfplumber,
    puis demande à qwen2.5:7b d'extraire les données structurées.

    Args:
        state: AgentState avec invoice_id, job_id, source_key, org_id.

    Returns:
        AgentState mis à jour avec extracted_data et raw_text,
        ou avec errors[] si extraction impossible.
    """
    from apps.agents.tools import read_document, update_job_status, update_invoice

    state = dict(state)
    state["current_step"] = "doc_intake"
    invoice_id = state.get("invoice_id")
    job_id = state.get("job_id")
    source_key = state.get("source_key")

    logger.info("agent.doc_intake.start invoice_id=%s job_id=%s", invoice_id, job_id)

    # Marquer le job comme démarré
    try:
        update_job_status(job_id, "started")
        update_invoice(invoice_id, {"status": "processing"})
    except Exception as exc:
        logger.error("agent.doc_intake.job_update_error job_id=%s err=%s", job_id, type(exc).__name__)

    # Étape 1 : Lecture PDF depuis MinIO
    try:
        pdf_bytes = read_document(source_key)
    except Exception as exc:
        logger.error("agent.doc_intake.read_error key=%s err=%s", source_key, type(exc).__name__)
        state["errors"].append("PDF_READ_ERROR")
        state["requires_human_review"] = True
        _fail_job(job_id, "PDF_READ_ERROR")
        return state

    # Étape 2 : Extraction texte avec pdfplumber
    raw_text = _extract_text_from_pdf(pdf_bytes, invoice_id)
    if not raw_text:
        state["errors"].append("PDF_NO_TEXT")
        state["requires_human_review"] = True
        _fail_job(job_id, "PDF_NO_TEXT")
        return state

    state["raw_text"] = raw_text

    # Étape 3 : Extraction structurée via LLM
    extracted = _llm_extract_invoice(raw_text, invoice_id)
    if extracted is None:
        state["errors"].append("LLM_EXTRACTION_ERROR")
        state["requires_human_review"] = True
        _fail_job(job_id, "LLM_EXTRACTION_ERROR")
        return state

    state["extracted_data"] = extracted

    # Étape 4 : Persistance en base (champs chiffrés — ADR-004)
    try:
        update_invoice(invoice_id, {
            "vendor_name": extracted.get("vendor_name", ""),
            "vendor_siren": extracted.get("vendor_siren", ""),
            "ht_amount": extracted.get("ht_amount", ""),
            "tva_amount": extracted.get("tva_amount", ""),
            "ttc_amount": extracted.get("ttc_amount", ""),
            "raw_text": raw_text,
            "status": "extracted",
        })
    except Exception as exc:
        logger.error("agent.doc_intake.save_error invoice_id=%s err=%s", invoice_id, type(exc).__name__)
        state["warnings"].append("INVOICE_SAVE_WARNING")

    logger.info("agent.doc_intake.success invoice_id=%s", invoice_id)
    return state


def _extract_text_from_pdf(pdf_bytes: bytes, invoice_id: str) -> str:
    """Extrait le texte d'un PDF avec pdfplumber.

    Args:
        pdf_bytes: Contenu binaire du PDF.
        invoice_id: UUID de la facture (pour les logs uniquement — ADR-005).

    Returns:
        Texte extrait, ou chaîne vide si extraction impossible.
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
            result = "\n".join(texts).strip()
            logger.debug(
                "agent.doc_intake.pdf_extracted invoice_id=%s chars=%d pages=%d",
                invoice_id, len(result), len(pdf.pages),
            )
            return result
    except Exception as exc:
        logger.error(
            "agent.doc_intake.pdf_error invoice_id=%s err=%s",
            invoice_id, type(exc).__name__,
        )
        return ""


def _llm_extract_invoice(raw_text: str, invoice_id: str) -> dict[str, Any] | None:
    """Appelle le LLM configuré pour extraire les données structurées d'une facture.

    Provider sélectionné via LLM_PROVIDER (ollama|groq, défaut: ollama).
    Modèle sélectionné via DOC_INTAKE_MODEL (défaut: qwen2.5:7b pour ollama,
    llama-3.1-8b-instant pour groq).

    Args:
        raw_text: Texte brut de la facture (jamais loggé — ADR-005).
        invoice_id: UUID pour les logs uniquement.

    Returns:
        Dict avec les clés extraites, ou None si l'extraction échoue.
    """
    import os
    from langchain_core.messages import HumanMessage, SystemMessage

    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()

    try:
        if provider == "groq":
            from langchain_groq import ChatGroq
            model_name = os.environ.get("DOC_INTAKE_MODEL", "llama-3.1-8b-instant")
            llm = ChatGroq(
                model=model_name,
                temperature=0.0,
                api_key=os.environ.get("GROQ_API_KEY", ""),
            )
        else:
            from langchain_ollama import ChatOllama
            model_name = os.environ.get("DOC_INTAKE_MODEL", "qwen2.5:7b")
            ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
            llm = ChatOllama(
                model=model_name,
                base_url=ollama_base_url,
                temperature=0.0,
                format="json",
            )
        logger.debug("agent.doc_intake.provider=%s model=%s invoice_id=%s", provider, model_name, invoice_id)
        messages = [
            SystemMessage(content=DOC_INTAKE_SYSTEM_PROMPT),
            HumanMessage(content=DOC_INTAKE_USER_PROMPT.format(text=raw_text[:4000])),
        ]
        response = llm.invoke(messages)
        raw_json = response.content.strip()

        # Extraction JSON robuste (le modèle peut ajouter du texte avant/après)
        json_match = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if not json_match:
            logger.warning("agent.doc_intake.llm_no_json invoice_id=%s", invoice_id)
            return None

        data = json.loads(json_match.group())
        logger.info("agent.doc_intake.llm_success invoice_id=%s", invoice_id)
        return data

    except json.JSONDecodeError as exc:
        logger.error("agent.doc_intake.json_error invoice_id=%s err=%s", invoice_id, exc)
        return None
    except Exception as exc:
        logger.error("agent.doc_intake.llm_error invoice_id=%s err=%s", invoice_id, type(exc).__name__)
        return None


# ---------------------------------------------------------------------------
# Nœud 2 — Accounting Reasoner (Agent 2)
# ---------------------------------------------------------------------------

def node_accounting_reasoner(state: dict[str, Any]) -> dict[str, Any]:
    """Nœud Agent 2 : déduction PCG + création écriture comptable.

    Utilise les données extraites par Agent 1 pour générer une
    écriture comptable équilibrée via mistral:7b, puis la persiste.

    Args:
        state: AgentState avec extracted_data, org_id, invoice_id.

    Returns:
        AgentState mis à jour avec journal_entry_id,
        ou avec errors[] si génération impossible.
    """
    from apps.agents.tools import create_journal_entry, get_account_plan, update_job_status

    state = dict(state)
    state["current_step"] = "accounting_reasoner"

    invoice_id = state.get("invoice_id")
    job_id = state.get("job_id")
    org_id = state.get("org_id")
    extracted = state.get("extracted_data")

    logger.info("agent.accounting.start invoice_id=%s", invoice_id)

    if not extracted:
        logger.error("agent.accounting.no_data invoice_id=%s", invoice_id)
        state["errors"].append("NO_EXTRACTED_DATA")
        state["requires_human_review"] = True
        return state

    # Étape 1 : Appel LLM pour la génération PCG
    account_plan = get_account_plan(org_id)
    accounting_result = _llm_generate_accounting(extracted, account_plan, invoice_id)

    if accounting_result is None:
        # Fallback : règles hardcodées (ADR-007)
        logger.warning("agent.accounting.llm_fallback invoice_id=%s", invoice_id)
        accounting_result = _hardcoded_accounting(extracted)
        if accounting_result:
            state["warnings"].append("ACCOUNTING_USED_FALLBACK")

    if accounting_result is None:
        state["errors"].append("ACCOUNTING_GENERATION_ERROR")
        state["requires_human_review"] = True
        _fail_job(job_id, "ACCOUNTING_ERROR")
        return state

    # Étape 2 : Persistance en base
    try:
        entry_date = extracted.get("invoice_date") or str(__import__("datetime").date.today())
        reference = extracted.get("invoice_number") or f"IMPORT-{invoice_id[:8].upper()}"

        entry_id = create_journal_entry(
            org_id=org_id,
            invoice_id=invoice_id,
            entry_date=entry_date,
            reference=reference,
            lines=accounting_result["lines"],
        )
        state["journal_entry_id"] = entry_id

    except ValueError as exc:
        logger.error("agent.accounting.create_error invoice_id=%s err=%s", invoice_id, exc)
        state["errors"].append("JOURNAL_CREATE_ERROR")
        state["requires_human_review"] = True
        _fail_job(job_id, "JOURNAL_CREATE_ERROR")
        return state
    except Exception as exc:
        logger.error("agent.accounting.unexpected invoice_id=%s err=%s", invoice_id, type(exc).__name__)
        state["errors"].append("JOURNAL_UNEXPECTED_ERROR")
        state["requires_human_review"] = True
        _fail_job(job_id, "JOURNAL_UNEXPECTED_ERROR")
        return state

    # Étape 3 : Marquer le job comme succès
    try:
        update_job_status(job_id, "success")
    except Exception as exc:
        logger.warning("agent.accounting.job_success_error job_id=%s err=%s", job_id, type(exc).__name__)

    logger.info(
        "agent.accounting.success invoice_id=%s entry_id=%s",
        invoice_id, state["journal_entry_id"],
    )
    return state


def _llm_generate_accounting(
    extracted: dict[str, Any],
    account_plan: dict[str, str],
    invoice_id: str,
) -> dict[str, Any] | None:
    """Appelle le LLM configuré pour générer l'écriture PCG.

    Provider sélectionné via LLM_PROVIDER (ollama|groq, défaut: ollama).
    Modèle sélectionné via ACCOUNTING_MODEL (défaut: mistral:7b pour ollama,
    mixtral-8x7b-32768 pour groq).

    Args:
        extracted: Données extraites par Agent 1.
        account_plan: Dict {code: libellé} du plan comptable.
        invoice_id: UUID pour les logs uniquement (ADR-005).

    Returns:
        Dict avec "lines" (liste d'AccountEntry), ou None si erreur.
    """
    import os
    from langchain_core.messages import HumanMessage, SystemMessage

    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    account_plan_str = "\n".join(f"  {k}: {v}" for k, v in account_plan.items())

    try:
        if provider == "groq":
            from langchain_groq import ChatGroq
            model_name = os.environ.get("ACCOUNTING_MODEL", "mixtral-8x7b-32768")
            llm = ChatGroq(
                model=model_name,
                temperature=0.0,
                api_key=os.environ.get("GROQ_API_KEY", ""),
            )
        else:
            from langchain_ollama import ChatOllama
            model_name = os.environ.get("ACCOUNTING_MODEL", "mistral:7b")
            ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
            llm = ChatOllama(
                model=model_name,
                base_url=ollama_base_url,
                temperature=0.0,
                format="json",
            )
        logger.debug("agent.accounting.provider=%s model=%s invoice_id=%s", provider, model_name, invoice_id)
        messages = [
            SystemMessage(content=ACCOUNTING_SYSTEM_PROMPT),
            HumanMessage(content=ACCOUNTING_USER_PROMPT.format(
                vendor_name=extracted.get("vendor_name", "Inconnu"),
                invoice_date=extracted.get("invoice_date", ""),
                invoice_number=extracted.get("invoice_number", ""),
                ht_amount=extracted.get("ht_amount", "0.00"),
                tva_rate=extracted.get("tva_rate", "20"),
                tva_amount=extracted.get("tva_amount", "0.00"),
                ttc_amount=extracted.get("ttc_amount", "0.00"),
                description=extracted.get("description", ""),
                account_plan=account_plan_str,
            )),
        ]
        response = llm.invoke(messages)
        raw_json = response.content.strip()

        json_match = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if not json_match:
            logger.warning("agent.accounting.llm_no_json invoice_id=%s", invoice_id)
            return None

        data = json.loads(json_match.group())

        # Validation : lignes présentes et équilibre
        lines = data.get("lines", [])
        if not lines:
            return None

        total_debit = sum(Decimal(str(l.get("debit", 0))) for l in lines)
        total_credit = sum(Decimal(str(l.get("credit", 0))) for l in lines)
        if total_debit != total_credit:
            logger.warning(
                "agent.accounting.llm_unbalanced invoice_id=%s debit=%s credit=%s",
                invoice_id, total_debit, total_credit,
            )
            return None

        logger.info("agent.accounting.llm_success invoice_id=%s lines=%d", invoice_id, len(lines))
        return data

    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("agent.accounting.json_error invoice_id=%s err=%s", invoice_id, exc)
        return None
    except Exception as exc:
        logger.error("agent.accounting.llm_error invoice_id=%s err=%s", invoice_id, type(exc).__name__)
        return None


def _hardcoded_accounting(extracted: dict[str, Any]) -> dict[str, Any] | None:
    """Génère l'écriture PCG par règles hardcodées (fallback sans LLM).

    Règles ADR-007 :
    - Services/prestations → 604
    - TVA 20% → 44566, TVA 10% → 44567, TVA 5.5% → 44568
    - Fournisseur → 401 (crédit TTC)

    Args:
        extracted: Données extraites par Agent 1.

    Returns:
        Dict avec "lines" ou None si données insuffisantes.
    """
    ht = extracted.get("ht_amount", "")
    tva = extracted.get("tva_amount", "")
    ttc = extracted.get("ttc_amount", "")
    tva_rate = str(extracted.get("tva_rate", "20"))

    try:
        ht_d = Decimal(str(ht)) if ht else None
        tva_d = Decimal(str(tva)) if tva else None
        ttc_d = Decimal(str(ttc)) if ttc else None
    except Exception:
        return None

    if not ht_d or not ttc_d:
        return None

    tva_account_map = {"20": "44566", "10": "44567", "5.5": "44568", "0": None}
    tva_account = tva_account_map.get(tva_rate, "44566")

    lines = [
        {
            "account_code": "604",
            "account_label": "Achats d'études et prestations de services",
            "debit": str(ht_d),
            "credit": "0.00",
        },
    ]

    if tva_account and tva_d and tva_d > 0:
        lines.append({
            "account_code": tva_account,
            "account_label": f"TVA déductible {tva_rate}%",
            "debit": str(tva_d),
            "credit": "0.00",
        })

    lines.append({
        "account_code": "401",
        "account_label": "Fournisseurs",
        "debit": "0.00",
        "credit": str(ttc_d),
    })

    return {"journal_code": "ACH", "lines": lines}


# ---------------------------------------------------------------------------
# Nœud 3 — Human Review (terminal sur erreur)
# ---------------------------------------------------------------------------

def node_human_review(state: dict[str, Any]) -> dict[str, Any]:
    """Nœud terminal pour les cas nécessitant une révision humaine.

    Met à jour le statut de la facture en "rejected" et logge
    les codes d'erreur sans détails métier (ADR-005).

    Args:
        state: AgentState avec errors, invoice_id, job_id.

    Returns:
        AgentState inchangé (nœud terminal).
    """
    from apps.agents.tools import update_invoice, update_job_status

    invoice_id = state.get("invoice_id")
    job_id = state.get("job_id")
    errors = state.get("errors", [])

    logger.warning(
        "agent.human_review invoice_id=%s errors=%s",
        invoice_id, errors,
    )

    try:
        update_invoice(invoice_id, {"status": "rejected"})
    except Exception as exc:
        logger.error("agent.human_review.invoice_error invoice_id=%s err=%s", invoice_id, type(exc).__name__)

    try:
        job = __import__("apps.documents.models", fromlist=["ProcessingJob"]).ProcessingJob
        current_status = job.objects.filter(id=job_id).values_list("status", flat=True).first()
        if current_status not in ("success", "failure"):
            update_job_status(job_id, "failure", error_code=errors[0][:50] if errors else "UNKNOWN")
    except Exception as exc:
        logger.error("agent.human_review.job_error job_id=%s err=%s", job_id, type(exc).__name__)

    return dict(state)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fail_job(job_id: str | None, error_code: str) -> None:
    """Marque un job comme en échec. Ne lève pas d'exception.

    Args:
        job_id: UUID du job (peut être None).
        error_code: Code d'erreur court (max 50 chars).
    """
    if not job_id:
        return
    try:
        from apps.agents.tools import update_job_status
        update_job_status(job_id, "failure", error_code=error_code)
    except Exception as exc:
        logger.error("agent._fail_job error job_id=%s err=%s", job_id, type(exc).__name__)


def should_continue(state: dict[str, Any]) -> str:
    """Fonction de routage LangGraph : détermine le prochain nœud.

    Args:
        state: AgentState après doc_intake.

    Returns:
        "accounting_reasoner" si extraction OK,
        "human_review" si erreur ou review requise.
    """
    if state.get("errors") or state.get("requires_human_review"):
        return "human_review"
    if not state.get("extracted_data"):
        return "human_review"
    return "accounting_reasoner"


def should_end(state: dict[str, Any]) -> str:
    """Fonction de routage LangGraph après accounting_reasoner.

    Args:
        state: AgentState après accounting_reasoner.

    Returns:
        "human_review" si erreur, "__end__" sinon.
    """
    if state.get("errors") or state.get("requires_human_review"):
        return "human_review"
    return "__end__"
