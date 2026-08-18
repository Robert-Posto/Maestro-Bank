# MaestroBank

**⚠️ Prototip / demo.** MaestroBank NU este o bancă reală — este o aplicație demonstrativă, cu arhitectură de microservicii, în care toate operațiunile bancare (conturi, IBAN, carduri, transferuri) sunt **simulate**. Nu există nicio integrare cu bănci reale, Visa/Mastercard, SEPA, PSD2 sau plăți reale.

## Arhitectură

```text
Angular (4200)
     │  HTTP
     ▼
   Nginx (8080)  — reverse proxy
     │
     ▼
API Gateway (8000)  — routing, JWT, CORS, rate limiting
     │
     ├──────────────┬──────────────────┬────────────────┐
     ▼              ▼                  ▼                ▼
auth-service   accounts-service  transactions-service  budgets-service
  (8001)            (8002)             (8003)              (8004)
     │              │                  │                │
     ▼              ▼                  ▼                ▼
  auth_db       accounts_db          tx_db           budgets_db
                                                    (aceeași instanță MongoDB, 27017)

future-service-1 / future-service-2 — placeholder-e rezervate, fără rută prin Gateway încă.
```

Toate serviciile FastAPI rulează în containere separate, dar folosesc **aceeași instanță MongoDB**, fiecare cu propria bază de date. Niciun microserviciu nu citește direct baza altui microserviciu — comunicarea între ele se face doar prin API (ex. `transactions-service` nu citește `accounts_db`, cere datele prin API-ul intern al `accounts-service`).

### Responsabilitatea fiecărui serviciu

| Serviciu | Responsabilitate | Bază Mongo | Port (debug, direct) |
| --- | --- | --- | --- |
| **frontend** | UI Angular | — | 4200 |
| **nginx** | reverse proxy către Gateway | — | 8080 (expus) |
| **gateway** | routing `/api/*` → microservicii, JWT, CORS, rate limiting, status agregat | — (doar ping) | 8000 (expus) |
| **auth-service** | users, autentificare, JWT, hash parole (bcrypt), provizionare automată cont bancar | `auth_db` | 8001 |
| **accounts-service** | conturi RON, IBAN demo, carduri virtuale demo, solduri | `accounts_db` | 8002 |
| **transactions-service** | transferuri, istoric tranzacții | `tx_db` | 8003 |
| **budgets-service** | bugete, abonamente, limite de cheltuieli (viitor) | `budgets_db` | 8004 |
| **future-service-1/2** | rezervate pentru funcționalități viitoare nedecise | `future1_db` / `future2_db` (nefolosite încă) | — (intern) |
| **mongodb** | baza de date, comună tuturor serviciilor de mai sus | — | 27018 (host) → 27017 (container) |

Angular **nu** vorbește niciodată direct cu un microserviciu — trece mereu prin Nginx → Gateway.

## Fluxul Core Banking

```text
Register  →  Login  →  JWT
    │
    ▼ (automat, sincron, la register)
Creare cont RON  →  IBAN demo  →  Card virtual demo
    │
    ▼
Alimentare demo (dev-only)  →  Sold
    │
    ▼
Transfer către alt IBAN  →  Actualizare solduri (debit + credit)  →  Istoric tranzacții
```

La `POST /api/auth/register`, `auth-service` creează userul și apoi cere automat lui `accounts-service` (intern, sincron) să provizioneze un cont curent RON (`balance_minor=0`) cu un IBAN demo unic și un card virtual demo. Dacă `accounts-service` nu răspunde, userul tot rămâne creat (nu depinde de banking pentru autentificare), dar nu va avea cont bancar — vezi limitarea documentată mai jos.

## JWT

