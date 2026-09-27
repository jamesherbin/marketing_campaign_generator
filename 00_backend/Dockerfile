# syntax=docker/dockerfile:1.7

FROM python:3.11.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app/00_backend

# Install dependencies separately so source-only changes reuse this layer.
COPY 00_backend/requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

# Use a fixed, unprivileged runtime identity. Cloud Run supplies Google
# credentials through the attached service account; no key is copied in.
RUN groupadd --system --gid 10001 appgroup \
    && useradd --system --uid 10001 --gid appgroup --home-dir /app --shell /usr/sbin/nologin appuser

COPY --chown=appuser:appgroup 00_backend/campaign ./campaign
COPY --chown=appuser:appgroup 00_backend/main.py ./main.py
COPY --chown=appuser:appgroup agents /app/agents

USER appuser:appgroup

EXPOSE 8080
STOPSIGNAL SIGTERM

# main.py reads Cloud Run's PORT variable through the typed Settings model and
# starts Uvicorn on 0.0.0.0. A single worker keeps process behavior predictable;
# durable campaign state is shared through PostgreSQL.
CMD ["python", "main.py"]
