# =============================================================================
# LedgerMind Backend — Dockerfile
# Multi-stage build: builder (deps) + runner (production image)
# =============================================================================
# Stage 1: builder — installe les dépendances Python dans un venv isolé
FROM python:3.11-slim AS builder

WORKDIR /app

# Dépendances système pour psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crée le virtualenv et installe les dépendances prod
COPY requirements/base.txt requirements/prod.txt ./requirements/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements/prod.txt

# =============================================================================
# Stage 2: runner — image minimale de production
FROM python:3.11-slim AS runner

# Utilisateur non-root pour la sécurité
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --no-create-home appuser

WORKDIR /app

# Dépendances runtime seulement
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copie le venv depuis le builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings.prod

# Copie le code applicatif
COPY . .

# Répertoires pour les fichiers statiques et media (montés en volume en prod)
RUN mkdir -p staticfiles media \
    && chown -R appuser:appgroup /app

USER appuser

# Collecte des fichiers statiques (sans DB — settings DB optionnels ici)
# Désactivé ici : effectué dans le entrypoint ou la CI
# RUN python manage.py collectstatic --noinput

EXPOSE 8000

# Gunicorn : 4 workers, timeout 120s, accès via socket unix ou TCP
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "config.wsgi:application"]
