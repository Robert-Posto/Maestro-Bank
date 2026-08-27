# Depozite la termen — design

Data: 2026-08-27
Status: aprobat de user, gata pentru plan de implementare

## Context

MaestroBank are azi un tip de cont "depozit" (`account_type="deposit"`) complet
gol funcțional — un cont RON simplu, fără termen, fără dobândă, fără nimic
care să-l diferențieze de "economii" în afară de etichetă și iconiță. Userul
a cerut un feature real de depozite la termen, "cât mai profi, ca la o bancă
reală", construit cu aceeași filozofie ca `exchange-service` (rată reală/
politică transparentă, execuție reală prin `accounts-service`).

Investițiile (acțiuni/fonduri) au fost identificate ca un subsistem separat,
mult mai mare (date de piață externe, portofoliu, ordine de cumpărare/
vânzare) și **explicit exclus din acest spec** — se proiectează separat,
după ce Depozitele sunt gata. Primitivele generice construite aici
(debit/credit pe un singur cont în accounts-service) sunt gândite să fie
reutilizate direct de Investiții mai târziu.

## Decizii confirmate cu userul

1. **Tipul de cont "deposit" vechi dispare** — înlocuit complet de feature-ul
   nou. Nu mai există două lucruri numite "depozit" care fac altceva.
2. **Mai multe depozite simultan per user** (nu doar unul) — ca la o bancă
   reală, fiecare cu propria sumă/termen/rată, urmărite separat (structural
   similar cu Pockets).
3. **Lichidare anticipată permisă, dar cu pierderea integrală a dobânzii**
   acumulate — userul primește înapoi doar principalul.
4. **La scadență: reînnoire automată implicită** (configurabilă per depozit,
   la deschidere) — dacă userul n-a ales explicit plata la scadență, depozitul
   se redeschide automat pe același termen, la rata *curentă* din tabel.
5. **Multi-monedă de la început**: RON, EUR, USD, GBP (aplicația are deja
   conturi în aceste valute, folosite și de exchange-service).
6. **Serviciu nou dedicat**: `deposits-service`, NU extindere în
   `accounts-service` — motiv: are nevoie de propriul proces de fundal
   (verificare scadențe), la fel ca `exchange-service` are nevoie de al lui
   (refresh curs BNR). Consistent cu precedentul arhitectural deja stabilit.
7. **Rata dobânzii NU e "live" de nicăieri** — spre deosebire de cursul FX
   (unde BNR publică un feed XML public zilnic, exact sursa reală folosită de
   bănci), nu există un echivalent curat pentru dobânzi de depozit: BNR
   publică doar rata de politică monetară (schimbată rar, fără feed
   structurat), iar băncile reale oricum își stabilesc propriile rate de
   depozit ca politică internă, nu direct din piață. MaestroBank publică
   deci **propriul tabel de rate**, documentat clar în cod ca politică
   proprie (nu pretins ca sursă externă) — vezi tabelul de mai jos.

## Arhitectură

```
Angular (Conturi → tab nou "Depozite")
        │
API Gateway ──► deposits-service (nou, :8009, deposits_db)
                     │                              │
                     │ deschide/lichidează          │ proces de fundal
                     ▼                              │ (poll periodic)
              accounts-service                      ▼
              (2 endpoint-uri INTERNE noi,    verifică depozitele scadente,
               generice, reutilizabile        reînnoiește SAU plătește
               și de viitorul serviciu de     automat în contul sursă
               Investiții):
                 POST /internal/accounts/{id}/debit   {amount_minor}
                 POST /internal/accounts/{id}/credit  {amount_minor}
              +
              GET /internal/accounts/by-user-and-type/{user_id}/{account_type}
              (rezolvă contul userului pt o monedă dată — RON→"current",
               altfel tipul = codul monedei, ca la exchange-service)
```

`debit`/`credit` sunt primitive **generice, cu un singur cont** — spre
deosebire de `transfer` (cont→cont) și `exchange` (RON↔valută), niciuna nu se
potrivește cu "banii ies dintr-un cont și intră într-un depozit" (depozitul
nu e un document `accounts_db.accounts`). `debit` e condiționat/atomic
(`update_one` cu filtru `balance_minor >= amount`, 409 la sold insuficient),
exact tiparul deja folosit la transfer/exchange.

`deposits-service` urmează STRICT structura standard a celorlalte servicii
(`main.py` / `config.py` / `database.py` / `models.py` / `security.py` /
`routers/` / `service.py`), cu un `maturity_loop` în `lifespan` (la fel ca
`transactions-service/app/scheduler.py` — pornit/oprit la boot/shutdown,
poll la interval configurabil, implicit 60s pentru demo, ca restul
scheduler-elor din acest backend).

## Modelul de date

```
deposits_db.deposits:
  _id
  user_id
  currency: "RON" | "EUR" | "USD" | "GBP"
  principal_minor: int          # suma depusă, bani/cenți
  term_months: 3 | 6 | 12 | 24
  rate_percent_annual: float    # FIXĂ la deschidere — nu se schimbă dacă
                                 # tabelul MaestroBank se modifică ulterior
  opened_at: datetime
  matures_at: datetime          # opened_at + term_months
  renew_at_maturity: bool       # ales de user la deschidere, implicit True
  status: "active" | "matured_renewed" | "liquidated_early" | "closed_paid_out"
  source_account_id: str        # contul din care s-a luat suma / unde revine
  renewed_into_deposit_id: str | None   # legătură către noul depozit, dacă s-a reînnoit
  renewed_from_deposit_id: str | None   # legătură inversă, pt istoric/UI
```

**Sumă minimă**: 500 RON echivalent (implicit prag separat per monedă —
~100 EUR/USD/GBP), ca să evităm depozite-jucărie.

