#!/bin/bash
# ==============================================================================
# Spectre — HF Spaces Startup Script (Enterprise Edition)
# ==============================================================================

set -e

echo "=============================================="
echo "  Spectre — Starting up on Hugging Face Spaces"
echo "=============================================="

# ---- Environment setup ----
export PATH="/app/.venv/bin:$PATH"
export PYTHONPATH="/app/src:$PYTHONPATH"
export PYTHONUNBUFFERED=1

# ---- Auto-detect PostgreSQL version ----
PG_VERSION=$(ls /usr/lib/postgresql/ | head -1)
export PG_BIN="/usr/lib/postgresql/${PG_VERSION}/bin"

# ---- Database Mode Detection ----
export PG_AUTOSTART=true
IS_EXTERNAL_DB=false

if [[ "$DATABASE_URL" == *"supabase"* ]] || [[ "$DATABASE_URL" == *"pooler"* ]]; then
    echo "[init] External Database detected (Supabase). Using remote storage."
    IS_EXTERNAL_DB=true
    export PG_AUTOSTART=false
fi

# ---- Local PostgreSQL Setup (Skip if external) ----
if [ "$IS_EXTERNAL_DB" = false ]; then
    PG_DATA="/var/lib/postgresql/data"
    if [ ! -f "$PG_DATA/PG_VERSION" ]; then
        echo "[init] Initializing PostgreSQL data directory..."
        su postgres -c "$PG_BIN/initdb -D $PG_DATA --encoding=UTF8 --locale=C"

        cat > "$PG_DATA/pg_hba.conf" <<EOF
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
EOF

        cat >> "$PG_DATA/postgresql.conf" <<EOF
shared_buffers = 64MB
max_connections = 30
logging_collector = off
EOF
        echo "[init] PostgreSQL data directory initialized."
    fi

    echo "[init] Starting PostgreSQL temporarily for setup..."
    su postgres -c "$PG_BIN/pg_ctl -D $PG_DATA -l /tmp/pg_init.log start -w -t 60"

    echo "[init] Creating local database and user..."
    su postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='spectre'\"" | grep -q 1 \
        || su postgres -c "psql -c \"CREATE ROLE spectre WITH LOGIN PASSWORD 'spectre';\""
    su postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='spectre'\"" | grep -q 1 \
        || su postgres -c "psql -c \"CREATE DATABASE spectre OWNER spectre;\""
    su postgres -c "psql -d spectre -c \"GRANT ALL ON SCHEMA public TO spectre;\""
fi

# ---- Service Readiness Checks ----
wait_for_redis() {
    echo "[init] Waiting for Redis readiness..."
    local retries=30
    # If redis-server is not running yet (it will be started by supervisor), 
    # we just need to ensure the local port is eventually available.
    # However, since supervisor starts it, we'll start it temporarily 
    # if we need it for seeds/migrations, or just let supervisord handle the retry.
    # For HF simplicity, we start it temporarily if it's not up.
    redis-server --port 6379 --daemonize yes
    until redis-cli -p 6379 ping > /dev/null 2>&1 || [ $retries -eq 0 ]; do
        retries=$((retries - 1))
        sleep 1
    done
    echo "[init] Redis is ready."
}

wait_for_db() {
    echo "[init] Verifying database connectivity..."
    if [ "$IS_EXTERNAL_DB" = false ]; then
        until su postgres -c "$PG_BIN/pg_isready -q"; do sleep 1; done
    fi
    # Alembic check provides a real connection test for remote DBs
    python -m alembic upgrade head || { echo "[init] FATAL: Migration failed."; exit 1; }
    echo "[init] Database is ready and migrated."
}

wait_for_redis
wait_for_db

# ---- Database Seeds ----
if [ "$IS_EXTERNAL_DB" = false ]; then
    echo "[init] Local DB detected. Running seeds..."
    python -m seeds all || echo "[init] Seeding failed."
fi

# ---- Stop temporary services (Supervisor will take over) ----
echo "[init] Cleaning up temporary setup services..."
redis-cli -p 6379 shutdown || true
if [ "$IS_EXTERNAL_DB" = false ]; then
    su postgres -c "$PG_BIN/pg_ctl -D $PG_DATA stop -w -t 10" || true
fi

# ---- Final Config Generation (Enterprise Pattern - Zero Dependency) ----
echo "[init] Rendering supervisord configuration from template..."
python -c "import os; from string import Template; t = Template(open('/etc/supervisor/conf.d/spectre.conf.tmpl').read()); open('/etc/supervisor/conf.d/spectre.conf', 'w').write(t.safe_substitute(os.environ))"

echo "=============================================="
echo "  Spectre — Launching Supervisord"
echo "=============================================="
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/spectre.conf
