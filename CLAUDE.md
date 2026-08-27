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

Service → db_name: `auth-service`→`auth_db`, `accounts-service`→`accounts_db`, `transactions-service`→`tx_db`, `budgets-service`→`budgets_db`, `support-service`→`support_db`, `exchange-service`→`exchange_db`, `ai-orchestrator-service`→`ai_orchestrator_db`. Test deps aren't baked into the image (keeps it lean); reinstall after every container recreate.

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
    ┌────────┬──────────┬────────────┬─────────┬─────────┬─────────┬────────────┬──────────────┬──────────┬──────────────┐
    ▼        ▼          ▼            ▼         ▼         ▼         ▼            ▼              ▼          ▼
  auth   accounts  transactions  budgets   support  exchange  verification  ai-orchestrator  deposits  investments
 (8001)   (8002)    -service      -service  -service  -service   -service       -service       -service   -service
          -service   (8003)       (8004)    (8005)    (8006)      (8007)         (8008)         (8009)     (8010)
 auth_db  accounts_db  tx_db   budgets_db support_db exchange_db (stateless) ai_orchestrator_db deposits_db investments_db
```

All services share **one MongoDB instance**, each with its **own database** — no service ever reads another's database directly. Cross-service data needs go through that service's HTTP API. `verification-service` is fully stateless (no `MONGO_URL`, no `database.py`), comparing two images (ID photo + selfie) and discarding them immediately after. `ai-orchestrator-service` now has a `database.py` for storing conversation history (see "MaestroAgent + Support Agent" below), but financial/account data still comes exclusively through the Gateway, exactly like an external client (Angular), with the current user's JWT propagated. `deposits-service` (term deposits) and `investments-service` (a demo brokerage catalog) are the two newest services — teammate-built, not yet covered in depth below; treat their own code/tests as the source of truth until this file catches up.

### Per-service internal structure (identical across the stateful FastAPI services)

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

`verification-service` follows the same `routers/`+`service.py` split but skips `database.py` (nothing to connect to). `ai-orchestrator-service` now includes `database.py` for conversation history persistence.

`routers/*.py` never touches the database directly. Routes under `routers/internal.py` (`/internal/*`) are service-to-service only — the Gateway hard-blocks any path starting with `internal/` at the proxy layer (`backend/gateway/app/routers/proxy.py::_forward`), so they're unreachable from the browser regardless of auth. This is how services call each other (e.g. accounts-service → auth-service `/internal/auth/verify-password` and `/internal/auth/verify-webauthn`; auth-service → accounts-service `/internal/accounts/provision` at registration).

**No migration tool exists** (Mongo, not SQL) — schema evolution and backfills are idempotent functions called from each service's `lifespan` in `main.py` (e.g. `accounts-service`'s `backfill_missing_account_types`, `auth-service`'s `webauthn_service.ensure_webauthn_indexes`), run on every boot. New fields on existing documents are handled by giving the Pydantic DTO a default, not by writing a migration.

### Gateway & JWT

- `backend/gateway/app/routers/proxy.py` — generic `/api/{service}/{path}` forwarder using internal Docker DNS names. `_is_protected(service, path)` decides which paths require a valid JWT *before* forwarding (defense in depth: each service also independently re-validates the same token on its protected routes — see each service's `security.py`).
- Public routes: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/webauthn/login/options`, `POST /api/auth/webauthn/login/verify`, `GET /health`, `GET /api/system/health`. Everything under `/api/accounts/*`, `/api/transactions/*`, `/api/budgets/*`, `/api/support/*`, `/api/exchange/*`, `/api/verification/*`, `/api/ai/*` is protected; under `/api/auth/*` only specific paths are (see `_is_protected`) — `me`, `change-password`, `verify-email`, `resend-verification-email`, and the WebAuthn register/credentials/step-up paths (login options/verify stay public — the whole point is authenticating an unknown user).
- `user_id` always comes from the JWT (`sub` claim) — never from a client-supplied field. A resource owned by another user 404s (not 403), to avoid confirming it exists.
- `role` claim (`"customer"` | `"staff"`) gates `/admin/*` vs `/app/*` at both the frontend guard level and independently in each backend service — see "Staff/admin console" below.
- `SERVICES` dict in `proxy.py` can override `_DEFAULT_TIMEOUT_SECONDS` (10s) per service — `verification` gets 30s (DeepFace on CPU can exceed the default) and `ai` gets 100s (tool-calling rounds against Azure OpenAI).
- Rate limiting is in-memory per Gateway process (`RATE_LIMIT_MAX_REQUESTS`/`_WINDOW_SECONDS`) — fine for one instance, would need a distributed store (Redis) to scale horizontally; intentionally not built.

### Auth: password + WebAuthn/passkeys

`auth-service` owns both. Password: bcrypt hash, JWT issued via `security.py::create_access_token`. Passkeys (`app/webauthn_service.py`, `app/routers/webauthn.py`, `app/models_webauthn.py`): registration, discoverable login, and a reusable **step-up** mechanism (`begin_step_up`/`verify_step_up`) for re-confirming identity on a specific sensitive action — currently wired only to accounts-service's card-reveal endpoint, action-payload-bound so an assertion for one card can't reveal another. No Redis: challenges live in Mongo with an absolute `expires_at` + TTL index, but single-use is enforced by `find_one_and_delete` in code, not the TTL sweep (which only runs ~every 60s). `rp_id`/allowed origins must match where the browser actually navigates (`localhost:4200`, the Angular dev server) — **not** Nginx's `:8080`, which the browser never visits directly. Both password and passkey paths converge on the same `create_access_token`/`AuthService.setToken` — one session mechanism regardless of login method. Card reveal (`accounts-service`'s `CardRevealRequest`) accepts *either* a password *or* a WebAuthn assertion, validated via a `model_validator` requiring exactly one.

### Core banking flow

`POST /api/auth/register` → auth-service creates the user, then synchronously calls accounts-service internally to provision one RON current account (demo IBAN, `balance_minor=0`) + one demo virtual card. If accounts-service is unreachable at that moment, the user is still created but has no bank account yet (documented gap, no retry). accounts-service also supports opening additional typed accounts (`savings`/`deposit`/`student`, one each, via `POST /accounts/new`) alongside the auto-provisioned `current` one — most account-scoped operations (cards, dev-fund, transfer source) are explicitly pinned to the `current` account by filtering `account_type`, not just "the user's account".

`eur`/`usd`/`gbp` are also creatable account types (same `POST /accounts/new`), each with its own real currency (not RON) — these exist specifically so currency exchange has somewhere to credit/debit real balances (see "Exchange" below); a user must open the target-currency account before exchanging into it.

Money is always `*_minor` integers (cents/bani) end-to-end, both backend and frontend — never float. `format_minor_amount`/`MoneyPipe` are the only formatting points.

### Exchange (real rate, real execution)

`exchange-service` fetches the official daily rate from BNR's public XML feed (`app/bnr_rates.py`), refreshed on a fixed interval (`RATES_REFRESH_INTERVAL_SECONDS`, default 6h) with a static fallback if BNR is unreachable. Spread/commission on top of the mid-rate are simulated MaestroBank policy (no real bank publishes its own spread either way). Execution (`POST /exchange/execute`) is real — it calls `accounts-service`'s `/internal/accounts/exchange` to debit the source currency account and credit the destination one, same conditional-atomic-debit-plus-credit pattern as a normal transfer (see below), just with two different amounts (applied rate) instead of one.

### MaestroAgent + Support Agent (AI, `ai-orchestrator-service`)

Two agents over Azure OpenAI (GPT-5-mini), both stateless in their own reasoning (`app/agents/*.py`, `app/services/support_service.py` untouched by persistence) but now with real conversation history: `app/database.py`/`app/services/conversation_service.py` give the service its own `ai_orchestrator_db`, one `conversations` collection shared by both agents (`agent` field distinguishes them), messages embedded per document. `POST /spending-forecast/chat` and `POST /support` take a `conversation_id` (server loads/saves history from Mongo) instead of client-sent history; `GET/DELETE .../conversations[/{id}]` list/fetch/delete past conversations, all scoped to the JWT's `user_id` (never trusted from the client), 404 (not 403) on someone else's conversation. MaestroAgent does RAG + deterministic forecast/affordability + propose-not-execute for budgets; Support Agent answers account/card/transaction/ticket questions + propose-not-execute for a new support ticket. Both frontend pages surface a "Conversații" dropdown (list/switch/delete/new) in the chat header, next to the agent's identity — not a permanent side panel.

### Financial Guardian (LLM explanations for fraud holds)

Lives in `transactions-service/app/guardian/` — when the deterministic fraud engine (18 fixed rules, see `app/fraud/catalogue.py`) holds a transfer for review, Guardian generates an async, separate LLM call (Azure OpenAI) explaining *why* in plain language for staff, plus a discreet phrase for the customer. It never decides whether to hold a transfer — that's 100% deterministic already; Guardian only explains a decision already made. Falls back to a static template if Azure OpenAI isn't configured or the call fails.

### Content screening (transfer descriptions)

`transactions-service/app/content_screening.py` — a deliberately deterministic, keyword-based screen (not an LLM) for terrorism/violence/illegal-activity terms in a transfer's description, several hundred roots in RO+EN across ~14 categories, leetspeak-resilient normalization. Warns only for a normal transfer (never blocks) — a payment REQUEST is stricter and blocks creation outright, since a request link is more like a public announcement than a private, already-consumed transaction. Kept separate from both the fraud engine (not a 19th rule) and Guardian (no LLM judgment call here, same philosophy as the profanity filter in `ai-orchestrator-service`'s Support Agent).

### Account statement (PDF)

`GET /transactions/statement?date_from=...&date_to=...` (both required) — `transactions-service`'s `app/statement.py` renders a formal PDF statement (reportlab) for the user's `current` account only (same MVP scope as the rest of this file's reports — see the `_build_filter_query` note on multi-account). Opening/closing balance for the period is *reconstructed*, not read from a stored ledger: it walks every `completed` transaction on the account backwards from the account's live `balance_minor` (see `app/statement.py::reconstruct_statement_balances`, split out as a pure function specifically so the balance math is unit-testable without a DB). Requires `fonts-dejavu-core` in the image (see Dockerfile) — reportlab's base Helvetica font has no glyphs for Romanian diacritics (ă/â/î/ș/ț).

### Subscription detection (passive, from transaction history)

`budgets-service`'s `detect_recurring_payments()` calls an internal endpoint (`transactions-service`'s `GET /internal/transactions/by-user/{user_id}`) to fetch a user's raw history, groups outgoing completed transactions by description, and flags groups with 2+ occurrences, near-identical amount (±10%), and a real monthly cadence (every consecutive gap between 20-40 days) as suggestions (`GET /budgets/subscriptions/suggestions`) — never auto-created, the user confirms explicitly. Deterministic heuristic, not ML, same philosophy as content screening.

### Staff/admin console (`/admin`, separate from `/app/*`)

A `role="staff"` account (created only via `scripts/create_staff_user.py`, never through public registration) never reaches `/app/*` — both `authGuard`/`guestGuard` (frontend) and each backend service's own `require_staff` dependency redirect/reject it. Staff get a visually distinct shell (`AdminShell`, navy+amber, deliberately different from the customer app) at `/admin`, where they review fraud holds (approve/reject, see the Guardian explanation, hover a fired rule code for a plain-language tooltip) and can open a read-only view of a specific customer's accounts/transactions (click a transaction for full details), reached from a hold.

## Frontend

Angular 22, **standalone components + signals** (no NgModules, no RxJS state stores) — `signal()`/`computed()` for local component state, RxJS `Observable`s only at the HTTP-service boundary (`frontend/src/app/services/*.service.ts`), converted with `firstValueFrom` where a service method needs to be `async` (e.g. `WebauthnService`, which wraps `@simplewebauthn/browser`'s Promise-based `navigator.credentials` calls).

- `core/api-config.ts` — single `API_BASE_URL` constant every service imports; never hardcode the API origin elsewhere. All requests go through Nginx (`:8080/api/...`), never directly to the Gateway or a microservice.
- `features/*` — one folder per route/page (`.ts` + `.html` + `.css`), each a standalone component.
- `shared/components/*` — reusable building blocks: `Modal`/`ConfirmDialog` for dialogs, `ActionButton` (variants + loading state), `Icon` (a single component with one inline-SVG `@switch` case per icon — never inline SVG elsewhere; add a new `@case` there), `Select` (custom dropdown — use instead of native `<select>` for anything with a color-coded option like a category/currency; native selects render their option popup with browser/OS chrome, not app CSS, so they break in dark mode), `ToastService` for feedback, `PageHeader`, `EmptyState`, `LoadingSkeleton`, `StatusBadge`, `ToggleControl`.
- `shared/error-utils.ts::extractErrorMessage(err, fallback)` — the one place that turns a FastAPI error response (`{detail: "..."}` or Pydantic's `{detail: [...]}`) into a user-facing string; reuse it in every `.subscribe({ error: ... })`.
- Design tokens (colors, spacing, radius, shadows, type scale) are centralized in `frontend/src/styles.css` as CSS custom properties (`--mb-*`) — components consume them, never redefine raw values (including in dark mode: redefine tokens under `:root[data-theme='dark']`, never hardcode a color that bypasses the theme — this codebase has had several real bugs from exactly that, e.g. brand-navy colors used as *text* instead of background, which vanish once the surrounding surface also goes dark). `angular.json`'s per-component CSS budget (`anyComponentStyle`) is set above the CLI default to accommodate richer feature panels (e.g. `cards.css`); don't shrink it without checking which components would break the build.
- Dark mode is a real, user-toggleable theme (`ThemeService`, switch in the topbar), not just a media-query — persisted, and gated behind `[data-theme="dark"]` on `<html>`.
- `AppShell` (customer, `/app/*`) and `AdminShell` (staff, `/admin`) are separate top-level shells with separate idle-timeout instances (`IdleService`, 5 min) — a staff session never shares chrome or navigation with a customer session.
- JWT lives in `sessionStorage` (`AuthService`) — a documented development simplification, not a production security posture (no httpOnly cookies/refresh tokens).

## Known, documented limitations (not oversights)

- Mongo transactions: no replica set, so multi-document transfers (and exchange execution) use a conditional atomic debit + credit with manual rollback on partial failure — not real ledger guarantees.
- Rate limiting is single-process in-memory.
- Demo IBANs have pseudo-random (not MOD-97-computed) check digits; demo card PANs/CVVs are generated, not real, and never leave this system.
- No RabbitMQ — scheduled transfers and fraud-hold expiry run through in-process `asyncio` loops (`transactions-service/app/scheduler.py`), started/stopped in `main.py`'s lifespan. Deliberate simplification for a single-worker demo, documented in the code itself, not a gap waiting to be filled.
- Card security toggles (freeze, online/contactless/ATM/international payments, daily limit) persist real values and the UI reflects them correctly, but **nothing enforces them** — there's no "pay with card at a merchant" flow in this app (money only moves via IBAN-to-IBAN transfer), so there's no point in the code where these settings could even be checked. Change PIN, Transaction alerts and Payment confirmation (Cards → Security settings) are fully implemented and server-enforced (see `accounts-service`'s `change_card_pin`/`get_account_card_settings` and `transactions-service`'s `create_transfer` PIN-confirmation step, gated by `payment_confirmation_required`) — no longer placeholders.
- Content screening (`content_screening.py`) and subscription detection (`budgets-service::detect_recurring_payments`) are both intentionally deterministic/heuristic, not ML — see their own sections above for why.
- Conversation history (`ai_orchestrator_db`) has no retention policy or size cap on a single conversation — fine for a demo, would need one before this went anywhere real.
