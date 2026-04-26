"""
apps/api/notifications.py — Service de notification plug-and-play.

Architecture:
  NotificationService est un façade stateless. Il tente dans l'ordre :
    1. Webhook externe (LEDGERMIND_NOTIFY_WEBHOOK_URL) — Akshi / tout service HTTP
    2. Log Django (toujours, pour traçabilité)

  Brancher un vrai système = poser LEDGERMIND_NOTIFY_WEBHOOK_URL dans .env.
  Le contrat du payload est fixe (voir _build_payload), ce qui garantit la
  compatibilité avec n'importe quel consumer (Akshi, Slack, custom).

Payload envoyé (JSON) :
  {
    "event":   "org_request.submitted" | "org_request.approved" | "org_request.rejected",
    "source":  "ledgermind",
    "data": {
      "request_id": "<uuid>",
      "requester":  "<username>",
      "org_name":   "<name>",
      "siren":      "<siren>",
      "status":     "pending" | "approved" | "rejected",
      "reviewer":   "<username>" | null,
      "note":       "<reviewer_note>" | ""
    }
  }

TODO (service indépendant) :
  - Remplacer le webhook par un client dédié (Akshi SDK, Novu, etc.)
  - Ajouter canaux email (Django send_mail)
  - Ajouter in-app notifications (table Notification + SSE/WebSocket)
"""
import json
import logging
import os
from typing import Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

_WEBHOOK_URL: Optional[str] = os.environ.get("LEDGERMIND_NOTIFY_WEBHOOK_URL", "").strip() or None


def _build_payload(event: str, request) -> dict:
    """Construit le payload normalisé pour tous les canaux.

    Args:
        event: Identifiant de l'événement (ex: "org_request.submitted").
        request: Instance OrgCreationRequest.

    Returns:
        Dictionnaire sérialisable en JSON.
    """
    return {
        "event": event,
        "source": "ledgermind",
        "data": {
            "request_id": str(request.id),
            "requester": request.requester.username,
            "org_name": request.name,
            "siren": request.siren,
            "status": request.status,
            "reviewer": request.reviewer.username if request.reviewer else None,
            "note": request.reviewer_note or "",
        },
    }


def _send_webhook(payload: dict) -> None:
    """Envoie le payload au webhook configuré (best-effort, pas de raise).

    Args:
        payload: Dictionnaire à sérialiser en JSON.
    """
    if not _WEBHOOK_URL:
        return
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "LedgerMind/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.debug("notification.webhook sent event=%s status=%s", payload["event"], resp.status)
    except urllib.error.URLError as exc:
        logger.warning("notification.webhook failed event=%s error=%s", payload["event"], exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("notification.webhook unexpected error event=%s error=%s", payload["event"], exc)


def notify_org_request_submitted(request) -> None:
    """Notifie qu'une demande de création d'org a été soumise.

    Args:
        request: Instance OrgCreationRequest fraîchement créée.
    """
    payload = _build_payload("org_request.submitted", request)
    logger.info(
        "org_request.submitted id=%s requester=%s org=%s siren=%s",
        request.id, request.requester.username, request.name, request.siren,
    )
    _send_webhook(payload)


def notify_org_request_approved(request) -> None:
    """Notifie que la demande a été approuvée et l'org créée.

    Args:
        request: Instance OrgCreationRequest avec status=approved.
    """
    payload = _build_payload("org_request.approved", request)
    logger.info(
        "org_request.approved id=%s org=%s reviewer=%s",
        request.id, request.name, request.reviewer.username if request.reviewer else "?",
    )
    _send_webhook(payload)


def notify_org_request_rejected(request) -> None:
    """Notifie que la demande a été refusée.

    Args:
        request: Instance OrgCreationRequest avec status=rejected.
    """
    payload = _build_payload("org_request.rejected", request)
    logger.info(
        "org_request.rejected id=%s org=%s reviewer=%s note=%s",
        request.id, request.name,
        request.reviewer.username if request.reviewer else "?",
        request.reviewer_note,
    )
    _send_webhook(payload)
