# JarviisAI Changelog

All notable changes to JarviisAI are documented here.
Format: [Semantic Versioning](https://semver.org/)

---

## [1.2.0] — 2026-04-28

### Added
- **2-day Pro trial** — all new organizations get a full Pro-tier trial automatically on signup
- **10 SaaS platform services** — events bus, usage metering, notifications, analytics, reports, feature flags, audit log, global search, compliance (SOC2/GDPR), customer health scoring
- **Analytics dashboard** — real pass rate trends, deployment frequency, healing ROI
- **Reports** — 10 report types including Executive Summary and SOC2 Evidence Pack as CSV/JSON/HTML
- **Team management** — invite members, assign roles, remove members from settings
- **Notifications** — Slack, Teams, email, and custom webhooks for test failures, deployments, and billing events
- **Audit log** — immutable cross-service event trail with 90-day retention and JSON export
- **Global search** — search across projects, runs, and deployments
- **Usage page** — real-time plan consumption with upgrade CTAs
- **Outbound webhook management** — register, list, and delete webhook endpoints
- **Admin panel** — user management, org health scores, billing overview

### Fixed
- GitHub OAuth new-user flow now correctly reads `?step=2` URL parameter
- API gateway now handles streaming responses (CSV, ZIP, HTML) without breaking them
- All internal services now have unique Redis database indices (no collisions)
- `trial_notified` column added to database schema with Alembic migration

### Security
- CORS restricted from wildcard `*` to internal origins on all 22 internal services
- Feature flag admin endpoints protected by `X-Internal-Secret` header
- Usage enforcement changed to fail-closed (503) instead of fail-open
- Admin panel now requires `owner` role or `is_superadmin` at layout level

---

## [1.1.0] — 2026-04-15

### Added
- **SSO** — SAML 2.0 and OIDC enterprise single sign-on
- **COBOL testing** — mainframe test generation and execution
- **Mobile testing** — Android (AWS Device Farm) and iOS (BrowserStack) support
- **Security scanner** — OWASP Top 10 automated scanning
- **Visual regression** — pixel-diff comparison across releases
- **Billing** — Stripe integration with 4-tier plan structure
- **Self-healing engine** — AI-powered CSS selector repair

### Fixed
- Prometheus metrics on all 16 services
- Nginx WebSocket proxy for live test streaming

---

## [1.0.0] — 2026-03-01

### Added
- Initial release
- Web app testing with Playwright
- AI test generation using Claude claude-sonnet-4-20250514
- Deploy engine (SSH, rolling, blue-green, canary)
- API testing with OpenAPI/Postman spec import
- GitHub integration with commit status checks
- Multi-organization support with RBAC
