# ADR-002 — Stratégie d'authentification et d'autorisation

| Champ       | Valeur                      |
|-------------|-----------------------------|
| Date        | 2026-04-23                  |
| Statut      | **Accepté**                 |
| Décideurs   | Fares Chehidi               |

---

## Contexte

LedgerMind expose deux surfaces d'entrée distinctes avec des profils de risque
différents :

1. **API REST** (DRF) — consommée par le frontend Next.js et éventuellement des
   intégrations tierces (ERP, outils comptables). Requiert une auth stateless, scalable,
   compatible SPA.

2. **Admin Django** (`/admin/`) — accès backoffice pour les opérateurs LedgerMind
   uniquement. Requiert un niveau de sécurité maximal (pas de compromission token API
   ne doit donner accès à l'admin).

---

## Décision

### API REST — SimpleJWT

- **Access token** : JWT, durée de vie **5 minutes** (intentionnellement courte —
  données financières sensibles ; le frontend doit implémenter un intercepteur de
  rafraîchissement transparent avant expiration)
- **Refresh token** : JWT opaque stocké en cookie `HttpOnly; Secure; SameSite=Strict`,
  durée de vie **24 heures** (réduit à 7 jours en prod selon politique de sécurité org)
- **Rotation des refresh tokens** : activée (`ROTATE_REFRESH_TOKENS = True`) —
  chaque refresh invalide le précédent
- **Blacklist** : `rest_framework_simplejwt.token_blacklist` activée — logout serveur
  effectif

```python
# config/settings/base.py
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_COOKIE": "refresh_token",
    "AUTH_COOKIE_HTTP_ONLY": True,
    "AUTH_COOKIE_SECURE": True,       # False en dev (HTTP)
    "AUTH_COOKIE_SAMESITE": "Strict",
    "ALGORITHM": "HS256",
}
```

### Admin Django — Session + 2FA

- **Session Django** standard (cookie signé, `SESSION_COOKIE_SECURE=True` en prod)
- **django-two-factor-auth** — TOTP obligatoire pour tous les comptes staff
- **`/admin/` accessible uniquement depuis IP allowlist** (Traefik middleware —
  cf. ADR-002 collatéral dans docker-compose)
- **SESSION_COOKIE_AGE** : 4 heures (inactivité = déconnexion)

### Gestion des rôles (RBAC applicatif)

| Rôle | Périmètre |
|------|-----------|
| `org_owner` | Tous droits sur son organisation |
| `org_admin` | Gestion membres + accès lecture totale |
| `accountant` | Création/validation écritures |
| `auditor` | Lecture seule (audit, rapports) |
| `ledgermind_staff` | Admin backoffice (accès global, bypass tenant) |

Les rôles sont stockés dans `TenantMembership.role` — pas dans les groupes Django
(trop génériques pour le modèle multi-tenant).

---

## Alternatives rejetées

**OAuth2 + PKCE (Keycloak/Auth0)** : sur-ingénierie pour le MVP. Ajoute une dépendance
externe critique. Migrable vers OAuth2 si besoin d'intégrations SSO entreprise.

**JWT long-lived (24h+)** : inacceptable pour des données financières — une fuite de
token donne un accès prolongé.

**Même mécanisme pour API et Admin** : séparation intentionnelle — un token API volé
ne doit jamais permettre d'accéder à l'admin.

---

## Conséquences

**Positives :**
- Access tokens de courte durée = surface d'exposition minimale
- Refresh token HttpOnly = inaccessible depuis JavaScript (protection XSS)
- Admin 2FA = résistant au phishing et credential stuffing

**Négatives / risques :**
- Gestion du refresh token côté frontend (interceptor Axios/fetch)
- Blacklist nécessite une table PostgreSQL → légère latence sur logout
- 2FA = friction UX pour les opérateurs, acceptable pour une surface admin
