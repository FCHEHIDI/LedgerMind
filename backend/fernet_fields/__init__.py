"""
fernet_fields — Shim de compatibilité Django 5 pour django-fernet-fields 0.6.

django-fernet-fields 0.6 utilise `force_text` supprimé dans Django 4.0.
Ce shim réimplémente EncryptedCharField et EncryptedTextField avec
`cryptography.fernet` (déjà installé en tant que dépendance transitive)
et `force_str` (Django 3.0+).

Configuration :
    FERNET_KEYS (list[bytes]) — optionnel. Si absent, dérivé de SECRET_KEY.
    Exemple dans settings :
        FERNET_KEYS = [base64.urlsafe_b64encode(hashlib.sha256(force_bytes(SECRET_KEY)).digest())]

ADR-004 : Champs sensibles chiffrés (vendor_name, vendor_siren, montants, raw_text).
"""

import base64
import hashlib
import logging
from typing import Any, Optional

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import models
from django.utils.encoding import force_bytes, force_str

logger = logging.getLogger(__name__)


def _get_fernet() -> MultiFernet:
    """Instancie MultiFernet à partir de FERNET_KEYS ou de SECRET_KEY.

    Returns:
        MultiFernet prêt à chiffrer/déchiffrer.
    """
    keys = getattr(settings, "FERNET_KEYS", None)
    if keys:
        return MultiFernet([Fernet(k) for k in keys])
    # Fallback : dérive une clé Fernet valide depuis SECRET_KEY (dev uniquement)
    secret = force_bytes(settings.SECRET_KEY)
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return MultiFernet([Fernet(derived_key)])


class _EncryptedMixin:
    """Mixin qui chiffre/déchiffre la valeur en base de données via Fernet.

    Le champ est stocké comme TextField (texte chiffré base64) en base,
    et exposé comme str en Python.
    """

    def get_internal_type(self) -> str:
        """Force le stockage en TEXT quel que soit le type déclaré."""
        return "TextField"

    def from_db_value(
        self, value: Optional[str], expression: Any, connection: Any
    ) -> Optional[str]:
        """Déchiffre la valeur lue depuis la base de données.

        Args:
            value: Valeur chiffrée (base64) ou None.
            expression: Expression SQL (non utilisé).
            connection: Connexion DB (non utilisé).

        Returns:
            Valeur déchiffrée en str, ou None.
        """
        if value is None:
            return value
        try:
            return force_str(_get_fernet().decrypt(force_bytes(value)))
        except Exception as exc:  # noqa: BLE001
            logger.error("Erreur déchiffrement fernet : %s", exc)
            raise ValueError("Impossible de déchiffrer la valeur chiffrée.") from exc

    def get_prep_value(self, value: Optional[str]) -> Optional[str]:
        """Chiffre la valeur avant écriture en base de données.

        Args:
            value: Valeur Python en clair ou None.

        Returns:
            Valeur chiffrée (base64) en str, ou None.
        """
        if value is None:
            return value
        return force_str(_get_fernet().encrypt(force_bytes(value)))


class EncryptedCharField(_EncryptedMixin, models.TextField):
    """Champ texte court chiffré via Fernet. Stocké en TEXT côté PostgreSQL."""


class EncryptedTextField(_EncryptedMixin, models.TextField):
    """Champ texte long chiffré via Fernet. Stocké en TEXT côté PostgreSQL."""
