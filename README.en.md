<div align="center">

![Youtiao API](frontend/public/youtiao.svg)

# Youtiao API

**An AI model aggregation gateway for applications and teams**

<p align="center">
  <a href="./README.md">简体中文</a> |
  <strong>English</strong>
</p>

<p align="center">
  <a href="#project-description">Project Description</a> •
  <a href="#capabilities">Capabilities</a> •
  <a href="#protocols-and-endpoints">Protocols and endpoints</a> •
  <a href="#quick-start">Quick start</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#development">Development</a> •
  <a href="#documentation">Documentation</a>
</p>

</div>

---

## Project Description

Youtiao API is a self-hosted AI model aggregation gateway: use a single `sk-` key to access
text, image, and video models, expose a consistent compatible API to your clients, and manage
routing, access, billing, and usage in one console.

Use it to share authorized model access across a team, switch providers without reconfiguring every
client, or operate a private multi-model service with a web console. Upstreams include Anthropic
(Claude), Google Gemini, OpenAI-compatible services, Alibaba Cloud DashScope (Qwen), Volcengine
Ark (Doubao Seed), FAL, MiniMax, and more.

> [!IMPORTANT]
> - This project is intended solely for lawful and authorized AI API gateway, organization-level authentication, multi-model management, usage analytics, and private deployment scenarios.
> - Users must lawfully obtain upstream API keys, accounts, model services, and interface permissions, and must comply with upstream terms of service and applicable laws and regulations.
> - When providing generative AI services to the public, users should complete all required filing, licensing, content safety, real-name verification, log retention, and tax obligations required by their jurisdiction.

> [!WARNING]
> Before operating this project as a public generative AI service or API resale service, complete all
> required filing, licensing, content safety, real-name verification, log retention, tax, payment, and
> upstream authorization obligations.

---

## Capabilities

| Area | What you can do |
| --- | --- |
| Unified gateway | Call every model with one API key. Change a single `baseURL` to integrate, and it works with the OpenAI SDK |
| Multi-vendor adapters | Built-in adapters for Anthropic, Google Gemini, OpenAI-compatible, Alibaba Cloud DashScope (Qwen), Volcengine Ark (Doubao Seed), FAL, and MiniMax |
| Multi-protocol compatibility | Exposes OpenAI (text / image / video / models / Responses), Anthropic Messages, Gemini, Volcengine Ark Responses, and DashScope text & multimodal protocol surfaces |
| Smart routing & concurrency | Multi-channel routing, model name mapping, per-group concurrency limits, and peak load distribution |
| Pricing & billing | Precise metering by tokens, image count, and video duration, with pricing rules, multipliers, and cache-billing items |
| Users & tokens | Registration and login, token groups, and per-key permission and quota management |
| Wallet & payments | Balance, top-up, and redemption codes, supporting Alipay (official), Epay, and Stripe |
| Usage statistics | Call records and daily aggregated statistics, filterable by type, model, key, and status, queryable in real time |
| Monitoring & alerting | Group / channel business metrics and server resource monitoring, with DingTalk webhook alerts |
| Console & i18n | Next.js management console, model marketplace, API docs, and a chat canvas, with built-in Chinese and English |

## Protocols and endpoints

| Interface | Common endpoints |
| --- | --- |
| OpenAI Chat / Responses | `POST /v1/chat/completions`, `POST /v1/responses` |
| OpenAI model list | `GET /v1/models` |
| Anthropic Messages | `POST /v1/messages` |
| Gemini | `GET /v1beta/models`, `POST /v1beta/models/{model}:generateContent`, `POST /v1beta/models/{model}:streamGenerateContent` |
| OpenAI images | `POST /v1/images/generations`, `POST /v1/images/edits` |
| OpenAI videos | `POST /v1/videos`, `GET /v1/videos/{video_id}`, `GET /v1/videos/{video_id}/content` |
| Alibaba Cloud DashScope | `POST /api/v1/services/aigc/text-generation/generation`, `POST /api/v1/services/aigc/multimodal-generation/generation` |
| Volcengine Ark Responses | `POST /api/v3/responses` |

Public interfaces are mounted on `/v1/**`, `/v1beta/**`, and some `/api/**` paths; platform management
APIs live under `/api/**`. Available features depend on the channel, upstream model, and protocol mapping.

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

### Use Docker Compose

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

### Make your first request