* `auth-service` emite JWT-ul la login (`POST /api/auth/login`), semnat cu `JWT_SECRET`/`JWT_ALGORITHM` (variabile de mediu, identice pe toate serviciile care validează token-uri).
* **Rute publice**: `POST /api/auth/register`, `POST /api/auth/login`, `GET /health`, `GET /api/system/health`.
* **Rute protejate JWT** (validate la nivel de Gateway, ÎNAINTE de orice forwarding — vezi `backend/gateway/app/routers/proxy.py::_is_protected`): `GET /api/auth/me`, `GET /api/accounts/me`, `GET /api/accounts/me/cards`, `GET /api/accounts/{id}`, `POST /api/accounts/dev/fund`, `POST /api/transactions/transfers`, `GET /api/transactions`, `GET /api/transactions/{id}`.
* Fiecare microserviciu care are rute protejate (`accounts-service`, `transactions-service`) își validează ȘI el, independent, tokenul (defense in depth) — nu se bazează exclusiv pe Gateway.
* `user_id`-ul vine STRICT din JWT — frontendul nu poate trimite un `user_id`/`from_account_id` arbitrar.

## Rate limiting

Gateway aplică un rate limit simplu, **în memorie**, per IP (implicit 300 cereri / 60s, configurabil prin `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`).

⚠️ Limitare cunoscută: fiind în memoria unui singur proces, această soluție e potrivită doar pentru development / o singură instanță de Gateway. Pentru producție, cu mai multe instanțe scalate orizontal, ar fi nevoie de o soluție distribuită (ex. Redis) — intenționat neintrodusă acum.

## Cum pornesc proiectul

```bash
docker compose up --build
```

## Cum îl opresc

```bash
docker compose down
```

Datele din MongoDB **persistă** (volum `mongodb_data`) atât timp cât nu rulezi `docker compose down -v`.

## URL-uri

- Frontend (Angular): http://localhost:4200
- API prin Nginx (recomandat, ca-n producție): http://localhost:8080/api/...
- API Gateway direct (debugging): http://localhost:8000 — Swagger: http://localhost:8000/docs
- Status agregat arhitectură: http://localhost:8080/api/system/health

### Swagger per microserviciu (debugging, development)

- auth-service: http://localhost:8001/docs
- accounts-service: http://localhost:8002/docs
- transactions-service: http://localhost:8003/docs
- budgets-service: http://localhost:8004/docs

## Teste automate

Fiecare serviciu cu logică de business (`auth-service`, `accounts-service`, `transactions-service`) are teste pytest, rulate cu o bază MongoDB de TEST separată (nu ating datele demo):

```bash
docker compose exec auth-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/auth_db_test auth-service python -m pytest -q

docker compose exec accounts-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/accounts_db_test accounts-service python -m pytest -q

docker compose exec transactions-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/tx_db_test transactions-service python -m pytest -q
```

## Configurare

Copiază `.env.example` în `.env` și ajustează dacă e nevoie (`.env` e în `.gitignore`, nu conține secrete reale implicit).

## Limitări cunoscute (documentate explicit, nu ascunse)

- **Atomicitate transfer**: MongoDB standalone (fără replica set) nu suportă tranzacții multi-document. Debit + credit se aplică prin 2 operații condiționate, atomice la nivel de document, cu rollback manual dacă a doua eșuează — nu oferă garanțiile unui ledger bancar real.
- **Provizionare cont la register**: sincronă, fără retry automat dacă `accounts-service` e indisponibil exact în acel moment — userul rămâne creat, dar fără cont bancar.
- **Rate limiting**: în memorie, per instanță de Gateway — nu se scalează orizontal fără o soluție distribuită.
- **JWT în frontend**: ținut în `sessionStorage`, alegere de DEVELOPMENT, nu arhitectură de securitate pentru producție.
- **IBAN demo**: cifrele de control sunt pseudo-aleatoare, NU calculate conform standardului real (MOD-97) — suficient pentru UI, nu valid ca IBAN real.

## Ce NU implementăm încă

Agenți AI, integrare OpenAI, plăți reale, Visa/Mastercard, SEPA, Open Banking/PSD2, IBAN-uri bancare reale, business logic complex de bugete/abonamente, designul final al aplicației Angular.
