#!/usr/bin/env python3
"""
scripts/seed_fraud_scenarios.py — Seed de date pentru calibrarea motorului
de fraud (app/fraud/, transactions-service, Faza 1 — shadow mode).

Separat de seed_demo_data.py (cei 3 clienți "vitrină", pentru testarea
manuală a restului aplicației) — acest script există STRICT ca să dea
motorului de scoring date pe care să le evalueze: destule tranzacții cât să
populeze un cohort baseline plauzibil, plus o mână de useri care reproduc
DELIBERAT tiparele din catalogul de reguli (vezi guardian-claude-code-prompt.md),
astfel încât raportul shadow-mode (GET /internal/fraud/shadow-report) să
aibă ce arăta, nu doar zerouri.

Creează:
  - 10 useri "baseline": user + cont RON + card + ~40-60 tranzacții de
    cheltuieli, distribuite pe 60 de zile, cu categorii/sume realiste —
    suficient cât să dea un cohort baseline (percentile globale) cu sens.
  - 8 useri "scenariu": fiecare reproduce UN tipar clar din catalog (vezi
    SCENARIOS mai jos), cu istoric propriu STABILIT (>=20 tranzacții, ca să
    nu cadă în cold start din greșeală — exceptând scenariul "dormant",
    unde cold start / inactivitatea e CHIAR punctul testat).

De ce istoricul de bază se scrie direct în Mongo, dar tranzacția-DECLANȘATOR
a fiecărui scenariu trece prin API-ul REAL (POST /api/transactions/transfers,
prin Gateway): la fel ca-n seed_demo_data.py, API-urile publice folosesc
datetime.now() — nu pot crea istoric retroactiv. DAR motorul de fraud
(app/fraud/service.py) rulează DOAR când create_transfer chiar execută — un
insert_many direct în tx_db NU-l declanșează. De-aia fiecare scenariu are
un pas live, real, prin Gateway: e singura cale să apară o înregistrare
reală în tx_db.fraud_evaluations, verificabilă la finalul scriptului.

Profilul fraud (tx_db.fraud_profiles) al fiecărui user e construit direct
din istoricul generat — IDENTIC ca formă cu ce ar produce
transactions-service/app/fraud/profile.py::update_profile_after_transfer
aplicat incremental pe fiecare tranzacție de ieșire, doar calculat aici
dintr-o dată pe tot lotul (echivalent matematic) — vezi
`_build_fraud_profile_doc`. Motivul e același ca la restul scriptului:
API-ul real actualizează profilul DOAR la transferuri live, niciodată
retroactiv.

STRICT PENTRU DEVELOPMENT — reutilizează exact aceleași gărzi de siguranță
ca seed_demo_data.py (importate de-acolo, nu duplicate).

Rulare (din interiorul containerului auth-service — vezi seed_demo_data.py
pentru motivul: singurul cu scripts/ montat și toate dependențele):

    docker compose exec \\
        -e APP_ENV=development \\
        -e ALLOW_DEMO_SEED=true \\
        -e DEMO_USER_PASSWORD='ParolaDemo123' \\
        -e MONGO_URL=mongodb://mongodb:27017 \\
        auth-service python scripts/seed_fraud_scenarios.py

Idempotent — identifică toți userii proprii prin domeniul de email
"@fraudsim.maestrobank.local" (distinct de cel folosit de seed_demo_data.py,
".demo@maestrobank.local", ca cele două seed-uri să nu se calce pe picioare)
și îi șterge complet (user, cont, card, tranzacții, profil fraud) înainte
de a recrea.

Reguli din catalog NEACOPERITE de un scenariu dedicat aici (extensie
viitoare, nu lipsă critică): BEN-03 (țară IBAN necunoscută — are nevoie de
un IBAN non-RO plauzibil), DEV-03 (are nevoie de un credential WebAuthn
fals în auth_db), AMT-02/AMT-05/TIME-01/BEH-02 (pot apărea incidental ca
efect secundar al celorlalte scenarii, dar nu sunt garantate).
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # ca seed_demo_data să fie importabil indiferent de cwd

from seed_demo_data import (  # noqa: E402 — vezi sys.path.insert de mai sus
    AMOUNT_RANGES_RON,
    CATEGORY_WEIGHTS,
    _random_day_between,
    _require_demo_password,
    _require_development_environment,
    _slugify,
    format_minor_amount,
    generate_unique_demo_iban,
    hash_password,
)

# NU reutilizăm seed_demo_data.py::create_pseudo_account — marchează
# conturile DOAR cu is_demo_merchant=True, fără niciun câmp care să distingă
# "merchant al ACESTUI script" de "merchant al seed_demo_data.py". Cleanup-ul
# ACELUI script șterge NESCOPED orice is_demo_merchant=True (linia 345,
# seed_demo_data.py) — dacă am folosi aceeași funcție, fie propriul nostru
# cleanup nu le-ar găsi niciodată (nu idempotent), fie o rulare ulterioară a
# CELUILALT script ne-ar șterge conturile-pseudo pe furiș. `create_pseudo_
# account` de mai jos e o copie DELIBERATĂ, cu marcaj propriu `is_fraud_sim`,
# exact ca să evite ambele probleme.

# --------------------------------------------------------------------------
# Determinism — seed PROPRIU, distinct de cel din seed_demo_data.py, ca cele
# două scripturi să rămână independent reproductibile.
# --------------------------------------------------------------------------
RANDOM_SEED = 20260820

EMAIL_DOMAIN = "fraudsim.maestrobank.local"
N_BASELINE_USERS = 10
BASELINE_TX_COUNT_RANGE = (40, 60)
BASELINE_HISTORY_DAYS = 60
BASELINE_CATEGORIES = ["groceries", "shopping", "transport", "restaurants", "bills", "entertainment", "other"]
BASELINE_OPENING_BALANCE_RANGE_RON = (3000, 15000)

_HISTORY_SAMPLE_CAP = 300  # IDENTIC cu app/fraud/profile.py::_HISTORY_SAMPLE_CAP


# --------------------------------------------------------------------------
# Helpere mici, proprii acestui script (fără echivalent reutilizabil din
# seed_demo_data.py).
# --------------------------------------------------------------------------


def _user_email(key: str) -> str:
    return f"{key}@{EMAIL_DOMAIN}"


async def create_pseudo_account(db_accounts, pseudo_id: str, name: str, created_at: datetime) -> dict:
    """Copie deliberată a seed_demo_data.py::create_pseudo_account, cu
    marcaj propriu `is_fraud_sim` — vezi nota de la import-uri, mai sus,
    pentru motiv."""
    iban = await generate_unique_demo_iban(db_accounts.accounts)
    doc = {
        "user_id": f"merchant:{pseudo_id}",
        "iban": iban,
        "currency": "RON",
        "balance_minor": 0,
        "status": "active",
        "account_type": "current",
        "created_at": created_at,
        "is_demo": True,
        "is_fraud_sim": True,
        "merchant_name": name,
    }
    result = await db_accounts.accounts.insert_one(doc)
    return {"account_id": str(result.inserted_id), "iban": iban, "name": name}


async def create_scenario_user(db_auth, db_accounts, key: str, first_name: str, last_name: str, password_hash: str, created_at: datetime) -> dict:
    """Variantă restrânsă a seed_demo_data.py::create_demo_user (nu are
    nevoie de spec-ul complet — merchants/subscriptions/budgets nu au
    relevanță pentru motorul de fraud)."""
    user_doc = {
        "first_name": first_name,
        "last_name": last_name,
        "email": _user_email(key),
        "phone_number": f"+4072{random.randint(1000000, 9999999)}",
        "password_hash": password_hash,
        "created_at": created_at,
        "is_active": True,
        "is_demo": True,
        "is_fraud_sim": True,
        "role": "customer",
        # Userii fraud-sim NU trec prin register public — la fel ca-n
        # seed_demo_data.py::create_demo_user, îi marcăm direct verificați,
        # altfel authGuard din frontend i-ar bloca în onboarding la login.
        "email_verified": True,
        "identity_verified": True,
    }
    result = await db_auth.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    iban = await generate_unique_demo_iban(db_accounts.accounts)
    account_result = await db_accounts.accounts.insert_one(
        {
            "user_id": user_id,
            "iban": iban,
            "currency": "RON",
            "balance_minor": 0,  # recalculat la final din tranzacțiile generate, ca-n seed_demo_data.py
            "status": "active",
            "account_type": "current",
            "created_at": created_at,
            "is_demo": True,
            "is_fraud_sim": True,
        }
    )
    account_id = str(account_result.inserted_id)

    now = datetime.now(timezone.utc)
    await db_accounts.cards.insert_one(
        {
            "user_id": user_id,
            "account_id": account_id,
            "last_four": f"{random.randint(1000, 9999)}",
            "expiry_month": now.month,
            "expiry_year": now.year + 3,
            "status": "active",
            "type": "virtual",
            "created_at": created_at,
            "is_frozen": False,
            "online_payments_enabled": True,
            "contactless_enabled": True,
            "atm_withdrawals_enabled": True,
            "international_payments_enabled": True,
            "daily_limit_minor": 10_000_00,
            "is_demo": True,
            "is_fraud_sim": True,
        }
    )

    return {"key": key, "user_id": user_id, "account_id": account_id, "iban": iban, "first_name": first_name, "last_name": last_name}


class Ledger:
    """La fel ca seed_demo_data.py::Ledger — acumulează tranzacții +
    delta de sold în Python înainte de scriere, ca soldul final să fie
    garantat matematic identic cu suma tranzacțiilor."""

    def __init__(self) -> None:
        self.transactions: list[dict] = []
        self.balance_deltas: dict[str, int] = {}

    def add(self, from_ctx: dict, to_ctx: dict, amount_ron: float, category: str, description: str, when: datetime, status: str = "completed") -> dict:
        amount_minor = round(amount_ron * 100)
        doc = {
            "from_account_id": from_ctx["account_id"],
            "to_account_id": to_ctx["account_id"],
            "from_iban": from_ctx["iban"],
            "to_iban": to_ctx["iban"],
            "amount_minor": amount_minor,
            "currency": "RON",
            "description": description,
            "category": category,
            "type": "transfer",
            "status": status,
            "recognized": False,
            "reported": False,
            "created_at": when,
            "is_demo": True,
            "is_fraud_sim": True,
        }
        self.transactions.append(doc)
        if status == "completed":
            self.balance_deltas[from_ctx["account_id"]] = self.balance_deltas.get(from_ctx["account_id"], 0) - amount_minor
            self.balance_deltas[to_ctx["account_id"]] = self.balance_deltas.get(to_ctx["account_id"], 0) + amount_minor
        return doc


def _weighted_category(categories: list[str]) -> str:
    weights = [CATEGORY_WEIGHTS.get(c, 1) for c in categories]
    return random.choices(categories, weights=weights, k=1)[0]


def generate_spending_history(
    ledger: Ledger, user_ctx: dict, merchant_accounts: dict[str, dict], opening_ctx: dict,
    opening_balance_ron: float, window_start: datetime, now: datetime, tx_count: int,
    categories: list[str] | None = None,
) -> None:
    """Istoric de cheltuieli simplu — DOAR ce are nevoie motorul de fraud
    (sume/categorii/momente realiste), fără salarii/abonamente/bugete (nu
    sunt citite de nicio regulă din Faza 1)."""
    categories = categories or BASELINE_CATEGORIES
    ledger.add(opening_ctx, user_ctx, opening_balance_ron, "other", "Sold inițial (fraud-sim)", window_start + timedelta(hours=1))

    for _ in range(tx_count):
        category = _weighted_category(categories)
        merchant_name = random.choice(merchant_accounts[category])
        merchant_ctx = merchant_accounts["_by_name"][merchant_name]
        amount = round(random.uniform(*AMOUNT_RANGES_RON.get(category, (20, 200))), 2)
        when = _random_day_between(window_start, now - timedelta(hours=1))
        ledger.add(user_ctx, merchant_ctx, amount, category, merchant_name, when)


def _build_fraud_profile_doc(user_id: str, account_id: str, all_transactions: list[dict], now: datetime) -> dict | None:
    """IDENTIC ca formă cu transactions-service/app/fraud/profile.py
    ::update_profile_after_transfer, aplicat pe tot lotul deodată — vezi
    docstring-ul modulului. Include DOAR tranzacțiile unde acest cont e
    SURSA (from_account_id) — profilul urmărește comportamentul celui care
    INIȚIAZĂ transferul, exact ca în create_transfer real."""
    outgoing = sorted(
        (t for t in all_transactions if t["from_account_id"] == account_id and t["status"] == "completed"),
        key=lambda t: t["created_at"],
    )
    if not outgoing:
        return None

    category_counts: dict[str, int] = {}
    beneficiary_countries: set[str] = set()
    samples = []
    for tx in outgoing:
        category_counts[tx["category"]] = category_counts.get(tx["category"], 0) + 1
        beneficiary_countries.add(tx["to_iban"][:2])
        samples.append(
            {"amount_minor": tx["amount_minor"], "category": tx["category"], "hour_utc": tx["created_at"].hour, "created_at": tx["created_at"]}
        )

    return {
        "user_id": user_id,
        "transaction_count": len(outgoing),
        "first_transaction_at": outgoing[0]["created_at"],
        "last_transaction_at": outgoing[-1]["created_at"],
        "history_samples": samples[-_HISTORY_SAMPLE_CAP:],
        "category_counts": category_counts,
        "beneficiary_countries": sorted(beneficiary_countries),
        "created_at": outgoing[0]["created_at"],
        "updated_at": outgoing[-1]["created_at"],
    }


# --------------------------------------------------------------------------
# Curățenie idempotentă — scoped STRICT la userii @fraudsim.maestrobank.local
# (lecție învățată: fiecare query de ștergere de mai jos e scoped explicit
# pe o listă de ID-uri, NICIODATĂ pe un filtru de forma "orice document cu
# câmpul X" — un astfel de filtru nescoped a produs un incident anterior).
# --------------------------------------------------------------------------


async def cleanup_fraud_sim_data(db_auth, db_accounts, db_tx) -> int:
    existing_users = await db_auth.users.find({"email": {"$regex": f"@{EMAIL_DOMAIN}$"}}).to_list(length=100)
    user_ids = [str(u["_id"]) for u in existing_users]

    if user_ids:
        accounts = await db_accounts.accounts.find({"user_id": {"$in": user_ids}}).to_list(length=100)
        account_ids = [str(a["_id"]) for a in accounts]

        if account_ids:
            await db_tx.transactions.delete_many(
                {"$or": [{"from_account_id": {"$in": account_ids}}, {"to_account_id": {"$in": account_ids}}]}
            )
        await db_tx.fraud_profiles.delete_many({"user_id": {"$in": user_ids}})
        await db_tx.fraud_evaluations.delete_many({"user_id": {"$in": user_ids}})
        await db_accounts.cards.delete_many({"user_id": {"$in": user_ids}})
        await db_accounts.accounts.delete_many({"user_id": {"$in": user_ids}})
        await db_auth.users.delete_many({"_id": {"$in": [ObjectId(uid) for uid in user_ids]}})

    merchant_accounts = await db_accounts.accounts.find({"is_fraud_sim": True, "user_id": {"$regex": "^merchant:"}}).to_list(length=200)
    merchant_account_ids = [str(a["_id"]) for a in merchant_accounts]
    if merchant_account_ids:
        await db_tx.transactions.delete_many(
            {"$or": [{"from_account_id": {"$in": merchant_account_ids}}, {"to_account_id": {"$in": merchant_account_ids}}]}
        )
        await db_accounts.accounts.delete_many({"_id": {"$in": [ObjectId(mid) for mid in merchant_account_ids]}})

    print(f"Curățenie fraud-sim: {len(user_ids)} useri + {len(merchant_account_ids)} conturi-pseudo șterse.")
    return len(user_ids)


# --------------------------------------------------------------------------
# Scenarii — fiecare reproduce UN tipar din catalog. Fiecare returnează
# {key, user, expected_rules, trigger_response} — verificat la final contra
# tx_db.fraud_evaluations REAL (nu doar presupus).
# --------------------------------------------------------------------------


async def run_live_transfer(client: httpx.AsyncClient, token: str, to_iban: str, amount_minor: int, description: str, category: str = "other") -> dict:
    response = await client.post(
        "/api/transactions/transfers",
        json={"to_iban": to_iban, "amount_minor": amount_minor, "description": description, "category": category},
        headers={"Authorization": f"Bearer {token}"},
    )
    return {"status_code": response.status_code, "body": response.json() if response.status_code < 500 else response.text}


async def scenario_drain(client, tokens, user_ctx, dest_ctx) -> dict:
    """AMT-03 + AMT-04 + BEN-01: 99% din sold, către un beneficiar NOU."""
    account = user_ctx["_live_balance_minor"]
    amount = round(account * 0.99)
    result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], amount, "Retragere urgentă", "other")
    return {"key": user_ctx["key"], "scenario": "drain (AMT-03, AMT-04, BEN-01)", "trigger": result}


async def scenario_velocity_burst(client, tokens, user_ctx, dest_ctxs) -> dict:
    """VEL-01 (+VEL-02): 6 transferuri rapide, succesive, către beneficiari diferiți."""
    results = []
    for i, dest_ctx in enumerate(dest_ctxs):
        result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], 5_000 + i * 100, f"Plată rapidă {i+1}", "shopping")
        results.append(result)
    return {"key": user_ctx["key"], "scenario": "velocity burst (VEL-01)", "trigger": results[-1], "all_triggers": results}


async def scenario_escalating(client, tokens, user_ctx, dest_ctx) -> dict:
    """VEL-05 (+BEN-01): 3 sume crescătoare, către ACELAȘI beneficiar nou, rapid."""
    results = []
    for amount_minor in (2_000, 8_000, 25_000):
        result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], amount_minor, "Test transfer", "other")
        results.append(result)
    return {"key": user_ctx["key"], "scenario": "escalating test-then-drain (VEL-05)", "trigger": results[-1], "all_triggers": results}


async def scenario_new_category(client, tokens, user_ctx, dest_ctx) -> dict:
    """BEH-01: categorie niciodată folosită de acest user (istoricul lui
    acoperă doar groceries/transport/bills — vezi seed())."""
    result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], 15_000, "Bilet concert", "entertainment")
    return {"key": user_ctx["key"], "scenario": "categorie nouă (BEH-01)", "trigger": result}


async def scenario_dormant(client, tokens, user_ctx, dest_ctx) -> dict:
    """TIME-02: userul are DOAR istoric vechi (>90 zile), nimic recent."""
    result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], 20_000, "Revenire după pauză", "other")
    return {"key": user_ctx["key"], "scenario": "dormant >90 zile (TIME-02)", "trigger": result}


async def scenario_structuring(client, tokens, user_ctx, dest_ctxs) -> dict:
    """STR-02: aceeași sumă EXACTĂ, către 3 beneficiari DIFERIȚI, rapid."""
    results = []
    for dest_ctx in dest_ctxs:
        result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], 9_900, "Contribuție", "other")
        results.append(result)
    return {"key": user_ctx["key"], "scenario": "structurare (STR-02)", "trigger": results[-1], "all_triggers": results}


async def scenario_passthrough(client, tokens, user_ctx, dest_ctx) -> dict:
    """BEH-03: creditul de intrare (inserat direct, cu puțin timp înainte)
    e urmat de un debit aproape egal, prin API-ul real."""
    result = await run_live_transfer(client, tokens[user_ctx["key"]], dest_ctx["iban"], 49_800, "Redirecționare fonduri", "other")
    return {"key": user_ctx["key"], "scenario": "pass-through (BEH-03)", "trigger": result}


async def scenario_mule_sender(client, tokens, user_ctx, mule_target_ctx) -> dict:
    """BEN-05 (informativ, exclus din scor): al 6-lea expeditor DISTINCT
    către același beneficiar, în ultimele 24h (5 istorice + acesta, live)."""
    result = await run_live_transfer(client, tokens[user_ctx["key"]], mule_target_ctx["iban"], 3_000, "Transfer", "other")
    return {"key": user_ctx["key"], "scenario": "tipar mulă (BEN-05)", "trigger": result}


# --------------------------------------------------------------------------
# Orchestrare
# --------------------------------------------------------------------------


async def seed(mongo_url: str, demo_password: str, gateway_url: str) -> dict:
    random.seed(RANDOM_SEED)

    client_mongo = AsyncIOMotorClient(mongo_url)
    db_auth = client_mongo["auth_db"]
    db_accounts = client_mongo["accounts_db"]
    db_tx = client_mongo["tx_db"]

    await client_mongo.admin.command("ping")
    print("Connected to configured MongoDB environment")

    await cleanup_fraud_sim_data(db_auth, db_accounts, db_tx)

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=BASELINE_HISTORY_DAYS)
    old_window_start = now - timedelta(days=180)  # pentru scenariul "dormant"

    # --- conturi-pseudo: comercianți (grupați pe categorie) + sold inițial + mule target ---
    merchant_accounts: dict[str, list[str]] = {}
    merchant_accounts["_by_name"] = {}
    for category in set(BASELINE_CATEGORIES + ["entertainment"]):
        names = [f"{category.capitalize()} Merchant {i}" for i in range(1, 3)]
        merchant_accounts[category] = names
        for name in names:
            ctx = await create_pseudo_account(db_accounts, _slugify(name), name, window_start)
            merchant_accounts["_by_name"][name] = ctx

    opening_ctx = await create_pseudo_account(db_accounts, "fraud-sim-opening-balance", "MaestroBank — Sold inițial (fraud-sim)", window_start)
    mule_target_ctx = await create_pseudo_account(db_accounts, "fraud-sim-mule-target", "Fraud-Sim Mule Target", window_start)

    password_hash = hash_password(demo_password)

    # --- useri baseline: istoric normal, ca să dea sens cohortei globale ---
    baseline_users = []
    ledger = Ledger()
    for i in range(1, N_BASELINE_USERS + 1):
        key = f"baseline-{i:02d}"
        user_ctx = await create_scenario_user(db_auth, db_accounts, key, "Baseline", f"User{i:02d}", password_hash, window_start)
        opening_balance = round(random.uniform(*BASELINE_OPENING_BALANCE_RANGE_RON), 2)
        tx_count = random.randint(*BASELINE_TX_COUNT_RANGE)
        generate_spending_history(ledger, user_ctx, merchant_accounts, opening_ctx, opening_balance, window_start, now, tx_count)
        baseline_users.append(user_ctx)

    # --- 5 dintre userii baseline trimit puțin către mule_target, în ultimele 24h ---
    for i, user_ctx in enumerate(baseline_users[:5]):
        when = now - timedelta(hours=20 - i * 2)
        ledger.add(user_ctx, mule_target_ctx, 25.0, "other", "Contribuție", when)

    # --- useri scenariu: istoric STABILIT propriu (>=25 tranzacții), ca să
    # nu cadă în cold start din greșeală (exceptând "dormant", unde asta e
    # CHIAR punctul) ---
    scenario_specs = [
        ("scenario-drain", "Drain", "Scenario"),
        ("scenario-velocity", "Velocity", "Scenario"),
        ("scenario-escalating", "Escalating", "Scenario"),
        ("scenario-newcat", "NewCategory", "Scenario"),
        ("scenario-dormant", "Dormant", "Scenario"),
        ("scenario-structuring", "Structuring", "Scenario"),
        ("scenario-passthrough", "Passthrough", "Scenario"),
        ("scenario-mulesender", "MuleSender", "Scenario"),
    ]
    scenario_users: dict[str, dict] = {}
    for key, first_name, last_name in scenario_specs:
        scenario_users[key] = await create_scenario_user(db_auth, db_accounts, key, first_name, last_name, password_hash, window_start)

    # drain/velocity/escalating/structuring/passthrough/mulesender: istoric NORMAL, RECENT
    for key in ["scenario-drain", "scenario-velocity", "scenario-escalating", "scenario-structuring", "scenario-passthrough", "scenario-mulesender"]:
        user_ctx = scenario_users[key]
        generate_spending_history(ledger, user_ctx, merchant_accounts, opening_ctx, 20_000.0, window_start, now, 30)

    # newcat: istoric STRICT în 2 categorii (groceries, transport) — ca
    # "entertainment" să fie garantat nou la declanșator
    generate_spending_history(
        ledger, scenario_users["scenario-newcat"], merchant_accounts, opening_ctx, 15_000.0, window_start, now, 30,
        categories=["groceries", "transport"],
    )

    # dormant: istoric VECHI (120-180 zile în urmă), NIMIC în ultimele 90 zile
    generate_spending_history(
        ledger, scenario_users["scenario-dormant"], merchant_accounts, opening_ctx, 12_000.0,
        old_window_start, now - timedelta(days=100), 25,
    )

    # passthrough: un credit de intrare, cu ~30 min înainte de declanșator
    passthrough_ctx = scenario_users["scenario-passthrough"]
    ledger.add(opening_ctx, passthrough_ctx, 500.0, "income", "Credit extern", now - timedelta(minutes=30))

    if ledger.transactions:
        await db_tx.transactions.insert_many(ledger.transactions)
    for account_id, delta in ledger.balance_deltas.items():
        await db_accounts.accounts.update_one({"_id": ObjectId(account_id)}, {"$inc": {"balance_minor": delta}})

    # --- profiluri fraud, construite din istoricul CHIAR generat mai sus ---
    all_users = baseline_users + list(scenario_users.values())
    profiles_written = 0
    for user_ctx in all_users:
        profile_doc = _build_fraud_profile_doc(user_ctx["user_id"], user_ctx["account_id"], ledger.transactions, now)
        if profile_doc:
            await db_tx.fraud_profiles.insert_one(profile_doc)
            profiles_written += 1

    print(f"Istoric generat: {len(ledger.transactions)} tranzacții, {profiles_written} profiluri fraud construite.")

    # --- rulare LIVE, prin API-ul real (Gateway) — vezi docstring-ul modulului ---
    scenario_results = []
    async with httpx.AsyncClient(timeout=15.0, base_url=gateway_url) as http_client:
        tokens: dict[str, str] = {}
        for user_ctx in all_users:
            email = _user_email(user_ctx["key"])
            response = await http_client.post("/api/auth/login", json={"email": email, "password": demo_password})
            if response.status_code == 200:
                tokens[user_ctx["key"]] = response.json()["access_token"]

        # sold curent (după istoric) pentru scenariul "drain"
        drain_ctx = scenario_users["scenario-drain"]
        account = await db_accounts.accounts.find_one({"_id": ObjectId(drain_ctx["account_id"])})
        drain_ctx["_live_balance_minor"] = account["balance_minor"]

        fresh_dest_1 = await create_pseudo_account(db_accounts, "fraud-sim-fresh-1", "Beneficiar Nou 1", now)
        fresh_dest_2 = await create_pseudo_account(db_accounts, "fraud-sim-fresh-2", "Beneficiar Nou 2", now)
        fresh_dest_3 = await create_pseudo_account(db_accounts, "fraud-sim-fresh-3", "Beneficiar Nou 3", now)
        fresh_dest_4 = await create_pseudo_account(db_accounts, "fraud-sim-fresh-4", "Beneficiar Nou 4", now)
        fresh_dest_5 = await create_pseudo_account(db_accounts, "fraud-sim-fresh-5", "Beneficiar Nou 5", now)
        fresh_dest_6 = await create_pseudo_account(db_accounts, "fraud-sim-fresh-6", "Beneficiar Nou 6", now)

        scenario_results.append(await scenario_drain(http_client, tokens, drain_ctx, fresh_dest_1))
        scenario_results.append(
            await scenario_velocity_burst(http_client, tokens, scenario_users["scenario-velocity"], [fresh_dest_2, fresh_dest_3, fresh_dest_4, fresh_dest_5, fresh_dest_6, fresh_dest_1])
        )
        scenario_results.append(await scenario_escalating(http_client, tokens, scenario_users["scenario-escalating"], fresh_dest_2))
        scenario_results.append(await scenario_new_category(http_client, tokens, scenario_users["scenario-newcat"], fresh_dest_3))
        scenario_results.append(await scenario_dormant(http_client, tokens, scenario_users["scenario-dormant"], fresh_dest_4))
        scenario_results.append(
            await scenario_structuring(http_client, tokens, scenario_users["scenario-structuring"], [fresh_dest_1, fresh_dest_2, fresh_dest_3])
        )
        scenario_results.append(await scenario_passthrough(http_client, tokens, passthrough_ctx, fresh_dest_5))
        scenario_results.append(await scenario_mule_sender(http_client, tokens, scenario_users["scenario-mulesender"], mule_target_ctx))

        shadow_report = None
        try:
            report_response = await http_client.get("http://transactions-service:8000/internal/fraud/shadow-report")
            shadow_report = report_response.json()
        except httpx.RequestError as exc:
            print(f"AVERTISMENT: nu am putut citi shadow-report-ul: {exc}")

    return {
        "client_mongo": client_mongo,
        "db_tx": db_tx,
        "baseline_count": len(baseline_users),
        "scenario_results": scenario_results,
        "shadow_report": shadow_report,
    }


async def print_final_report(db_tx, scenario_results: list[dict], shadow_report: dict | None, baseline_count: int) -> None:
    print("\n" + "=" * 70)
    print("RAPORT FINAL — SEED SCENARII FRAUD (Faza 1, shadow mode)")
    print("=" * 70)
    print(f"\nUseri baseline: {baseline_count}")
    print(f"Scenarii declanșate live: {len(scenario_results)}")

    print("\n--- Scenarii: ce s-a declanșat REAL (citit din tx_db.fraud_evaluations) ---")
    for result in scenario_results:
        trigger = result["trigger"]
        status_code = trigger["status_code"]
        body = trigger["body"]
        print(f"\n{result['scenario']} ({result['key']})")
        print(f"  HTTP transfer declanșator: {status_code}")
        if status_code != 201:
            print(f"  EȘUAT: {body}")
            continue
        tx_id = body.get("id")
        evaluation = await db_tx.fraud_evaluations.find_one({"transaction_id": ObjectId(tx_id)}) if tx_id else None
        if not evaluation:
            print("  Nicio evaluare fraud găsită (neașteptat).")
            continue
        fired = ", ".join(r["rule_id"] for r in evaluation["fired_rules"]) or "(niciuna)"
        print(f"  Scor: {evaluation['score']} -> {evaluation['decision_would_apply']}")
        print(f"  Reguli declanșate: {fired}")

    if shadow_report:
        print("\n--- Shadow report agregat (GET /internal/fraud/shadow-report) ---")
        print(f"  Total evaluări: {shadow_report['total_evaluations']}")
        print(f"  Pe status: {shadow_report['by_status']}")
        print(f"  Pe bandă de decizie: {shadow_report['by_decision_band']}")
        print(f"  Histogramă scor: {shadow_report['score_histogram']}")
        print("  Rată declanșare per regulă:")
        for rule_id, stats in sorted(shadow_report["rule_fire_counts"].items()):
            marker = " (exclusă din scor)" if stats["excluded_from_score"] else ""
            print(f"    {rule_id}: {stats['fire_count']}{marker}")

    print("\n" + "=" * 70)


async def main() -> None:
    _require_development_environment()
    demo_password = _require_demo_password()
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000")

    print("Seed scenarii fraud MaestroBank (idempotent — recreează DOAR datele fraud-sim)...")

    seed_result = await seed(mongo_url, demo_password, gateway_url)
    await print_final_report(seed_result["db_tx"], seed_result["scenario_results"], seed_result["shadow_report"], seed_result["baseline_count"])

    seed_result["client_mongo"].close()


if __name__ == "__main__":
    asyncio.run(main())