1. Create a channel in **Channels**, fill in the upstream base URL and API key, select the available models and token group, and run the test.
2. Register the public model under **Models** and configure its pricing; make sure the user has balance or quota.
3. Create a key under **API Keys**; its group and model scope must match the channel.
4. Set your client `baseURL` to `http://localhost:3000/v1` and use the platform-issued `sk-` key.

Export the key, then list the accessible models:

```bash
export YOUTIAO_API_KEY=sk-xxxxxxxx
curl --fail-with-body http://localhost:3000/v1/models \
  -H "Authorization: Bearer ${YOUTIAO_API_KEY}"
```

Then send a chat completion, replacing `your-enabled-model` with an enabled model name:

```bash
curl --fail-with-body http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer ${YOUTIAO_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"your-enabled-model","messages":[{"role":"user","content":"Hello"}]}'
```

## Deployment

### Docker Compose (recommended)

The [Compose configuration](docker/docker-compose.yml) starts **Nginx + frontend + API + PostgreSQL + Redis**,
with only Nginx exposing a port; the other services communicate on the internal network.

```bash
cd docker
cp .env.example .env
docker compose up -d --build
docker compose logs -f api
```

### Storage and configuration

| Component | Options |
| --- | --- |
| Main database | PostgreSQL 16 |
| Cache | Redis 7 (JWT session-validation cache; auth falls back to the database when unavailable) |
| Media storage | The `/app/media` volume inside the API container (video outputs and input materials) |
| Container platforms | Linux amd64 / arm64 |

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Database password, **required**; Compose exits with an error when missing |
| `JWT_SIGNING_KEY` | Access-token HS256 signing key, **required**; strength is enforced outside development |
| `REFRESH_TOKEN_PEPPER` | Refresh-token digest pepper, **required**; strength is enforced outside development |
| `DATABASE_URL` | Database connection string; Compose assembles it from `POSTGRES_*` automatically |
| `AUTH_REDIS_URL` | Redis connection used only for session-validation caching |
| `PAYMENT_CONFIG_ENCRYPTION_KEY` | Payment credential encryption key (Fernet); only needed when payments are enabled |
| `PUBLIC_BASE_URL` | Public base URL used to generate absolute asset-download links |
| `FRONTEND_PORT` | Nginx public port, default `3000` |
| `APP_ENV` | Runtime environment; non-`development` enforces key strength |

See [docker/.env.example](docker/.env.example), [backend/.env.example](backend/.env.example), and
[backend/app/core/config.py](backend/app/core/config.py) for the full variable reference and defaults.

### Security Notes

- **Never commit `.env`**: `.gitignore` already ignores `.env`, `docker/.env`, and similar files.
- **Secrets come from the environment**: the database password, JWT key, and payment encryption key are never hardcoded; supply them via environment variables.
- **JWT_SIGNING_KEY / REFRESH_TOKEN_PEPPER** leakage allows tokens to be forged — use sufficiently long random values and keep them safe.
- **PAYMENT_CONFIG_ENCRYPTION_KEY** encrypts payment credentials (Fernet); generate it with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Changing it makes previously stored payment credentials undecryptable.

## Development

The backend uses Python ≥ 3.11 and FastAPI; the frontend uses Next.js (App Router) and React.

### Backend (requires a local PostgreSQL; Redis optional)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # configure DATABASE_URL at minimum
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

In development, the backend ships interactive docs at `http://localhost:8000/api/docs`
(disabled in production by default).

### Frontend

```bash
cd frontend
npm install
# create .env.local and set API_BASE_URL=http://localhost:8000
# (Next.js rewrites proxy /api to the backend based on this)
npm run dev
```

Open `http://localhost:3000`.

| Location | Responsibility |
| --- | --- |
| [backend/app/bootstrap](backend/app/bootstrap) | App assembly: route registration, middleware, lifespan |
| [backend/app/core](backend/app/core) | Config, auth, database, logging, errors, and the protocol registry |
| [backend/app/modules](backend/app/modules) | Domain modules and upstream provider adapters |
| [backend/app/web](backend/app/web) | Request context, unified responses, and streaming helpers |
| [frontend/app](frontend/app) | Page routes (home, marketplace, docs, console, system settings) |
| [frontend/components](frontend/components) | UI and business components |
| [docker](docker) | Dockerfile, Compose, Nginx config and deployment env template |

Backend tests and checks:

```bash
cd backend
pytest
ruff check .
```

## Documentation

| Resource | Link |
| --- | --- |
| Development API docs | `http://localhost:8000/api/docs` |

## License

This project is licensed under the [MIT License](LICENSE).
