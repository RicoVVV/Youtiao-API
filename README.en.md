# Youtiao API

[简体中文](README.md) | **English**

Youtiao API is an open-source AI model aggregation gateway: use a single `sk-` key to access
text, image, and video models, with multi-vendor protocol adapters, usage-based billing, wallet
and payments, usage statistics, monitoring and alerting, and a full management console.

## Features

- **Unified gateway**: call every model with one API key. Change a single `baseURL` to integrate, and it works with the OpenAI SDK.
- **Multi-vendor adapters**: built-in adapters for Anthropic (Claude), Google Gemini, OpenAI-compatible, Alibaba Cloud DashScope (Qwen), Volcengine Ark (Doubao Seed), FAL, MiniMax, and more.
- **Multi-protocol compatibility**: exposes OpenAI (text / image / video / models / Responses), Anthropic Messages, Gemini, Volcengine Ark Responses, and DashScope text & multimodal protocol surfaces.
- **Smart routing & concurrency control**: multi-channel routing, model mapping, per-group concurrency limits, and peak load distribution.
- **Pricing & billing**: precise metering by tokens, image count, and video duration, with pricing rules, multipliers, and cache-billing items.
- **Users & tokens**: registration and login, token groups, and per-key permission and quota management.
- **Wallet & payments**: balance, top-up, and redemption codes, supporting Alipay (official), Epay, and Stripe.
- **Usage statistics**: call records and daily aggregated statistics, queryable in real time.
- **Monitoring & alerting**: group business metrics and server resource monitoring, with DingTalk webhook alerts.
- **Console & i18n**: Next.js management console, model marketplace, and API docs, with built-in Chinese and English.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python ≥ 3.11, FastAPI, SQLAlchemy / SQLModel, Alembic, Pydantic v2 |
| Database / Cache | PostgreSQL 16, Redis 7 |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, Radix UI, i18next |
| Deployment | Docker, Docker Compose, Nginx, Gunicorn + Uvicorn |

## Architecture Overview

```
                    ┌───────────────┐
   Browser / SDK ─▶ │   Nginx :80   │
                    └───────┬───────┘
           / (pages)│               │ /api, /v1, /v1beta (APIs)
                    ▼               ▼
            ┌───────────────┐  ┌────────────────┐
            │ Frontend      │  │ API (FastAPI)  │
            │ Next.js :3000 │  │ Gunicorn :8000 │
            └───────────────┘  └────────┬───────┘
                                      ▼
                          ┌───────────────────────┐
                          │ PostgreSQL  /  Redis  │
                          └───────────────────────┘
                                      ▼
                     Upstream providers (Anthropic / Gemini / OpenAI / Qwen / Doubao / FAL / MiniMax ...)
```

Nginx is the single entry point: page routes are proxied to the frontend, while `/api`, `/v1`,
and `/v1beta` go directly to the backend, with response buffering and gzip disabled for
streaming endpoints.

## Directory Structure

```
Youtiao-API/
├── backend/          FastAPI service
│   ├── app/
│   │   ├── bootstrap/      App assembly (routes, middleware, lifespan)
│   │   ├── core/           Config, auth, database, logging, errors, protocol registry
│   │   ├── infrastructure/ HTTP, Redis, system metrics
│   │   ├── modules/        Domain modules (see below)
│   │   └── web/            Request context, response and streaming helpers
│   ├── alembic/            Database migrations
│   └── tests/              Tests
├── frontend/         Next.js website and console
│   ├── app/[locale]/       Page routes (home, marketplace, docs, console, system settings)
│   ├── components/         UI and business components
│   └── i18n/               Chinese and English copy
├── docker/           Dockerfile, docker-compose.yml, Nginx config and deployment env template
├── LICENSE
├── README.md
└── README.en.md
```

Backend domain modules: `admin` (admin APIs), `user` (auth / tokens / profile),
`channels` (channels and routing), `providers` (upstream adapters), `generation` (text / image
generation), `video` (async video tasks), `pricing` and `billing` (pricing and billing),
`wallet` and `payment` (wallet and payments), `usage` (usage statistics), `monitoring`
(monitoring and alerting), `marketplace` and `model_catalog` (model marketplace and matching),
`system_settings` and `system_tasks` (system settings and scheduled tasks).

## Quick Start

### Option 1: Docker Compose (recommended)

Requires Docker and Docker Compose.

```bash
cd docker
cp .env.example .env
# Edit .env and provide at least the following three values (startup fails without them):
#   POSTGRES_PASSWORD      database password
#   JWT_SIGNING_KEY        a random string of at least 32 characters
#   REFRESH_TOKEN_PEPPER   another random string of at least 32 characters
docker compose up -d --build
```

Once up, open `http://localhost:3000` (change the port via `FRONTEND_PORT`).
The first visit guides you to create an admin account at `/setup`.

### Option 2: Local development

Backend (requires a local PostgreSQL; Redis is optional for session caching, and auth falls back
to the database when it is unavailable):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # configure DATABASE_URL at minimum
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
# create .env.local and set API_BASE_URL=http://localhost:8000
# (Next.js rewrites proxy /api to the backend based on this)
npm run dev
```

Open `http://localhost:3000`.

## Configuration

| File | Purpose |
| --- | --- |
| [docker/.env.example](docker/.env.example) | Docker Compose deployment; copy to `docker/.env` |
| [backend/.env.example](backend/.env.example) | Running the backend directly; copy to `backend/.env` |

Only `DATABASE_URL` is required for the backend; every other variable has a code default (see
[backend/app/core/config.py](backend/app/core/config.py)). Non-`development` environments enforce
the strength of the JWT key and refresh token pepper.

## Security Notes

- **Never commit `.env`**: `.gitignore` already ignores `.env`, `docker/.env`, and similar files.
- **Secrets come from the environment**: the database password, JWT key, and payment encryption key are never hardcoded; supply them via environment variables.
- **JWT_SIGNING_KEY / REFRESH_TOKEN_PEPPER** leakage allows tokens to be forged — use sufficiently long random values and keep them safe.
- **PAYMENT_CONFIG_ENCRYPTION_KEY** encrypts payment credentials (Fernet); generate it with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Changing it makes previously stored payment credentials undecryptable.

## API Surfaces

APIs are exposed on the following paths (proxied directly to the backend by Nginx):

- `/v1/**`, `/v1beta/**`: client-SDK compatible endpoints (OpenAI / Anthropic / Gemini / Volcengine Ark / DashScope protocols, etc.).
- `/api/**`: platform management APIs, plus native vendor surfaces such as Qwen and Ark.

In development, the backend ships interactive docs at `http://localhost:8000/api/docs`
(disabled in production by default).

## License

This project is licensed under the [MIT License](LICENSE).
