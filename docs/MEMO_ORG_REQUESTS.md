# Mémo technique — Workflow OrgCreationRequest

> Rédigé pour relecture rapide en cas de bug.  
> HEAD au moment de l'implémentation : `52d91ae`

---

## 1. Vue d'ensemble

```
Utilisateur                Next.js (proxy)           Django                        Akshi (optionnel)
    │                           │                        │                               │
    ├─ POST /api/org-requests ──►│                        │                               │
    │                           ├─ POST /api/v1/org-requests/ ──►│                       │
    │                           │                        ├─ crée OrgCreationRequest      │
    │                           │                        ├─ notify_submitted ────────────►│
    │                           │◄───────── 201 ─────────┤                               │
    │◄────── 201 ───────────────┤                        │                               │
    │                           │                        │                               │
Superuser                        │                        │                               │
    ├─ POST /api/org-requests/<id>/approve/ ──────────────►│                              │
    │                           │                        ├─ crée Organization             │
    │                           │                        ├─ crée TenantMembership(owner)  │
    │                           │                        ├─ request.status = approved     │
    │                           │                        ├─ notify_approved ─────────────►│
    │◄────── 200 ───────────────────────────────────────┤                               │
```

---

## 2. Modèle Django

**Fichier** : `backend/apps/tenants/models.py`  
**Table** : `tenants_org_creation_request`

| Champ | Type | Notes |
|-------|------|-------|
| `id` | UUIDField (PK) | auto-généré |
| `requester` | FK → User | `related_name="org_requests"` |
| `name` | CharField(255) | nom de l'org demandée |
| `siren` | CharField(9) | validé côté serializer (9 chiffres) |
| `message` | TextField | optionnel |
| `status` | CharField | `pending` / `approved` / `rejected`, indexé |
| `reviewer` | FK → User (nullable) | `related_name="reviewed_org_requests"` |
| `reviewer_note` | TextField | note de refus/approbation |
| `created_at` | DateTimeField(auto_now_add) | |
| `reviewed_at` | DateTimeField(nullable) | rempli à approve/reject |

**Migration** : `0003_add_org_creation_request.py` — déjà appliquée.

---

## 3. Endpoints Django

Base : `http://api.localhost:8888/api/v1/`

| Méthode | URL | Qui peut | Description |
|---------|-----|----------|-------------|
| POST | `org-requests/` | tout user auth | Soumettre une demande |
| GET | `org-requests/` | user = ses demandes, superuser = toutes | Lister |
| GET | `org-requests/<uuid>/` | idem | Détail |
| POST | `org-requests/<uuid>/approve/` | **superuser only** | Approuver |
| POST | `org-requests/<uuid>/reject/` | **superuser only** | Rejeter |

### Body approve/reject (optionnel)
```json
{ "reviewer_note": "Motif de refus ou note de validation" }
```

### Sécurité IDOR
`get_queryset()` filtre automatiquement : un user normal ne voit que ses propres demandes.  
Les actions `approve`/`reject` vérifient `request.user.is_superuser` → 403 sinon.

---

## 4. Serializers

**`OrgCreationRequestSerializer`** — lecture + création
- Champs en lecture seule : `id`, `status`, `requester_username`, `reviewer_username`, `reviewer_note`, `created_at`, `reviewed_at`
- Validation SIREN : exactement 9 chiffres (`\d{9}`)

**`OrgCreationRequestReviewSerializer`** — approve/reject body
- Un seul champ optionnel : `reviewer_note`

---

## 5. ViewSet — logique métier

**Fichier** : `backend/apps/api/views.py` → `OrgCreationRequestViewSet`

### `perform_create`
1. Sauvegarde avec `requester=request.user`
2. Appelle `notify_org_request_submitted(request_obj)`

### `@action approve/`
```python
with transaction.atomic():
    org = Organization.objects.create(name=req.name, siren=req.siren)
    TenantMembership.objects.create(
        user=req.requester, organization=org,
        role="org_owner", is_active=True
    )
    req.status = "approved"
    req.reviewer = request.user
    req.reviewer_note = note
    req.reviewed_at = now()
    req.save()
notify_org_request_approved(req)
```

### `@action reject/`
```python
req.status = "rejected"
req.reviewer = request.user
req.reviewer_note = note
req.reviewed_at = now()
req.save()
notify_org_request_rejected(req)
```

---

## 6. NotificationService

**Fichier** : `backend/apps/api/notifications.py`

### Comportement
- Lit `LEDGERMIND_NOTIFY_WEBHOOK_URL` depuis les variables d'env
- Si définie → POST JSON vers ce webhook (timeout 5s)
- **Best-effort** : les exceptions sont attrapées et loggées, jamais remontées
- Log INFO systématique même sans webhook

