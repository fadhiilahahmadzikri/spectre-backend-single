---
title: Spectre Backend
emoji: 👻
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
---

# Spectre

AI-Powered Facial Authentication Platform.

## Overview

Spectre is a production-grade facial authentication API that provides:

- **Face Registration** — Enroll users with liveness-verified face embeddings
- **Face Authentication** — Verify identity against stored profiles
- **Anti-Spoofing** — Real-time liveness detection via AntiSpoofNetV4
- **Multi-Tenant** — Isolated per-application face databases with API key auth
- **Webhook Delivery** — Async event notifications with HMAC-signed payloads
- **OAuth Integration** — Google OAuth2 login support
- **TOTP 2FA** — Time-based one-time password for dashboard access

## Live Deployment

| Environment | URL | Status |
|---|---|---|
| **Production (HF Spaces)** | https://thewhitenigs-spectre-backend.hf.space | ✅ Live |
| **Swagger UI** | https://thewhitenigs-spectre-backend.hf.space/docs | ✅ |
| **Health Check** | https://thewhitenigs-spectre-backend.hf.space/health | ✅ |

### Quick Test

```bash
curl https://thewhitenigs-spectre-backend.hf.space/health
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HF Spaces Container                    │
│                                                          │
│  ┌──────────┐  ┌───────┐  ┌──────────┐  ┌───────────┐  │
│  │ FastAPI  │  │ Redis │  │ PostgreSQL│  │  Celery   │  │
│  │ :7860    │  │ :6379 │  │  :5432   │  │  Worker   │  │
│  └──────────┘  └───────┘  └──────────┘  └───────────┘  │
│                    supervisord                            │
└─────────────────────────────────────────────────────────┘
```

**Stack:** Python 3.11 · FastAPI · SQLAlchemy (async) · PostgreSQL 16 · Redis 7 · Celery · TensorFlow/Keras · InsightFace

## Local Development

### Option A: Full Docker (zero local deps)

```powershell
git clone <repo>
cd spectre
make docker-dev
```

This starts the entire stack — API, database, Redis, Celery worker, — in Docker. No Python, no Node, no local installs needed.

- **API:** http://localhost:8000
- **Swagger:** http://localhost:8000/docs

### Option B: Local Python + Docker infra

```powershell
# Start Postgres + Redis
make docker-up

# Install dependencies
make install

# Run migrations + seed
make migrate
make seed

# Start server
make dev-win
```

## Makefile Commands

Run `make help` for the full list. Key commands:

| Command | Purpose |
|---|---|
| `make docker-dev` | Start full containerized stack |
| `make dev-win` | Start local dev server (Windows) |
| `make test` | Run all pytest tests |
| `make test-newman` | Run Newman API tests (local) |
| `make test-newman-hf` | Run Newman API tests (HF Spaces) |
| `make docs` | Open Swagger UI (local) |
| `make docs-hf` | Open Swagger UI (HF Spaces) |
| `make health` | Check local API health |
| `make health-hf` | Check HF Spaces health |
| `make migrate` | Run database migrations |
| `make seed` | Seed database |
| `make lint` | Run linter |
| `make check` | Lint + typecheck |
| `make ci` | Full CI pipeline |
| `make bootstrap` | One-command project setup |
| `make docker-reset` | Nuclear reset + rebuild |

## API Authentication

Two auth mechanisms:

| Mechanism | Used For | Header |
|---|---|---|
| **JWT Bearer** | Dashboard (apps, keys, sessions, webhooks) | `Authorization: Bearer <token>` |
| **API Key** | Face operations (register, authenticate) | `X-API-Key: spk_...` |

### Pre-provisioned API Key (HF Spaces)

For immediate testing against the live deployment:

```
X-API-Key: spk_d602c7bc949464b18c0fafc1c3c5d4f048bf2a524acad217
```

## API Endpoints (31 total)

| Group | Endpoints | Auth |
|---|---|---|
| Health | `GET /`, `GET /health`, `GET /health/ml-status` | None |
| Auth | Register, Login, Verify Email, TOTP, OAuth, Refresh, Logout | None / Bearer |
| Applications | CRUD for tenant apps | Bearer |
| API Keys | Generate, List, Revoke | Bearer |
| Face Ops | Register, Authenticate, Replace, Delete, List, Purge, Benchmark | X-API-Key |
| Sessions | List, Get detail | Bearer / X-API-Key |
| Webhooks | Test, List deliveries, Retry | Bearer |
| Telemetry | Client log ingestion | X-API-Key |
| Admin | Config CRUD, FAS Models list, Stats, Automation | Bearer (admin) |

Full integration reference: [`Docs/API_INTEGRATION_REFERENCE.md`](Docs/API_INTEGRATION_REFERENCE.md)  
HF Spaces-specific guide: [`Docs/API_HF_SPACES_REFERENCE.md`](Docs/API_HF_SPACES_REFERENCE.md)

## Testing

```powershell
# Unit tests (mocked infra)
make test-unit

# Integration tests (requires DB)
make test-integration

# Newman contract tests — local
make test-newman

# Newman contract tests — HF Spaces
make test-newman-hf

# Full suite
make test-all

# Coverage report
make test-cov
```

## Project Structure

```
spectre/
├── src/spectre/              # Application source
│   ├── application/          # Use cases (business logic)
│   ├── domain/               # Entities, value objects, ports
│   ├── infrastructure/       # DB, ML, cache, security, email
│   ├── interface/            # Routers, schemas, middleware
│   └── workers/              # Celery tasks
├── tests/                    # pytest + Newman collections
├── migrations/               # Alembic DB migrations
├── seeds/                    # Database seeders
├── artifact/                 # ML model weights
├── Docs/                     # API references
├── docker-compose.dev.yml    # Full dev stack
├── Dockerfile                # HF Spaces (all-in-one)
├── Dockerfile.local          # Multi-stage (API only)
└── Makefile                  # All operational commands
```

## License

Proprietary