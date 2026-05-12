# JarviisAI — Autonomous Testing & Deployment Platform

**Zero human QA. AI-native. Production-ready.**

JarviisAI autonomously tests, deploys, and heals software. It crawls your app, generates test suites using Claude AI, executes them across browsers and devices, self-heals broken selectors, and manages your entire deployment pipeline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14)  :3000                            │
├─────────────────────────────────────────────────────────┤
│  API Gateway            :8000  (single entry point)      │
├────────────────┬────────────────┬───────────────────────┤
│  Core Services │  SaaS Services │  Infrastructure        │
│  auth    :8001 │  events  :8017 │  PostgreSQL 16  :5432  │
│  projects:8002 │  usage   :8018 │  Redis 7        :6379  │
│  crawler :8003 │  notifs  :8019 │  Prometheus     :9090  │
│  ai      :8004 │  analytics:8020│  Grafana        :3001  │
│  executor:8005 │  reports :8021 │  OTel Collector :4317  │
│  healing :8006 │  flags   :8022 │  Nginx          :80    │
│  visual  :8007 │  audit   :8023 │                        │
│  deploy  :8008 │  search  :8024 │                        │
│  api-test:8009 │  comply  :8025 │                        │
│  security:8010 │  health  :8026 │                        │
│  jarviis :8012 │                │                        │
│  cobol   :8013 │                │                        │
│  billing :8014 │                │                        │
│  sso     :8015 │                │                        │
│  mobile  :8016 │                │                        │
└────────────────┴────────────────┴───────────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker 24+ and Docker Compose v2
- Node.js 20+ (for local frontend dev)
- Python 3.12+ (for local service dev)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/jarviisai.git
cd jarviisai
cp .env.example .env
```

### 2. Set required environment variables

Edit `.env` — **minimum required**:

```bash
# Auth
JWT_SECRET=your_secret_minimum_32_characters_here
SECRET_KEY=your_app_secret_32_chars_here

# AI
ANTHROPIC_API_KEY=sk-ant-...

# Stripe (for billing features)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (optional but recommended)
SMTP_HOST=smtp.your-provider.com
SMTP_USER=noreply@yourcompany.com
SMTP_PASSWORD=your_smtp_password
EMAIL_FROM=noreply@yourcompany.com
```

### 3. Start everything

```bash
make up          # Start all 33 containers with hot reload
# OR
make up-d        # Background mode
```

### 4. Open the app

```
http://localhost:3000    — Frontend
http://localhost:8000    — API Gateway / Swagger
http://localhost:3001    — Grafana dashboards  (admin/jarviis_admin)
http://localhost:9090    — Prometheus metrics
```

---

## Development

### Useful make commands

```bash
make logs s=auth-service     # Tail logs for one service
make logs-all                # Tail all services
make shell-db                # Open psql shell
make shell-redis             # Open redis-cli
make shell-auth              # Open bash in auth container
make test                    # Run all pytest suites
make migrate                 # Run Alembic migrations
make restart s=projects      # Restart one service
```

### Running tests

```bash
# All services
make test

# Single service
cd services/usage && pytest tests/ -v

# Frontend type-check
cd frontend && npm run type-check
```

### Creating a migration

```bash
make migrate-create msg="add usage_snapshots table"
make migrate
```

---

## Service Map

| Port | Service | Role |
|------|---------|------|
| 8000 | api-gateway | Entry point, auth validation, routing |
| 8001 | auth | JWT, OAuth (GitHub), orgs, RBAC, SSO provision |
| 8002 | projects | Projects, test runs, GitHub integration |
| 8003 | crawler | Playwright BFS spider — discovers pages |
| 8004 | ai-orchestrator | Claude test generation |
| 8005 | test-executor | Playwright execution, WebSocket streaming |
| 8006 | healing | AI selector repair engine |
| 8007 | visual | Visual regression (pixel diff) |
| 8008 | deploy | SSH deploy, rolling/blue-green/canary |
| 8009 | api-tester | OpenAPI/Postman test runner |
| 8010 | security | OWASP Top 10 scanner |
| 8012 | jarviis-ai | Conversational AI assistant |
| 8013 | cobol | COBOL/mainframe testing |
| 8014 | billing | Stripe subscriptions, webhooks |
| 8015 | sso | SAML 2.0 + OIDC enterprise SSO |
| 8016 | mobile | Android/iOS device testing |
| 8017 | events | Redis Streams event bus |
| 8018 | usage | Plan quota metering & enforcement |
| 8019 | notifications | Slack/Email/Teams/webhook alerts |
| 8020 | analytics | Pass rate trends, deploy metrics |
| 8021 | reports | PDF/CSV report generation |
| 8022 | feature-flags | Runtime feature flags + kill switches |
| 8023 | audit | Immutable cross-service audit trail |
| 8024 | search | Global search across all entities |
| 8025 | compliance | SOC2/GDPR evidence packs |
| 8026 | health | Customer health scoring |

---

## Plans & Limits

| Plan | Test Runs/mo | Projects | Members | Price |
|------|-------------|----------|---------|-------|
| Starter | 100 | 3 | 1 | Free |
| Pro | 2,000 | 20 | 5 | $49/mo |
| Team | 10,000 | 100 | 25 | $149/mo |
| Enterprise | Unlimited | Unlimited | Unlimited | Custom |

New orgs get a **2-day Pro trial** automatically on signup.

---

## Environment Variables Reference

See `.env.example` for the complete list with descriptions.

---

## Contributing

1. Branch from `develop`
2. Run `make test` — all tests must pass
3. Update `.env.example` if adding new env vars
4. Open a PR against `develop`

---

## License

Proprietary — © JarviisAI. All rights reserved.
webhook test