**Dobândă simplă** (standardul pentru depozite la termen RO, plătită la
scadență, nu compusă): `interest_minor = round(principal_minor × rate_percent_annual/100 × term_months/12)`.

## Tabelul de rate (politică MaestroBank, hardcodat + documentat)

| Termen   | RON   | EUR   | USD   | GBP   |
|----------|-------|-------|-------|-------|
| 3 luni   | 5.00% | 2.00% | 3.50% | 3.75% |
| 6 luni   | 5.50% | 2.25% | 3.75% | 4.00% |
| 12 luni  | 5.75% | 2.50% | 4.00% | 4.25% |
| 24 luni  | 5.25% | 2.25% | 3.75% | 4.00% |

Trăiește într-un `app/rates.py` propriu (funcție pură `get_rate(currency, term_months) -> float`),
ca să fie ușor de testat și de actualizat manual — NU un fetch HTTP către
nimic extern (vezi decizia #7 de mai sus).

## Fluxuri

**Deschidere depozit** (`POST /deposits/open`):
1. Validează `term_months` ∈ {3,6,12,24}, `currency` ∈ {RON,EUR,USD,GBP},
   `amount_minor` ≥ pragul minim pt acea monedă.
2. Rezolvă contul sursă: `GET /internal/accounts/by-user-and-type/{user_id}/{type}`
   (RON→"current", altfel tipul = moneda lowercase — cere ca userul să aibă
   deja deschis acel cont, la fel ca la exchange, 400 clar dacă nu).
3. `POST /internal/accounts/{source_id}/debit` — 409 propagat curat ("sold
   insuficient") dacă nu are destui bani.
4. Inserează documentul `deposits` cu `rate_percent_annual` = rata curentă
   din tabel pt (currency, term_months) — SNAPSHOT, nu referință live.

**Lichidare anticipată** (`POST /deposits/{id}/liquidate`):
1. Verifică proprietate (404 dacă nu e al userului) și `status == "active"`.
2. `POST /internal/accounts/{source_id}/credit` cu DOAR `principal_minor`
   (dobânda se pierde).
3. `status = "liquidated_early"`.

**Maturare** (`maturity_loop`, rulează la fiecare `MATURITY_POLL_SECONDS`):
1. Găsește toate depozitele `status="active"` cu `matures_at <= now`.
2. Calculează dobânda (formula de mai sus).
3. Dacă `renew_at_maturity=True`: deschide un depozit NOU cu
   `principal_minor = principal + interest`, la rata CURENTĂ din tabel pt
   același `(currency, term_months)` (nu neapărat aceeași rată ca depozitul
   vechi) — `status` vechi devine `"matured_renewed"`, cu
   `renewed_into_deposit_id` populat.
4. Dacă `renew_at_maturity=False`: `POST /internal/accounts/{source_id}/credit`
   cu `principal + interest`, `status = "closed_paid_out"`.

## Frontend

Al treilea tab pe pagina **Conturi** (lângă "Conturi" / "Obiective"), stil
identic (carduri, bară de progres pt zile rămase până la scadență — reutilizat
vizual din Pockets).

- **Listă de depozite**: card per depozit — sumă, monedă, termen, rată,
  zile rămase, status, buton "Lichidează anticipat" (confirm dialog cu
  avertisment explicit că pierde dobânda).
- **"Depozit nou"**: modal — alegere monedă → termen (arată rata pt fiecare,
  din `GET /deposits/rates`) → sumă → toggle "Reînnoiește automat la
  scadență" (implicit pornit).
- Card-ul de sumar de sus de pe Conturi ("Pus deoparte") se extinde să
  includă și suma blocată în depozite active, nu doar `savings`/`deposit`
  (tipul vechi dispare din calcul, evident).
- Tipul de cont "Depozit" dispare din modalul "Cont nou" / carusel de tipuri
  creabile (`CREATABLE_ACCOUNT_TYPES`).

## Migrare / date existente

Cont-uri `account_type="deposit"` deja existente (seed data / conturi reale
create de useri în timpul dezvoltării) — dat fiind că e mediu de demo/dev,
NU migrăm automat solduri: contul rămâne pur și simplu needitabil de aici
înainte (nu mai apare ca opțiune de creat), dar nu-l ștergem — un cont deja
deschis rămâne vizibil/funcțional ca înainte (transfer în/din el prin IBAN
tot merge), doar nu se mai poate DESCHIDE unul nou de acest tip. Documentat
explicit în cod, ca viitorii cititori să înțeleagă de ce tipul mai există în
`AccountType` dar nu în `CreatableAccountType`.

## Testare

- `deposits-service`: pytest complet — deschidere (sold suficient/insuficient,
  sub prag minim, monedă fără cont deschis), lichidare anticipată (pierde
  dobânda, respinge dacă nu-i al userului / nu e activ), maturare+reînnoire
  (rata nouă corectă, legături `renewed_into/from`), maturare+plată (fără
  reînnoire), tabelul de rate (toate combinațiile monedă×termen).
- `accounts-service`: teste pt cele 2 endpoint-uri interne noi (debit atomic
  cu sold insuficient → 409, credit simplu, rezolvare cont per user+tip).
- Verificare live prin Gateway (curl) + `ng build` + restart frontend —
  același flux folosit toată sesiunea asta.

## Non-goals (explicit excluse din acest spec)

- Investiții (acțiuni/fonduri/ETF) — subsistem separat, spec propriu ulterior.
- Depozite cu dobândă compusă sau plată lunară a dobânzii.
- Migrare automată a conturilor `deposit` vechi către noul sistem.
- Rată "live" fetch-uită dintr-o sursă externă.
