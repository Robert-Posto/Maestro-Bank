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
     ├────────┬──────────┬──────────┬─────────┬──────────┬──────────────┬──────────────┐
     ▼        ▼          ▼          ▼         ▼          ▼              ▼              ▼
  auth      accounts  transactions budgets  support   exchange     verification    ai-orchestrator
 (8001)      (8002)      (8003)    (8004)    (8005)     (8006)         (8007)          (8008)
     │        │          │          │         │          │               │              │
     ▼        ▼          ▼          ▼         ▼          ▼          (fără bază proprie)  (fără bază proprie)
  auth_db  accounts_db  tx_db   budgets_db support_db exchange_db   compară imagini,   vorbește DOAR prin
                                                                     nu le persistă     Gateway (ca un
                              (aceeași instanță MongoDB, 27017)                          client extern)
```

Toate serviciile FastAPI rulează în containere separate, dar folosesc **aceeași instanță MongoDB**, fiecare cu propria bază de date. Niciun microserviciu nu citește direct baza altui microserviciu — comunicarea între ele se face doar prin API (ex. `transactions-service` nu citește `accounts_db`, cere datele prin API-ul intern al `accounts-service`; la fel, pentru forecast, `transactions-service` cere abonamentele active prin API-ul intern al `budgets-service`, nu citește `budgets_db` direct).

`verification-service` și `ai-orchestrator-service` sunt STATELESS — n-au bază proprie. Primul compară două imagini (buletin + selfie) și le șterge imediat după; al doilea nu atinge MongoDB deloc, ci apelează celelalte servicii prin Gateway, exact ca un client extern (Angular), propagând JWT-ul userului curent.

### Responsabilitatea fiecărui serviciu

| Serviciu | Responsabilitate | Bază Mongo | Port (debug, direct) |
| --- | --- | --- | --- |
| **frontend** | UI Angular (design MaestroBank — vezi `UI reference/`) | — | 4200 |
| **nginx** | reverse proxy către Gateway | — | 8080 (expus) |
| **gateway** | routing `/api/*` → microservicii, JWT, CORS, rate limiting, status agregat | — (doar ping) | 8000 (expus) |
| **auth-service** | users, autentificare, JWT, hash parole (bcrypt), schimbare parolă, passkeys (WebAuthn), verificare email la onboarding, provizionare automată cont bancar | `auth_db` | 8001 |
| **accounts-service** | conturi (curent + economii/depozit/student + eur/usd/gbp, pentru schimbul valutar real), IBAN demo, carduri virtuale demo + control card (freeze/settings/limite — vezi limitările de mai jos), beneficiari, pockets (obiective de economisire) | `accounts_db` | 8002 |
| **transactions-service** | transferuri (inclusiv programate/recurente), screening determinist al descrierii (termeni asociați cu activități ilegale/violente), Financial Guardian (explicații LLM ale deciziilor motorului de fraudă), istoric tranzacții (filtre, export CSV, recognize/report), analytics (spending/cash-flow/forecast) | `tx_db` | 8003 |
| **budgets-service** | bugete pe categorie + abonamente/plăți recurente (CRUD manual + detecție pasivă din istoricul de tranzacții) | `budgets_db` | 8004 |
| **support-service** | tichete de suport + notificări persistente per user | `support_db` | 8005 |
| **exchange-service** | schimb valutar — curs REAL (feed oficial BNR), execuție REALĂ (mută solduri între contul RON și conturile pe valută eur/usd/gbp); spread-ul și comisionul rămân politică simulată MaestroBank | `exchange_db` | 8006 |
| **verification-service** | verificare identitate la onboarding — compară poza buletinului cu un selfie live (DeepFace, model `ArcFace`), apoi marchează userul verificat printr-un apel intern la `auth-service` | — (stateless) | 8007 |
| **ai-orchestrator-service** | găzduiește 2 agenți: "MaestroAgent" (Spending + Forecast) și "Support Agent" (întrebări despre cont/card/tranzacții/tichete) — ambii peste Azure OpenAI (GPT-5-mini), cu tool-calling către celelalte servicii prin Gateway și un strat RAG (fallback local TF-IDF dacă nu sunt embeddings configurate) | — (stateless) | 8008 |
| **mongodb** | baza de date, comună serviciilor cu stare | — | 27018 (host) → 27017 (container) |

Angular **nu** vorbește niciodată direct cu un microserviciu — trece mereu prin Nginx → Gateway.

### Structura internă a unui serviciu

Toate serviciile respectă aceeași separare:

```text
app/
├── main.py      # app factory FastAPI, health check, includerea router-elor
├── config.py    # settings din variabile de mediu (pydantic-settings)
├── database.py  # conexiunea Motor la MongoDB (LIPSEȘTE la verification-service/ai-orchestrator-service — stateless)
├── models.py    # documente Mongo + DTO-uri Pydantic (request/response)
├── security.py  # dependency de validare JWT (get_current_user_id)
├── routers/     # DOAR HTTP: validare input, apel service.py, returnare
└── service.py   # TOATĂ logica de business + acces la bază de date
```

Regula: `routers/*.py` nu atinge niciodată direct baza de date — doar validează și deleagă către `service.py`. Rutele `/internal/*` (provisioning, transfer, subscriptions-by-user, mark-identity-verified) sunt DOAR pentru comunicare service-to-service — Gateway le blochează explicit, nu sunt accesibile din browser.

## Fluxul Core Banking

```text
Register  →  Login automat  →  JWT
    │
    ▼ (automat, sincron, la register)
Creare cont RON  →  IBAN demo  →  Card virtual demo
    │
    ▼
Onboarding: verificare email (cod) → verificare identitate (buletin + selfie) → bonus de bun venit
    │
    ▼
Transfer către alt IBAN  →  Actualizare solduri (debit + credit)  →  Istoric tranzacții
```

La `POST /api/auth/register`, `auth-service` creează userul, cere automat lui `accounts-service` (intern, sincron) să provizioneze un cont curent RON (`balance_minor=0`) cu un IBAN demo unic și un card virtual demo, apoi generează și trimite (sau doar logează, vezi mai jos) un cod de verificare email. Dacă `accounts-service` nu răspunde, userul tot rămâne creat (nu depinde de banking pentru autentificare), dar nu va avea cont bancar — vezi limitarea documentată mai jos. Userii creați ÎNAINTE de acest feature sunt marcați automat ca deja verificați la boot (`auth-service::backfill_verification_flags`) — nu sunt puși retroactiv să treacă prin verificare cu buletin.

## Onboarding: verificare email + identitate

După register, userul trece prin 3 ecrane (`/onboarding/verify-email` → `/onboarding/verify-identity` → `/onboarding/welcome`) înainte să ajungă în `/app/*` — impus printr-un route guard (`frontend/src/app/core/auth.guard.ts`), nu doar o convenție de UI.

- **Verificare email**: cod de 6 cifre, generat de `auth-service`, trimis prin SMTP (stdlib `smtplib`, fără dependință nouă). Dacă `SMTP_HOST` nu e configurat (implicit), codul apare doar în `docker logs maestrobank-auth-service` — suficient pentru testare locală fără cont de email real. Vezi `.env.example`, secțiunea SMTP, pentru cum pui credențiale reale (recomandat: Mailtrap "Email Testing" — inbox partajat de toată echipa, nu trimite pe adrese reale).
- **Verificare identitate**: userul încarcă o poză (buletin sau orice poză clară cu fața lui) + un selfie live (cameră din browser). `verification-service` compară cele două fețe cu **DeepFace** (model `VGG-Face`, detector `retinaface`) — imaginile sunt scrise temporar pe disc doar cât durează comparația, apoi șterse necondiționat; NU sunt persistate niciunde. Rezultatul (`identity_verified: true/false`) e singurul lucru care ajunge să fie salvat, ca flag pe userul din `auth_db`.
- **Bonus de bun venit**: la finalul flow-ului, contul primește automat 500 lei demo (reutilizează endpoint-ul existent `dev/fund`), ca userul să aibă ceva de explorat din prima secundă.

Modelele DeepFace (~600MB total) se descarcă o singură dată, la pornirea containerului `verification-service` (`lifespan` din `main.py`, nu la prima cerere reală) — persistate într-un volum Docker dedicat (`verification_models`), ca să nu se redescarce la fiecare recreare a containerului.

## MaestroAgent + Support Agent (AI, `ai-orchestrator-service`)

Serviciul găzduiește 2 agenți separați, ambii peste Azure OpenAI (deployment GPT-5-mini), cu tool-calling propriu — niciunul nu primește vreodată un `user_id` arbitrar, doar JWT-ul userului curent, propagat prin Gateway:

- **MaestroAgent** (`/app/copilot`) — analiza cheltuielilor și forecast de sold. Tool-calling către `accounts`/`transactions`/`budgets`, plus un strat RAG minimal peste `app/rag/knowledge/*.md` (fallback local TF-IDF dacă nu sunt configurate embeddings Azure).
- **Support Agent** (`/app/support`) — răspunde despre cont/card/tranzacții/tichete, cu tool-calling propriu (`app/tools/support_*.py`) și un filtru determinist de moderare a mesajelor userului (`app/services/moderation_service.py`) — aceeași filozofie ca screening-ul de descrieri din `transactions-service`: listă de cuvinte-cheie, nu LLM, pentru rezultat instant și verificabil.

Fără credențiale Azure OpenAI setate, serviciul tot pornește (health check trece), dar orice cerere de chat întoarce `503`.

## Financial Guardian (explicații AI pentru rețineri de fraudă)

Trăiește în `transactions-service/app/guardian/` — când motorul de fraudă (determinist, 18 reguli) reține un transfer pentru revizuire, Guardian generează ASINCRON, printr-un apel separat la Azure OpenAI, o explicație în limbaj natural pentru personal ("de ce a fost reținut acest transfer") și o frază discretă pentru client. E strict un strat de EXPLICAȚIE peste o decizie deja luată determinist — Guardian nu decide NICIODATĂ dacă un transfer se reține sau nu, doar explică o decizie existentă. Fără credențiale Azure OpenAI, motorul de fraudă funcționează identic (scor + reținere), doar explicația LLM lipsește (fallback pe un șablon static).

## Consolă separată pentru personal (`/admin`)

Un cont cu `role="staff"` (creat DOAR prin `scripts/create_staff_user.py`, niciodată prin înregistrare publică) nu ajunge NICIODATĂ pe `/app/*` — e redirecționat direct către `/admin`, o consolă complet separată (`AdminShell`), fără acces la vreun cont bancar personal. Acolo, personalul revizuiește rețineri de fraudă (aprobă/respinge, vede explicația Guardian) și poate deschide o vedere READ-ONLY a conturilor/tranzacțiilor unui client anume, pornind de la o reținere.

## JWT

* `auth-service` emite JWT-ul la login (`POST /api/auth/login`), semnat cu `JWT_SECRET`/`JWT_ALGORITHM` (variabile de mediu, identice pe toate serviciile care validează token-uri).
* **Rute publice**: `POST /api/auth/register`, `POST /api/auth/login`, `GET /health`, `GET /api/system/health`, `POST /api/auth/webauthn/login/options`, `POST /api/auth/webauthn/login/verify`.
* **Rute protejate JWT** (validate la nivel de Gateway, ÎNAINTE de orice forwarding — vezi `backend/gateway/app/routers/proxy.py::_is_protected`): `GET/POST /api/auth/me`, `/api/auth/change-password`, `/api/auth/verify-email`, `/api/auth/resend-verification-email`, passkey register/credentials/step-up, TOT sub `/api/accounts/*`, `/api/transactions/*`, `/api/budgets/*`, `/api/support/*`, `/api/exchange/*`, `/api/verification/*`, `/api/ai/*`.
* Fiecare microserviciu cu rute protejate își validează ȘI el, independent, tokenul (defense in depth) — nu se bazează exclusiv pe Gateway.
* `user_id`-ul vine STRICT din JWT — frontendul nu poate trimite un `user_id`/`from_account_id` arbitrar.

## Rate limiting

Gateway aplică un rate limit simplu, **în memorie**, per IP (implicit 300 cereri / 60s, configurabil prin `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`).

⚠️ Limitare cunoscută: fiind în memoria unui singur proces, această soluție e potrivită doar pentru development / o singură instanță de Gateway. Pentru producție, cu mai multe instanțe scalate orizontal, ar fi nevoie de o soluție distribuită (ex. Redis) — intenționat neintrodusă acum.

## Cum pornesc proiectul

```bash
docker compose up --build
```

⚠️ Prima pornire a `verification-service` durează mult mai mult decât restul (build-ul instalează TensorFlow + DeepFace, apoi descarcă modelele la boot) — e normal, se întâmplă o singură dată (imagine + model cache-uite după).

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
- support-service: http://localhost:8005/docs
- exchange-service: http://localhost:8006/docs
- verification-service: http://localhost:8007/docs
- ai-orchestrator-service: http://localhost:8008/docs

## Teste automate

Fiecare serviciu cu logică de business are teste pytest, rulate cu o bază MongoDB de TEST separată (nu ating datele demo). `verification-service` și `ai-orchestrator-service` sunt stateless — nu au nevoie de `MONGO_URL` la teste.

```bash
docker compose exec auth-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/auth_db_test auth-service python -m pytest -q

docker compose exec accounts-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/accounts_db_test accounts-service python -m pytest -q

docker compose exec transactions-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/tx_db_test transactions-service python -m pytest -q

docker compose exec budgets-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/budgets_db_test budgets-service python -m pytest -q

docker compose exec support-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/support_db_test support-service python -m pytest -q

docker compose exec exchange-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/exchange_db_test exchange-service python -m pytest -q

docker compose exec verification-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
docker compose exec verification-service python -m pytest -q

docker compose exec ai-orchestrator-service pip install -r requirements-dev.txt -q
docker compose exec ai-orchestrator-service python -m pytest -q
```

## Configurare

Copiază `.env.example` în `.env` și ajustează dacă e nevoie (`.env` e în `.gitignore`, nu conține secrete reale implicit). Vezi comentariile din `.env.example` pentru: alegerea MongoDB Atlas vs. local, SMTP pentru codul de verificare email, și credențialele Azure OpenAI pentru MaestroAgent.

## Limitări cunoscute (documentate explicit, nu ascunse)

- **Atomicitate transfer**: MongoDB standalone (fără replica set) nu suportă tranzacții multi-document. Debit + credit se aplică prin 2 operații condiționate, atomice la nivel de document, cu rollback manual dacă a doua eșuează — nu oferă garanțiile unui ledger bancar real.
- **Provizionare cont la register**: sincronă, fără retry automat dacă `accounts-service` e indisponibil exact în acel moment — userul rămâne creat, dar fără cont bancar.
- **Rate limiting**: în memorie, per instanță de Gateway — nu se scalează orizontal fără o soluție distribuită.
- **JWT în frontend**: ținut în `sessionStorage`, alegere de DEVELOPMENT, nu arhitectură de securitate pentru producție.
- **IBAN demo**: cifrele de control sunt pseudo-aleatoare, NU calculate conform standardului real (MOD-97) — suficient pentru UI, nu valid ca IBAN real.
- **Verificare identitate**: DeepFace compară efectiv fețele (nu e simulat), dar NU validează că documentul e un buletin real, nu e expirat, sau că datele extrase (nume, CNP) corespund — doar potrivirea facială e reală.
- **Similaritate facială**: procentul afișat (`similarity_percent`) e derivat direct din distanța cosine întoarsă de DeepFace, NU o probabilitate calibrată statistic — util ca reper vizual, nu ca metrică de încredere formală.
- **Setările de securitate ale cardului sunt cosmetice**: freeze, plăți online/contactless/ATM/internaționale, limită zilnică — toate se salvează real în bază și UI-ul reflectă corect starea, dar NIMIC nu le verifică vreodată înainte de a permite o operațiune (spre deosebire de "Coming soon" din secțiunea de mai jos, care sunt marcate explicit ca inerte, astea ARATĂ funcționale). Motivul structural: aplicația nu simulează un flux de "plată cu cardul la comerciant" — banii se mișcă doar prin transferuri IBAN-la-IBAN, deci n-are unde să existe un punct de aplicare a acestor reguli.
- **Screening de conținut**: lista de termeni periculoși din descrierea unui transfer (`transactions-service/app/content_screening.py`) e o listă demonstrativă (câteva sute de rădăcini, RO+EN), NU conținutul complet al vreunei liste oficiale de sancțiuni/AML. Doar avertizează — transferul TOT trece.
- **Detecție de abonamente**: euristică deterministă (grupare după descriere, sumă asemănătoare ±10%, cadență 20-40 zile) — NU e ML, poate rata pattern-uri neregulate sau poate cere 2+ apariții înainte să sugereze ceva nou.

## Ce lipsește față de planul complet (Cumpăna)

- **RabbitMQ** — nu rulează încă în `docker-compose.yml`. Necesar pentru fluxul asincron (`transaction.created` → analiză Guardian în fundal, fără să blocheze userul).
- **Financial Guardian** — zona vizuală există (Cardul meu, Detalii tranzacție), marcată explicit "Coming in AI phase" — fără detecție reală de anomalii.
- **Validare IBAN MOD-97** — clienții pot avea IBAN-uri demo generate cu cifre de control pseudo-aleatoare; validarea reală MOD-97 la transferuri nu e încă aplicată.
- Plăți reale, Visa/Mastercard, SEPA, Open Banking/PSD2, IBAN-uri bancare reale, schimb valutar real, PIN real de card — intenționat, niciodată planificate (proiect demo) — vezi butoanele marcate "Coming soon" din Cardul meu (Change PIN, Transaction alerts, Payment confirmation).

## UI — MaestroBank

Design-ul curent al Angular-ului reproduce mockup-urile din `UI reference/` (Overview, Cards, Transactions, Exchange, AI Copilot) — sidebar bleumarin, fundal alb, accent albastru, design tokens centralizate în `frontend/src/styles.css` (inclusiv temă dark, comutabilă din topbar). Componente reutilizabile în `frontend/src/app/shared/components/` (AppShell, Sidebar, Topbar, StatCard, AccountCard, TransactionRow, TransactionDetailsPanel, StatusBadge, ToggleControl, ActionButton, Modal, ConfirmDialog, EmptyState, LoadingSkeleton, Toast, Icon). Pagini în `frontend/src/app/features/*`, inclusiv fluxul de onboarding (`features/onboarding/`) și abonamentele/obiectivele de economisire (Pockets, tab "Obiective" din Conturi).
