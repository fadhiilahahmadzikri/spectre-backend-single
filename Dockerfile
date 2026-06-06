# ==============================================================================
# Spectre — Dockerfile for Hugging Face Spaces (Docker SDK)
#
# Bundles: PostgreSQL 15 · Redis 7 · FastAPI (uvicorn)
# All processes managed by supervisord inside a single container.
# Original local Dockerfile preserved as Dockerfile.local.
# ==============================================================================

FROM python:3.11-slim

# ---- Prevent interactive prompts during apt-get ----
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# ---- System dependencies ----
# PostgreSQL, Redis, supervisord, OpenCV runtime libs, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    # --- Database ---
    postgresql \
    postgresql-client \
    # --- Cache ---
    redis-server \
    # --- Process manager ---
    supervisor \
    # --- Build deps for Python wheels ---
    build-essential \
    libpq-dev \
    # --- OpenCV / PIL runtime ---
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    # --- Healthcheck ---
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---- Install uv (fast Python package manager) ----
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ---- Install Python dependencies ----
COPY pyproject.toml uv.lock* README.md ./
RUN uv sync --frozen --no-dev --no-editable 2>/dev/null \
    || uv sync --no-dev --no-editable

# ---- Remove build dependencies to slim down image ----
RUN apt-get purge -y build-essential libpq-dev && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# ---- Copy application source ----
COPY src/ src/
COPY alembic.ini .
COPY migrations/ migrations/
COPY seeds/ seeds/

# ---- Copy ML model weights ----
# ~206 MB — handled by HF LFS automatically
COPY artifact/ artifact/

# ---- Copy orchestration files ----
COPY supervisord.conf.tmpl /etc/supervisor/conf.d/spectre.conf.tmpl
COPY start.sh /app/start.sh


# ---- Directory setup ----
RUN chmod +x /app/start.sh \
    && mkdir -p /app/logs/app /app/logs/error /app/logs/access \
    && mkdir -p /var/run/postgresql /var/log/supervisor \
    # PostgreSQL data directory
    && mkdir -p /var/lib/postgresql/data \
    && chown -R postgres:postgres /var/lib/postgresql/data \
    && chown -R postgres:postgres /var/run/postgresql \
    && chmod 0700 /var/lib/postgresql/data

# ---- Environment variables ----
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:$PYTHONPATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ---- HF Spaces requires port 7860 ----
EXPOSE 7860

# ---- Health check ----
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# ---- Entrypoint: init DB → migrations → supervisord ----
CMD ["/app/start.sh"]
