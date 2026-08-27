# Investiții — design

Data: 2026-08-27
Status: aprobat, în implementare directă (fără plan separat detaliat — execuție
directă, verificată live la fiecare pas, ca la finalul Depozitelor)

## Context

Al doilea sub-proiect din "Depozite + Investiții" (Depozitele sunt gata,
complet, verificate). Cumpărare/vânzare de acțiuni/ETF-uri reale, cu preț de
piață real, folosind exact primitivele generice (`debit`/`credit` pe un
cont) construite special pentru asta la Depozite.

## Sursa de preț — verificată live, nu presupusă

Prima alegere (Stooq, propusă inițial ca echivalent BNR) **nu mai
funcționează fără cheie** — endpoint-ul CSV public e mort/protejat de
verificare anti-bot (`https://stooq.com/q/l/...` → 404; `/q/d/l/...` →
challenge JS). Verificat live, nu doar presupus.

**Sursa aleasă**: endpoint-ul **neoficial** Yahoo Finance —
`https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}` (header
`User-Agent` necesar, altfel unele cereri sunt respinse). Verificat live cu
16 simboluri, toate răspund cu preț real curent (`meta.regularMarketPrice`)
și nume companie (`meta.longName`). Simbol invalid → JSON curat cu
`error.code = "Not Found"`, ușor de tratat.

**Diferență onestă față de BNR**: BNR e un feed OFICIAL, documentat, publicat
de banca centrală. Endpoint-ul Yahoo e NEOFICIAL — nu există un echivalent
gratuit, fără cheie, oficial pentru cotații bursiere live. Documentat cinstit
ca atare în cod (la fel cum am fost cinstiți despre ratele de depozit —
nu pretindem o garanție care nu există). Fallback: ultimul preț cunoscut,
cache-uit — dacă Yahoo devine indisponibil, portofoliul arată ultimul preț
văzut, nu crapă.

## Catalog curatoriat (16 simboluri, toate verificate live)

| Simbol | Nume | Preț verificat (demo) |
|---|---|---|
| AAPL | Apple Inc. | $313.45 |
| MSFT | Microsoft | $496.37 |
| GOOGL | Alphabet | $342.00 |
| AMZN | Amazon | $260.28 |
| TSLA | Tesla | $345.82 |
| NVDA | NVIDIA | $209.66 |
| META | Meta Platforms | $576.14 |
| NFLX | Netflix | $81.46 |
| DIS | Disney | $109.63 |
| JPM | JPMorgan Chase | $356.50 |
| V | Visa | $383.90 |
| KO | Coca-Cola | $90.08 |
| BRK-B | Berkshire Hathaway B | $504.91 |
| SPY | S&P 500 ETF | $766.08 |
| QQQ | Nasdaq 100 ETF | $711.37 |
| IWM | Russell 2000 ETF | $298.93 |

Nu o piață deschisă (căutare orice simbol) — catalog fix, hardcodat, ca
tabelul de rate de la Depozite. Toate se tranzacționează în **USD**.

## Arhitectură

```
Angular (pagină nouă "Investiții", în meniu, separată de Conturi)
        │
API Gateway ──► investments-service (nou, :8010, investments_db)
                     │                              │
                     │ cumpără/vinde                │ proces de fundal
                     ▼                              │ (poll ~15 min)
              accounts-service                      ▼
              (REUTILIZEAZĂ debit/credit      reîmprospătează cache de
               generice, deja construite       prețuri (16 simboluri) de
               la Depozite — Task 1)           la Yahoo, cu fallback pe
                                                ultimul preț cunoscut
```

`investments-service` urmează structura standard (main/config/database/
security/models/service/routers), la fel ca `deposits-service`.

## Modelul de date

```
investments_db.holdings:
  _id, user_id, symbol, quantity (float, fracționată),
  avg_cost_minor_per_share (int, preț mediu de achiziție, bani/cenți USD),
  updated_at

investments_db.price_cache:
  _id = symbol, name, price_minor (bani/cenți USD), updated_at, source ("yahoo" | "fallback")
```

Fără colecție separată de "ordine" — o cumpărare/vânzare doar
crește/scade `quantity` și recalculează `avg_cost_minor_per_share` (medie
ponderată la cumpărare; la vânzare, cost mediu neschimbat, doar `quantity`
scade) — la fel de simplu ca o poziție netă, fără istoric tranzacție per
ordin (YAGNI — nu construim un ledger de tranzacții bursiere complet
pentru un demo).

## Fluxuri

**Cumpărare** (`POST /investments/buy {symbol, amount_minor}`):
1. Validează simbolul e în catalog.
2. Ia prețul curent din cache (`price_cache`).
3. `quantity_bought = amount_minor / price_minor` (float).
4. Rezolvă contul USD al userului (`get_account_by_user_and_type`, REUTILIZAT
   din Depozite) → `debit_account(amount_minor)`.
5. Upsert holding: dacă există deja o poziție pe acel simbol, recalculează
   media ponderată (`avg_cost_nou = (avg_vechi×qty_veche + preț×qty_nouă) / (qty_veche+qty_nouă)`);
   altfel creează una nouă.

**Vânzare** (`POST /investments/sell {symbol, quantity}`):
1. Verifică userul are destule `quantity` din simbolul respectiv.
2. `proceeds_minor = quantity × preț_curent`.
3. `credit_account(proceeds_minor)`.
4. Scade `quantity`; dacă ajunge la 0, șterge holding-ul.

**Portofoliu** (`GET /investments/portfolio`): per holding, calculează
valoare curentă (`quantity × preț_curent`) și câștig/pierdere nerealizat(ă)
(`valoare_curentă - quantity × avg_cost`).

## Frontend

Pagină nouă, separată, în meniul lateral ("Investiții") — NU tab pe Conturi
(suprafață prea mare: catalog cu preț live, formular cumpărare/vânzare,
tabel portofoliu cu câștig/pierdere). Stil vizual identic cu restul
aplicației (carduri, culori, `MoneyPipe`).

## Testare

`investments-service`: pytest complet (cumpărare — sold suficient/
insuficient/simbol invalid, vânzare — cantitate suficientă/insuficientă,
recalcul medie ponderată, portofoliu — câștig/pierdere corect). Mock-uri pe
apelurile către accounts-service, la fel ca Depozitele. Fetch de preț de la
Yahoo NU e apelat în teste — mock-uit, cu propriul test pentru fallback pe
indisponibilitate.

Verificare live prin Gateway (curl) + `ng build` + restart frontend, ca la
Depozite.

## Non-goals

- Istoric complet de ordine/tranzacții bursiere (doar poziția netă).
- Piață deschisă de căutat orice simbol — doar catalogul curatoriat.
- Alte valute în afară de USD pentru tranzacționare.
- Grafice de preț istoric.
