"""
apps/agents/graph.py — Graphe LangGraph pour le pipeline de traitement facture.

Le graphe implémente le flux ADR-007 :
  start → doc_intake → accounting_reasoner → END
                     ↘ human_review (sur erreur)
                                           ↗

Usage :
    from apps.agents.graph import run_invoice_pipeline
    final_state = run_invoice_pipeline(state)

ADR-007 — Architecture des agents.
"""
import logging
from typing import Any

from langgraph.graph import StateGraph, END

from apps.agents.state import AgentState
from apps.agents.nodes import (
    node_doc_intake,
    node_accounting_reasoner,
    node_human_review,
    should_continue,
    should_end,
)

logger = logging.getLogger(__name__)


def build_invoice_graph() -> Any:
    """Construit et compile le graphe LangGraph pour le pipeline facture.

    Topologie :
      doc_intake → (routing) → accounting_reasoner → (routing) → END
                             ↘ human_review ↗

    Returns:
        Graphe compilé (CompiledGraph) prêt à être invoké.
    """
    graph = StateGraph(AgentState)

    # Nœuds
    graph.add_node("doc_intake", node_doc_intake)
    graph.add_node("accounting_reasoner", node_accounting_reasoner)
    graph.add_node("human_review", node_human_review)

    # Point d'entrée
    graph.set_entry_point("doc_intake")

    # Transitions conditionnelles
    graph.add_conditional_edges(
        "doc_intake",
        should_continue,
        {
            "accounting_reasoner": "accounting_reasoner",
            "human_review": "human_review",
        },
    )
    graph.add_conditional_edges(
        "accounting_reasoner",
        should_end,
        {
            "__end__": END,
            "human_review": "human_review",
        },
    )

    # human_review est toujours terminal
    graph.add_edge("human_review", END)

    compiled = graph.compile()
    logger.debug("agent.graph.compiled nodes=%s", list(compiled.get_graph().nodes.keys()))
    return compiled


# Instance compilée — réutilisée entre les appels Celery
_invoice_graph = None


def get_invoice_graph() -> Any:
    """Retourne l'instance compilée du graphe (singleton).

    Le graphe est compilé une seule fois au premier appel.
    Thread-safe pour les workers Celery (lecture seule après compile).

    Returns:
        Graphe compilé (CompiledGraph).
    """
    global _invoice_graph
    if _invoice_graph is None:
        _invoice_graph = build_invoice_graph()
        logger.info("agent.graph.initialized")
    return _invoice_graph


def run_invoice_pipeline(initial_state: AgentState) -> AgentState:
    """Exécute le pipeline complet de traitement d'une facture.

    Args:
        initial_state: AgentState initial avec org_id, invoice_id,
            job_id, source_key, user_id.

    Returns:
        AgentState final après exécution du graphe.

    Raises:
        Exception: Propagée si le graphe plante de façon inattendue.
            Les erreurs métier sont capturées dans state["errors"].
    """
    graph = get_invoice_graph()

    logger.info(
        "agent.pipeline.start invoice_id=%s org_id=%s",
        initial_state.get("invoice_id"),
        initial_state.get("org_id"),
    )

    final_state = graph.invoke(initial_state)

    logger.info(
        "agent.pipeline.end invoice_id=%s step=%s errors=%s entry_id=%s",
        initial_state.get("invoice_id"),
        final_state.get("current_step"),
        final_state.get("errors"),
        final_state.get("journal_entry_id"),
    )

    return final_state
