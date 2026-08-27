# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MaestroBank — a **demo/prototype bank** (explicitly, not a real financial institution: no real Visa/Mastercard, SEPA, PSD2, or FX integration anywhere). Microservices backend (FastAPI + MongoDB) behind an API Gateway, Angular frontend. All Romanian-language UI/comments; code identifiers are English.

## Commands

### Start/stop the stack

```bash
docker compose up --build       # first run / after dependency changes
docker compose up -d --build    # detached
docker compose down             # stop (Mongo data persists in the `mongodb_data` volume unless `-v` is added)
```

**Before first run, copy `.env.example` to `.env`.** `MONGO_URL` for every service is built from `${MONGODB_URI_BASE}` in `docker-compose.yml` with **no fallback default** — if `.env` is missing, every service crash-loops on boot with `pymongo.errors.InvalidURI` (login/register/everything breaks with no obvious cause). `.env.example` documents two choices: a shared MongoDB Atlas cluster, or the local `mongodb` container already defined in compose (`MONGODB_URI_BASE=mongodb://mongodb:27017`) — the local option needs no credentials and is the reliable default for solo/offline dev.

After editing only one service's code, rebuild just that one: `docker compose up -d --build <service-name>`. After editing `frontend/package.json`, the running frontend container's `node_modules` (an anonymous volume, persists across rebuilds) needs a manual refresh — `docker exec maestrobank-frontend npm install && docker restart maestrobank-frontend` — a plain image rebuild alone won't update it.

### Backend tests (pytest, per service)

Each service with business logic has its own pytest suite, run against a **separate test database** inside the running container:

```bash
docker compose exec <service> pip install -r requirements-dev.txt -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/<db_name>_test <service> python -m pytest -q
```

Single test: append `::test_name` (or `::TestClass::test_name`) to the pytest invocation, e.g. `python -m pytest -q tests/test_auth.py::test_login_valid`.

Service → db_name: `auth-service`→`auth_db`, `accounts-service`→`accounts_db`, `transactions-service`→`tx_db`, `budgets-service`→`budgets_db`, `support-service`→`support_db`, `exchange-service`→`exchange_db`. Test deps aren't baked into the image (keeps it lean); reinstall after every container recreate.

### Frontend

```bash
cd frontend
npm install
ng serve              # dev server on :4200 (also runs inside the frontend container)
ng build               # production build; per-component CSS budget is enforced (see angular.json)
ng test                 # vitest — minimal coverage today, just the CLI-scaffolded app.spec.ts
```

No linter is configured on either side (no ESLint, no ruff/black) — only Prettier (`frontend/.prettierrc`) for formatting.

### Windows / git-bash note

`docker exec`/`docker run` with absolute container paths (e.g. `/app/tests`) get mangled by MSYS path conversion in Git Bash — prefix with `MSYS_NO_PATHCONV=1` when a bind-mount volume spec (`-v "C:\...:/work"`) or container path is involved.

## Architecture

```
Angular (4200) → Nginx (8080, reverse proxy) → API Gateway (8000: routing, JWT, CORS, rate limiting)
                                                        │
        ┌───────────┬──────────────┬─────────────┬─────────────┬──────────────┐
        ▼           ▼              ▼             ▼             ▼              ▼
  auth-service  accounts-service  transactions  budgets       support       exchange
    (8001)         (8002)        -service(8003) -service(8004) -service(8005) -service(8006)
     auth_db       accounts_db       tx_db       budgets_db    support_db    exchange_db
```

All services share **one MongoDB instance**, each with its **own database** — no service ever reads another's database directly. Cross-service data needs go through that service's HTTP API. `future-service-1`/`future-service-2` in compose are placeholder name reservations (e.g. a future `ai-orchestrator-service`), no code yet.

### Per-service internal structure (identical across all 6 FastAPI services)

```
app/
├── main.py      # FastAPI app + lifespan (health check; idempotent startup tasks — see below)
├── config.py    # env-var settings
├── database.py  # Motor/MongoDB client
├── models.py    # Mongo document shapes + Pydantic request/response DTOs
├── security.py  # JWT validation dependency (get_current_user_id)
├── routers/     # HTTP layer ONLY — validate input, delegate to service.py, return
└── service.py   # ALL business logic + the only place that touches the database directly
```

`routers/*.py` never touches the database directly. Routes under `routers/internal.py` (`/internal/*`) are service-to-service only — the Gateway hard-blocks any path starting with `internal/` at the proxy layer (`backend/gateway/app/routers/proxy.py::_forward`), so they're unreachable from the browser regardless of auth. This is how services call each other (e.g. accounts-service → auth-service `/internal/auth/verify-password` and `/internal/auth/verify-webauthn`; auth-service → accounts-service `/internal/accounts/provision` at registration).

**No migration tool exists** (Mongo, not SQL) — schema evolution and backfills are idempotent functions called from each service's `lifespan` in `main.py` (e.g. `accounts-service`'s `backfill_missing_account_types`, `auth-service`'s `webauthn_service.ensure_webauthn_indexes`), run on every boot. New fields on existing documents are handled by giving the Pydantic DTO a default, not by writing a migration.

### Gateway & JWT

