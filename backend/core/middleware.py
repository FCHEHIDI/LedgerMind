"""
core/middleware.py — TenantMiddleware (ADR-001).

Injecte l'org_id du tenant courant dans la session PostgreSQL via
`SET LOCAL app.current_org_id = %s` avant chaque requête ORM.

Ce middleware DOIT être le dernier dans MIDDLEWARE (après AuthenticationMiddleware)
pour que request.user soit disponible.

Sécurité:
  - Si l'utilisateur n'est pas authentifié, org_id n'est pas setté
    (les RLS policies rejettent toutes les requêtes sans org_id).
  - Si l'utilisateur a plusieurs memberships actifs, le premier actif
    est utilisé ; l'API peut changer d'org via le header X-Organization-Id.
  - L'org_id est validé UUID v4 avant d'être passé à PostgreSQL.
"""
import logging
import re
import uuid
from typing import Callable

from django.db import connection
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("core.middleware")

# UUID v4 pattern — validated before passing to PostgreSQL
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_valid_uuid4(value: str) -> bool:
    """Validate that value is a well-formed UUID v4.

    Args:
        value: String to validate.

    Returns:
        True if value is a valid UUID v4, False otherwise.
    """
    return bool(_UUID_RE.match(value))


class TenantMiddleware:
    """Middleware d'isolation tenant — injecte org_id dans la connexion PostgreSQL.

    Appelé sur chaque requête HTTP après que request.user est disponible.
    Utilise SET LOCAL (transaction-scoped) pour la sécurité : l'org_id
    est automatiquement effacé à la fin de la transaction.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Initialise le middleware.

        Args:
            get_response: Callable Django vers le prochain middleware/view.
        """
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Traite la requête en injectant org_id dans PostgreSQL si authentifié.

        Args:
            request: Requête HTTP Django.

        Returns:
            Réponse HTTP.
        """
        org_id = self._resolve_org_id(request)

        if org_id is not None:
            # SET LOCAL — transaction-scoped, effacé automatiquement après commit
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.current_org_id', %s, TRUE)",
                    [str(org_id)],
                )
            logger.debug("tenant_middleware: org_id=%s set for request", org_id)
        else:
            logger.debug("tenant_middleware: no org_id (unauthenticated or no membership)")

        return self.get_response(request)

    def _resolve_org_id(self, request: HttpRequest) -> uuid.UUID | None:
        """Résout l'org_id pour la requête courante.

        Priorité:
          1. Header X-Organization-Id (multi-org users)
          2. Premier membership actif de l'utilisateur

        Args:
            request: Requête HTTP Django.

        Returns:
            UUID de l'organisation ou None si non résolu.
        """
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return None

        # Priority 1: explicit org selection via header
        header_org_id = request.headers.get("X-Organization-Id", "").strip()
        if header_org_id:
            if not _is_valid_uuid4(header_org_id):
                logger.warning(
                    "tenant_middleware: invalid X-Organization-Id header format"
                )
                return None
            # Verify user is actually a member of this org
            from apps.tenants.models import TenantMembership

            has_membership = TenantMembership.objects.filter(
                user=request.user,
                organization_id=header_org_id,
                is_active=True,
            ).exists()
            if has_membership:
                return uuid.UUID(header_org_id)
            logger.warning(
                "tenant_middleware: user has no active membership in requested org"
            )
            return None

        # Priority 2: first active membership
        from apps.tenants.models import TenantMembership

        membership = (
            TenantMembership.objects.filter(
                user=request.user,
                is_active=True,
            )
            .select_related("organization")
            .first()
        )
        if membership:
            return membership.organization_id

        return None