### Payload webhook
```json
{
  "event": "org_request.submitted | org_request.approved | org_request.rejected",
  "source": "ledgermind",
  "data": {
    "request_id": "<uuid>",
    "requester": "username",
    "org_name": "Acme SAS",
    "siren": "123456789",
    "status": "pending | approved | rejected",
    "reviewer": "admin_username | null",
    "note": "..."
  }
}
```

---

## 7. Proxy Next.js

| Fichier | Route frontend | Destination Django |
|---------|---------------|-------------------|
| `src/app/api/org-requests/route.ts` | GET/POST `/api/org-requests` | `/api/v1/org-requests/` |
| `src/app/api/org-requests/[id]/[action]/route.ts` | POST `/api/org-requests/<id>/approve\|reject` | `/api/v1/org-requests/<id>/approve\|reject/` |

Les deux utilisent `buildProxyHeaders()` (Authorization + X-Organization-Id depuis les cookies).

---

## 8. Frontend `/app` page

**Fichier** : `frontend/src/app/app/page.tsx`

### État ajouté
- `showModal` — ouvre/ferme le modal
- `myRequests` — demandes en statut `pending` récupérées via `GET /api/org-requests`
- `successMsg` — banner vert 6s après soumission réussie

### Comportements
- Badge orange sur le bouton "**+ Nouveau dossier**" si demandes en attente
- Banner ambré en haut du grid listant les demandes en attente
- SIREN : input limité à 9 chiffres, auto-strip non-chiffres, validation HTML5 `pattern="\d{9}"`
- Message vide state mis à jour : guide l'utilisateur vers le bouton au lieu de "contacter l'admin"

---

## 9. Akshi — Intégration observabilité

**Repo** : https://github.com/FCHEHIDI/Akshi  
**URL dev** : http://obs.localhost:8888 (après `docker compose --profile obs up`)

### Démarrage rapide
```bash
# Depuis C:/Users/Fares/LedgerMind/docker/
docker compose --profile obs up -d

# Migrations Akshi (1ère fois)
docker exec lm_akshi python manage.py migrate
docker exec lm_akshi python manage.py createsuperuser
```

### Configurer le webhook LedgerMind
1. Aller sur http://obs.localhost:8888/admin ou l'UI Akshi
2. Créer un **Notification Channel** de type `webhook`
3. Copier l'URL (ex: `http://akshi:8000/api/v1/notification-channels/<uuid>/trigger/`)
4. Dans `docker/docker-compose.dev.yml`, section `django > environment`, décommenter et remplir :
   ```yaml
   LEDGERMIND_NOTIFY_WEBHOOK_URL: http://akshi:8000/api/v1/notification-channels/<uuid>/trigger/
   ```
5. `docker compose restart django`

### Variables d'env Akshi (`.env` ou compose)
| Var | Défaut | Description |
|-----|--------|-------------|
| `AKSHI_DB_PASSWORD` | `sentinel_dev` | Mot de passe Postgres Akshi |
| `AKSHI_SECRET_KEY` | `akshi-dev-secret-change-me` | **Changer en prod !** |

---

## 10. Administration directe

Accès rapide sans passer par l'UI : http://api.localhost:8888/admin/tenants/orgcreationrequest/

- Filtre par statut (pending / approved / rejected)
- Champs `reviewer` et `reviewer_note` éditables directement
- Attention : passer par l'admin Django **ne déclenche PAS** les notifications Akshi (le signal n'est pas branché, uniquement les actions DRF)

---

## 11. Points de fragilité connus

| # | Risque | Mitigation |
|---|--------|------------|
| 1 | SIREN dupliqué entre deux `OrgCreationRequest` approuvées | Ajouter `unique_together` sur `Organization.siren` ou vérifier avant `approve` |
| 2 | Webhook Akshi down → log silencieux | Vérifier les logs Django : `grep "webhook" lm_django` |
| 3 | Double-clic sur approve → deux orgs créées | `transaction.atomic()` protège, mais ajouter un guard `status == pending` avant create |
| 4 | `OrgCreationRequest` approuvée mais membership raté | Le `transaction.atomic()` rollback tout en cas d'exception |
| 5 | Token expiré lors du submit modal | Le middleware Next.js rafraîchit silencieusement, mais si refresh aussi expiré → 401 → l'utilisateur voit "Erreur lors de la soumission" |

---

## 12. Commits liés

| Hash | Description |
|------|-------------|
| `584b2a8` | feat(backend): org-requests — workflow demande/approbation + NotificationService |
| `da9e88a` | feat(frontend): org-requests — modal demande nouveau dossier + proxy approve/reject |
| `52d91ae` | feat(infra): Akshi observability dans docker-compose.dev (profile obs) |