- `backend/gateway/app/routers/proxy.py` — generic `/api/{service}/{path}` forwarder using internal Docker DNS names. `_is_protected(service, path)` decides which paths require a valid JWT *before* forwarding (defense in depth: each service also independently re-validates the same token on its protected routes — see each service's `security.py`).
- Public routes: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/webauthn/login/options`, `POST /api/auth/webauthn/login/verify`, `GET /health`, `GET /api/system/health`. Everything under `/api/accounts/*`, `/api/transactions/*`, `/api/budgets/*`, `/api/support/*`, `/api/exchange/*` is protected; under `/api/auth/*` only specific paths are (see `_is_protected`).
- `user_id` always comes from the JWT (`sub` claim) — never from a client-supplied field. A resource owned by another user 404s (not 403), to avoid confirming it exists.
- Rate limiting is in-memory per Gateway process (`RATE_LIMIT_MAX_REQUESTS`/`_WINDOW_SECONDS`) — fine for one instance, would need a distributed store (Redis) to scale horizontally; intentionally not built.

### Auth: password + WebAuthn/passkeys

`auth-service` owns both. Password: bcrypt hash, JWT issued via `security.py::create_access_token`. Passkeys (`app/webauthn_service.py`, `app/routers/webauthn.py`, `app/models_webauthn.py`): registration, discoverable login, and a reusable **step-up** mechanism (`begin_step_up`/`verify_step_up`) for re-confirming identity on a specific sensitive action — currently wired only to accounts-service's card-reveal endpoint, action-payload-bound so an assertion for one card can't reveal another. No Redis: challenges live in Mongo with an absolute `expires_at` + TTL index, but single-use is enforced by `find_one_and_delete` in code, not the TTL sweep (which only runs ~every 60s). `rp_id`/allowed origins must match where the browser actually navigates (`localhost:4200`, the Angular dev server) — **not** Nginx's `:8080`, which the browser never visits directly. Both password and passkey paths converge on the same `create_access_token`/`AuthService.setToken` — one session mechanism regardless of login method. Card reveal (`accounts-service`'s `CardRevealRequest`) accepts *either* a password *or* a WebAuthn assertion, validated via a `model_validator` requiring exactly one.

### Core banking flow

`POST /api/auth/register` → auth-service creates the user, then synchronously calls accounts-service internally to provision one RON current account (demo IBAN, `balance_minor=0`) + one demo virtual card. If accounts-service is unreachable at that moment, the user is still created but has no bank account yet (documented gap, no retry). accounts-service also supports opening additional typed accounts (`savings`/`deposit`/`student`, one each, via `POST /accounts/new`) alongside the auto-provisioned `current` one — most account-scoped operations (cards, dev-fund, transfer source) are explicitly pinned to the `current` account by filtering `account_type`, not just "the user's account".

Money is always `*_minor` integers (cents/bani) end-to-end, both backend and frontend — never float. `format_minor_amount`/`MoneyPipe` are the only formatting points.

## Frontend

Angular 22, **standalone components + signals** (no NgModules, no RxJS state stores) — `signal()`/`computed()` for local component state, RxJS `Observable`s only at the HTTP-service boundary (`frontend/src/app/services/*.service.ts`), converted with `firstValueFrom` where a service method needs to be `async` (e.g. `WebauthnService`, which wraps `@simplewebauthn/browser`'s Promise-based `navigator.credentials` calls).

- `core/api-config.ts` — single `API_BASE_URL` constant every service imports; never hardcode the API origin elsewhere. All requests go through Nginx (`:8080/api/...`), never directly to the Gateway or a microservice.
- `features/*` — one folder per route/page (`.ts` + `.html` + `.css`), each a standalone component.
- `shared/components/*` — reusable building blocks: `Modal`/`ConfirmDialog` for dialogs, `ActionButton` (variants + loading state), `Icon` (a single component with one inline-SVG `@switch` case per icon — never inline SVG elsewhere; add a new `@case` there), `ToastService` for feedback, `PageHeader`, `EmptyState`, `LoadingSkeleton`, `StatusBadge`, `ToggleControl`.
- `shared/error-utils.ts::extractErrorMessage(err, fallback)` — the one place that turns a FastAPI error response (`{detail: "..."}` or Pydantic's `{detail: [...]}`) into a user-facing string; reuse it in every `.subscribe({ error: ... })`.
- Design tokens (colors, spacing, radius, shadows, type scale) are centralized in `frontend/src/styles.css` as CSS custom properties (`--mb-*`) — components consume them, never redefine raw values. `angular.json`'s per-component CSS budget (`anyComponentStyle`) is set above the CLI default to accommodate richer feature panels (e.g. `cards.css`); don't shrink it without checking which components would break the build.
- JWT lives in `sessionStorage` (`AuthService`) — a documented development simplification, not a production security posture (no httpOnly cookies/refresh tokens).

## Known, documented limitations (not oversights)

- Mongo transactions: no replica set, so multi-document transfers use a conditional atomic debit + credit with manual rollback on partial failure — not real ledger guarantees.
- Rate limiting is single-process in-memory.
- Demo IBANs have pseudo-random (not MOD-97-computed) check digits; demo card PANs/CVVs are generated, not real, and never leave this system.
- `exchange-service` is a fully static/simulated FX dataset — no real market data, no real multi-currency balances moved.
- No AI layer yet (`ai-orchestrator-service`, RabbitMQ, Financial Guardian) — the Copilot page and "Coming soon" card-security toggles are intentionally inert placeholders for a later phase.
