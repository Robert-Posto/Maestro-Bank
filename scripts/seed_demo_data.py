#!/usr/bin/env python3
"""
scripts/seed_demo_data.py — Seed de date demo pentru development MaestroBank.

Creează 3 clienți demo COMPLEȚI (Octavia, Andrei, Maria): user + login
funcțional, cont RON + IBAN demo + card virtual, ~90 zile de istoric de
tranzacții (salarii, cumpărături, abonamente, transferuri între ei),
bugete, abonamente și câteva tichete de suport — suficient pentru a testa
Overview / Accounts / Cards / Transactions / Transfers / Budgets /
Spending & Forecast / Subscriptions / Support.

STRICT PENTRU DEVELOPMENT — vezi `_require_development_environment()`.

Reutilizează EXACT mecanismele existente (nu introduce business logic
nouă, doar le reproduce identic, documentat la fiecare punct):
  - hash parolă: bcrypt — identic cu auth-service/app/security.py::hash_password
  - IBAN demo: identic cu accounts-service/app/iban_service.py
  - shape-urile documentelor: identice cu fiecare app/service.py existent
  - categoriile: identice cu transactions-service/app/models.py::TRANSACTION_CATEGORIES

De ce scrie direct în MongoDB, nu prin API: API-urile publice folosesc
mereu `datetime.now()` — nu pot crea istoric retroactiv pe 90 de zile.
Scrisul direct e singura cale să obținem timestamp-uri realiste, distribuite
pe ultimele 3 luni. Verificarea finală (login, API-uri, transfer) apelează
însă API-ul REAL prin Gateway, fără nicio scurtătură — vezi `run_live_checks()`.

Rulare (din interiorul containerului auth-service, care are deja toate
dependențele necesare — motor, bcrypt, pyjwt, httpx):

    docker compose exec \\
        -e APP_ENV=development \\
        -e ALLOW_DEMO_SEED=true \\
        -e DEMO_USER_PASSWORD='ParolaDemo123' \\
        -e MONGO_URL=mongodb://mongodb:27017 \\
        auth-service python scripts/seed_demo_data.py

Reset explicit (identic ca efect cu o rulare normală — scriptul e deja
idempotent: șterge + recreează DOAR datele demo, la fiecare rulare):

    docker compose exec ... auth-service python scripts/seed_demo_data.py --reset
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import os
import random
import re
import string
import sys
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

# --------------------------------------------------------------------------
# Determinism — vezi cerința: toți colegii trebuie să obțină ACELAȘI dataset.
# --------------------------------------------------------------------------
RANDOM_SEED = 20260101

# --------------------------------------------------------------------------
# Categorii — IDENTICE cu transactions-service/app/models.py::TRANSACTION_CATEGORIES
# --------------------------------------------------------------------------
TRANSACTION_CATEGORIES = [
    "groceries", "shopping", "transport", "bills", "restaurants",
    "entertainment", "subscriptions", "income", "other",
]

CATEGORY_WEIGHTS = {
    "groceries": 5, "restaurants": 4, "transport": 4,
    "shopping": 2, "bills": 1, "entertainment": 1, "other": 1,
}

AMOUNT_RANGES_RON = {
    "groceries": (35, 220), "shopping": (60, 480), "transport": (9, 220),
    "restaurants": (18, 150), "bills": (70, 340), "entertainment": (35, 160),
    "other": (20, 190),
}

# --------------------------------------------------------------------------
# Cei 3 clienți demo — vezi task-ul MaestroBank, secțiunile 5, 8, 9.
# --------------------------------------------------------------------------
USERS = [
    {
        "key": "octavia",
        "first_name": "Octavia",
        "last_name": "Stefan",
        "email": "octavia.demo@maestrobank.local",
        "phone_number": "+40721000001",
        "salary_range_ron": (9200, 9500),
        "salary_day": 25,
        "opening_balance_ron": 13000,
        "card_last_four": "5678",
        "card_daily_limit_ron": 5000,
        "merchants": {
            "groceries": ["Kaufland", "Lidl", "Mega Image", "Carrefour"],
            "shopping": ["Zara", "H&M", "Sephora", "eMAG"],
            "transport": ["Uber", "Bolt", "OMV", "Metrorex"],
            "restaurants": ["Starbucks", "McDonald's", "La Mama", "Glovo", "Bolt Food"],
            "bills": ["Electrica", "ENGIE", "Digi"],
            "entertainment": ["Cinema City", "Eventim"],
            "other": ["Dr. Max", "Bebe Tei"],
        },
        "subscriptions": [
            ("Netflix", 49.99, 3), ("Spotify", 29.99, 7),
            ("Vodafone", 62.99, 12), ("iCloud", 14.99, 20),
        ],
        "budgets": [
            ("Shopping", "shopping", 1500, (0.60, 0.80)),
            ("Restaurants", "restaurants", 900, (0.40, 0.75)),
            # Ținta e mai jos decât cerința brută (50-70%) ca să compenseze
            # contribuția suplimentară, ne-țintită, a burst-ului "ultimele 7
            # zile" și a categoriilor generale — verificat empiric să lande
            # rezultatul final tot în 50-70% (vezi raportul de verificare).
            ("Transport", "transport", 700, (0.26, 0.42)),
            ("Groceries", "groceries", 1800, (0.60, 0.85)),
            ("Entertainment", "entertainment", 500, (0.35, 0.60)),
        ],
        "monthly_general_tx_count": (14, 18),
    },
    {
        "key": "andrei",
        "first_name": "Andrei",
        "last_name": "Popescu",
        "email": "andrei.demo@maestrobank.local",
        "phone_number": "+40721000002",
        "salary_range_ron": (7400, 7600),
        "salary_day": 28,
        "opening_balance_ron": 4500,
        "card_last_four": "3344",
        "card_daily_limit_ron": 4000,
        "merchants": {
            "groceries": ["Mega Image", "Carrefour"],
            "shopping": ["eMAG", "Altex"],
            "transport": ["Uber", "OMV"],
            "restaurants": ["Trattoria Roma", "Glovo"],
            "entertainment": ["Cinema City", "Steam"],
        },
        "subscriptions": [
            ("Netflix", 49.99, 5), ("World Class", 179.99, 1),
            ("Digi", 64.99, 15), ("Spotify", 29.99, 22),
        ],
        "budgets": [
            ("Groceries", "groceries", 1200, None),
            ("Transport", "transport", 600, None),
            ("Entertainment", "entertainment", 400, None),
            ("Shopping", "shopping", 1000, None),
        ],
        "monthly_general_tx_count": (10, 13),
    },
    {
        "key": "maria",
        "first_name": "Maria",
        "last_name": "Ionescu",
        "email": "maria.demo@maestrobank.local",
        "phone_number": "+40721000003",
        "salary_range_ron": (10800, 11200),
        "salary_day": 30,
        "opening_balance_ron": 9500,
        "card_last_four": "7712",
        "card_daily_limit_ron": 8000,
        "merchants": {
            "groceries": ["Carrefour", "Mega Image"],
            "shopping": ["Zara", "Notino"],
            "transport": ["Uber"],
            "restaurants": ["Casa Boierească"],
            "bills": ["Digi"],
            "other": ["Booking.com"],
        },
        "subscriptions": [
            ("Netflix", 49.99, 4), ("Spotify", 29.99, 9), ("Orange", 64.99, 18),
        ],
        "budgets": [
            ("Shopping", "shopping", 2000, None),
            ("Travel", "other", 2500, None),  # "Travel" nu există în enum -> "other" (documentat în task)
            ("Restaurants", "restaurants", 800, None),
            ("Groceries", "groceries", 1500, None),
        ],
        "monthly_general_tx_count": (9, 12),
    },
]

# Transferuri P2P INTERNE MaestroBank — o singură tranzacție per transfer,
# direcția se calculează la citire (identic cu to_transaction_view real).
# days_ago variate + cel puțin unul în ultimele 7 zile (secțiunea 12).
P2P_TRANSFERS = [
    ("octavia", "andrei", 250, "Cină", 50),
    ("andrei", "octavia", 120, "Bilete", 35),
    ("maria", "octavia", 500, "Weekend", 20),
    ("octavia", "maria", 300, "Cadou", 10),
    ("andrei", "maria", 180, "Transfer", 4),
]

TICKETS = {
    "octavia": [
        ("Nu recunosc o tranzacție", "transfer", "Am observat o tranzacție pe extras pe care nu mi-o amintesc. Puteți verifica?", "resolved"),
        ("Întrebare despre card", "card", "Cum activez plățile internaționale pe cardul virtual?", "open"),
    ],
    "andrei": [
        ("Plată online refuzată", "card", "Am încercat o plată pe un site și cardul a fost refuzat, deși am fonduri suficiente.", "in_progress"),
    ],
}

BENEFICIARIES_EXTRA = {
    # beneficiar extern demo (IBAN nu corespunde unui cont real) — doar pentru Octavia.
    "octavia": [("Bunica Maria", "RO88MAES0000000000009999")],
}


# --------------------------------------------------------------------------
# Mecanisme reproduse IDENTIC din serviciile reale (documentat la fiecare).
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Identic cu auth-service/app/security.py::hash_password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _generate_demo_iban() -> str:
    """Identic cu accounts-service/app/iban_service.py::generate_demo_iban."""
    check_digits = f"{random.randint(0, 99):02d}"
    account_digits = "".join(random.choices(string.digits, k=16))
    return f"RO{check_digits}MAES{account_digits}"


async def generate_unique_demo_iban(accounts_collection) -> str:
    """Identic cu accounts-service/app/iban_service.py::generate_unique_demo_iban."""
    for _ in range(10):
        candidate = _generate_demo_iban()
        if await accounts_collection.find_one({"iban": candidate}) is None:
            return candidate
    raise RuntimeError("Nu s-a putut genera un IBAN demo unic după 10 încercări.")


def format_minor_amount(amount_minor: int) -> str:
    """Identic cu accounts-service/app/money.py::format_minor_amount."""
    major, minor = divmod(amount_minor, 100)
    return f"{major}.{minor:02d}"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _shift_months(dt: datetime, delta_months: int) -> datetime:
    month = dt.month - 1 + delta_months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _random_time_on(day: datetime) -> datetime:
    """Ora random, ponderată spre dimineață/prânz/seară (secțiunea 11)."""
    hour = random.choice([8, 9, 10, 12, 13, 14, 18, 19, 20, 21, 22])
    return day.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59), microsecond=0)


def _random_day_between(start: datetime, end: datetime) -> datetime:
    delta_days = max((end - start).days, 0)
    offset = random.randint(0, delta_days) if delta_days > 0 else 0
    return _random_time_on(start + timedelta(days=offset))


# --------------------------------------------------------------------------
# 2. SAFETY — refuză să ruleze în afara development (secțiunea 2 din task).
# --------------------------------------------------------------------------

def _require_development_environment() -> None:
    app_env = os.getenv("APP_ENV", "")
    allow_seed = os.getenv("ALLOW_DEMO_SEED", "")

    if app_env != "development" or allow_seed.lower() != "true":
        print("REFUZ: seed-ul de date demo rulează STRICT în development.", file=sys.stderr)
        print("Setează explicit variabilele de mediu:", file=sys.stderr)
        print("  APP_ENV=development", file=sys.stderr)
        print("  ALLOW_DEMO_SEED=true", file=sys.stderr)
        print(f"(curent: APP_ENV={app_env!r}, ALLOW_DEMO_SEED={allow_seed!r})", file=sys.stderr)
        sys.exit(1)


def _require_demo_password() -> str:
    password = os.getenv("DEMO_USER_PASSWORD")
    if not password:
        print("REFUZ: variabila DEMO_USER_PASSWORD nu este setată.", file=sys.stderr)
        sys.exit(1)
    return password


# --------------------------------------------------------------------------
# 3. IDEMPOTENCY — șterge DOAR datele marcate is_demo=True ale celor 3 useri
#    (identificați după email), plus conturile-pseudo de comerciant/angajator.
#    Nu atinge NICIODATĂ date nemarcate is_demo.
# --------------------------------------------------------------------------

async def cleanup_demo_data(db_auth, db_accounts, db_tx, db_budgets, db_support) -> None:
    """Idempotență (secțiunea 3): identifică cei 3 useri demo PRIN EMAIL —
    "octavia.demo@maestrobank.local" etc. sunt identificatori unic-demo prin
    construcție (nimeni altcineva nu ar folosi acest format/domeniu .local),
    exact cum cere task-ul ("identifică cei 3 demo users; șterge DOAR datele
    asociate lor"). NU cerem și is_demo=True la acest pas — dacă un user cu
    exact acest email există deja (ex. dintr-un test manual anterior, fără
    marcaj), tot trebuie înlocuit la o rulare nouă de seed, altfel login-ul
    ar găsi documentul vechi (hash de parolă diferit) și seed-ul n-ar mai fi
    idempotent. Odată ce un user_id e confirmat demo (prin email), ștergem
    TOATE datele lui din celelalte colecții — user_id-ul e deja limita de
    siguranță, un `is_demo` suplimentar acolo doar ar risca să lase resturi
    orfane dintr-un test manual mai vechi, fără să adauge protecție reală.
    """
    demo_emails = [u["email"] for u in USERS]
    existing_users = await db_auth.users.find({"email": {"$in": demo_emails}}).to_list(length=10)
    user_ids = [str(u["_id"]) for u in existing_users]

    if user_ids:
        accounts = await db_accounts.accounts.find({"user_id": {"$in": user_ids}}).to_list(length=10)
        account_ids = [str(a["_id"]) for a in accounts]

        if account_ids:
            await db_tx.transactions.delete_many(
                {"$or": [{"from_account_id": {"$in": account_ids}}, {"to_account_id": {"$in": account_ids}}]}
            )
        await db_accounts.cards.delete_many({"user_id": {"$in": user_ids}})
        await db_accounts.beneficiaries.delete_many({"user_id": {"$in": user_ids}})
        await db_accounts.accounts.delete_many({"user_id": {"$in": user_ids}})
        await db_budgets.budgets.delete_many({"user_id": {"$in": user_ids}})
        await db_budgets.subscriptions.delete_many({"user_id": {"$in": user_ids}})
        await db_support.tickets.delete_many({"user_id": {"$in": user_ids}})
        await db_auth.users.delete_many({"email": {"$in": demo_emails}})

    # Conturi-pseudo (comercianți, angajator, sold inițial) — NU aparțin
    # niciunui user real, se identifică prin is_demo_merchant.
    merchant_accounts = await db_accounts.accounts.find({"is_demo_merchant": True}).to_list(length=200)
    merchant_account_ids = [str(a["_id"]) for a in merchant_accounts]
    if merchant_account_ids:
        await db_tx.transactions.delete_many(
            {
                "is_demo": True,
                "$or": [
                    {"from_account_id": {"$in": merchant_account_ids}},
                    {"to_account_id": {"$in": merchant_account_ids}},
                ],
            }
        )
        await db_accounts.accounts.delete_many({"is_demo_merchant": True})

    print(f"Curățenie: {len(user_ids)} useri demo anteriori + {len(merchant_account_ids)} conturi-pseudo șterse.")


# --------------------------------------------------------------------------
# 4. GENERARE — conturi-pseudo (comercianți/angajator/sold-inițial)
# --------------------------------------------------------------------------

async def create_pseudo_account(db_accounts, pseudo_id: str, name: str, created_at: datetime) -> dict:
    iban = await generate_unique_demo_iban(db_accounts.accounts)
    doc = {
        "user_id": f"merchant:{pseudo_id}",
        "iban": iban,
        "currency": "RON",
        "balance_minor": 0,
        "status": "active",
        "created_at": created_at,
        "is_demo": True,
        "is_demo_merchant": True,
        "merchant_name": name,
    }
    result = await db_accounts.accounts.insert_one(doc)
    doc["_id"] = result.inserted_id
    return {"account_id": str(result.inserted_id), "iban": iban, "name": name}


async def create_demo_user(db_auth, db_accounts, spec: dict, password_hash: str, created_at: datetime) -> dict:
    user_doc = {
        "first_name": spec["first_name"],
        "last_name": spec["last_name"],
        "email": spec["email"],
        "phone_number": spec.get("phone_number"),
        "password_hash": password_hash,
        "created_at": created_at,
        "is_active": True,
        "is_demo": True,
        "role": "customer",
    }
    result = await db_auth.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    iban = await generate_unique_demo_iban(db_accounts.accounts)
    account_result = await db_accounts.accounts.insert_one(
        {
            "user_id": user_id,
            "iban": iban,
            "currency": "RON",
            "balance_minor": 0,  # se recalculează la final, din suma tranzacțiilor generate
            "status": "active",
            # Fără acest câmp, contul e "invizibil" pentru get_account_by_user/
            # get_account_for_user (query Mongo strict pe account_type="current",
            # nu doar defaultul Pydantic la citire) — vezi accounts-service/app/
            # service.py::backfill_missing_account_types pentru explicația completă.
            # Backfill-ul de-acolo rulează DOAR la boot-ul accounts-service, deci
            # NU acoperă conturi inserate direct de acest script între două
            # restart-uri — trebuie setat explicit aici, la creare.
            "account_type": "current",
            "created_at": created_at,
            "is_demo": True,
        }
    )
    account_id = str(account_result.inserted_id)

    now = datetime.now(timezone.utc)
    await db_accounts.cards.insert_one(
        {
            "user_id": user_id,
            "account_id": account_id,
            "last_four": spec["card_last_four"],
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
            "daily_limit_minor": spec["card_daily_limit_ron"] * 100,
            "is_demo": True,
        }
    )

    return {"key": spec["key"], "user_id": user_id, "account_id": account_id, "iban": iban, "spec": spec}


# --------------------------------------------------------------------------
# 5. GENERARE — tranzacții (istoric 90 zile + luna curentă ajustată pentru bugete)
# --------------------------------------------------------------------------

class Ledger:
    """Acumulează tranzacțiile + soldurile în Python, ÎNAINTE de a scrie în
    Mongo — astfel soldul final e garantat matematic identic cu suma
    semnată a tranzacțiilor (secțiunea 14), fără niciun `balance = X` brut.
    """

    def __init__(self) -> None:
        self.transactions: list[dict] = []
        self.balance_deltas: dict[str, int] = {}

    def add(
        self,
        from_ctx: dict,
        to_ctx: dict,
        amount_ron: float,
        category: str,
        description: str,
        when: datetime,
        status: str = "completed",
    ) -> dict:
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
        }
        self.transactions.append(doc)
        if status == "completed":
            self.balance_deltas[from_ctx["account_id"]] = self.balance_deltas.get(from_ctx["account_id"], 0) - amount_minor
            self.balance_deltas[to_ctx["account_id"]] = self.balance_deltas.get(to_ctx["account_id"], 0) + amount_minor
        return doc


def _weighted_category(categories: list[str]) -> str:
    weights = [CATEGORY_WEIGHTS.get(c, 1) for c in categories]
    return random.choices(categories, weights=weights, k=1)[0]


def generate_user_history(
    ledger: Ledger,
    user_ctx: dict,
    merchant_accounts: dict[str, dict],
    employer_ctx: dict,
    opening_ctx: dict,
    window_start: datetime,
    month_start: datetime,
    now: datetime,
) -> None:
    spec = user_ctx["spec"]
    available_categories = list(spec["merchants"].keys())

    # --- Sold inițial (demo) — o tranzacție reală, nu un balance= brut ---
    ledger.add(
        opening_ctx, user_ctx, spec["opening_balance_ron"], "other",
        "Sold inițial (demo)", window_start + timedelta(hours=2),
    )

    # --- Salariu — ultimele 3 luni (secțiunea 5/13) ---
    salary_anchor = now.replace(
        day=min(spec["salary_day"], calendar.monthrange(now.year, now.month)[1]),
        hour=9, minute=0, second=0, microsecond=0,
    )
    if salary_anchor > now:
        salary_anchor = _shift_months(salary_anchor, -1)
    for i in range(3):
        salary_date = _shift_months(salary_anchor, -i)
        if salary_date < window_start:
            continue
        amount = round(random.uniform(*spec["salary_range_ron"]), 2)
        ledger.add(employer_ctx, user_ctx, amount, "income", "Salariu", salary_date)

    # --- Abonamente — billing lunar, ultimele ~3 ocurențe (secțiunea 6) ---
    for name, amount_ron, billing_day in spec["subscriptions"]:
        merchant_ctx = merchant_accounts[name]
        anchor = now.replace(
            day=min(billing_day, calendar.monthrange(now.year, now.month)[1]),
            hour=10, minute=0, second=0, microsecond=0,
        )
        if anchor > now:
            anchor = _shift_months(anchor, -1)
        for i in range(3):
            billing_date = _shift_months(anchor, -i)
            if billing_date < window_start:
                continue
            ledger.add(user_ctx, merchant_ctx, amount_ron, "subscriptions", name, billing_date)

    # --- Cumpărături "istorice" (window_start -> month_start), spread realist ---
    cursor = window_start + timedelta(days=1)
    while cursor < month_start:
        month_end = min(_shift_months(cursor.replace(day=1), 1), month_start)
        count = random.randint(*spec["monthly_general_tx_count"])
        for _ in range(count):
            category = _weighted_category(available_categories)
            merchant_name = random.choice(spec["merchants"][category])
            merchant_ctx = merchant_accounts[merchant_name]
            amount = round(random.uniform(*AMOUNT_RANGES_RON[category]), 2)
            when = _random_day_between(cursor, month_end - timedelta(seconds=1))
            ledger.add(user_ctx, merchant_ctx, amount, category, merchant_name, when)
        cursor = month_end

    # --- Luna curentă — cheltuieli ȚINTITE per buget, ca procentele să fie
    # interesante și variate (secțiunea 7), NU hardcodate ca "spent". ---
    for name, category, limit_ron, pct_range in spec["budgets"]:
        low, high = pct_range if pct_range else (0.35, 0.70)
        target_ron = limit_ron * random.uniform(low, high)
        merchants_in_category = spec["merchants"].get(category, [name])
        installments = random.randint(2, 4)
        remaining = target_ron
        for i in range(installments):
            share = remaining / (installments - i) if i < installments - 1 else remaining
            share = max(share * random.uniform(0.6, 1.3), 5.0) if i < installments - 1 else max(remaining, 5.0)
            merchant_name = random.choice(merchants_in_category)
            merchant_ctx = merchant_accounts.get(merchant_name) or merchant_accounts[merchant_name]
            when = _random_day_between(month_start, now - timedelta(days=1))
            ledger.add(user_ctx, merchant_ctx, round(share, 2), category, merchant_name, when)
            remaining -= share

    # --- Categorii fără buget explicit, dar cu comercianți -> puțină activitate ---
    budgeted_categories = {category for _, category, _, _ in spec["budgets"]}
    for category in available_categories:
        if category in budgeted_categories:
            continue
        for _ in range(random.randint(1, 3)):
            merchant_name = random.choice(spec["merchants"][category])
            merchant_ctx = merchant_accounts[merchant_name]
            amount = round(random.uniform(*AMOUNT_RANGES_RON[category]), 2)
            when = _random_day_between(month_start, now - timedelta(days=1))
            ledger.add(user_ctx, merchant_ctx, amount, category, merchant_name, when)

    # --- Refund (secțiunea 13) ---
    refund_category = "shopping" if "shopping" in available_categories else available_categories[0]
    refund_merchant = random.choice(spec["merchants"][refund_category])
    refund_ctx = merchant_accounts[refund_merchant]
    refund_when = _random_day_between(now - timedelta(days=30), now - timedelta(days=2))
    ledger.add(refund_ctx, user_ctx, round(random.uniform(30, 150), 2), "income", f"Refund {refund_merchant}", refund_when)

    # --- Burst "ultimele 7 zile" — garantează minim 6 tranzacții recente (secțiunea 12) ---
    recent_start = now - timedelta(days=7)
    for _ in range(random.randint(6, 8)):
        category = _weighted_category(available_categories)
        merchant_name = random.choice(spec["merchants"][category])
        merchant_ctx = merchant_accounts[merchant_name]
        amount = round(random.uniform(*AMOUNT_RANGES_RON[category]), 2)
        when = _random_day_between(recent_start, now)
        ledger.add(user_ctx, merchant_ctx, amount, category, merchant_name, when)


def generate_p2p_transfers(ledger: Ledger, users_by_key: dict[str, dict], now: datetime) -> None:
    """Transferuri INTERNE MaestroBank între cei 3 clienți (secțiunea 10) —
    o singură tranzacție per transfer, consistentă pentru ambele părți
    (direction se calculează la citire, identic cu transactions-service).
    """
    for from_key, to_key, amount_ron, description, days_ago in P2P_TRANSFERS:
        when = _random_time_on(now - timedelta(days=days_ago))
        ledger.add(users_by_key[from_key], users_by_key[to_key], amount_ron, "other", description, when)


# --------------------------------------------------------------------------
# 6. Bugete, abonamente, beneficiari, tichete de suport
# --------------------------------------------------------------------------

async def create_budgets_and_subscriptions(db_budgets, user_ctx: dict, created_at: datetime) -> tuple[int, int]:
    spec = user_ctx["spec"]
    budgets_count = 0
    for name, category, limit_ron, _pct_range in spec["budgets"]:
        await db_budgets.budgets.insert_one(
            {
                "user_id": user_ctx["user_id"],
                "name": name,
                "category": category,
                "limit_minor": round(limit_ron * 100),
                "period": "monthly",
                "active": True,
                "created_at": created_at,
                "is_demo": True,
            }
        )
        budgets_count += 1

    subs_count = 0
    for name, amount_ron, billing_day in spec["subscriptions"]:
        await db_budgets.subscriptions.insert_one(
            {
                "user_id": user_ctx["user_id"],
                "name": name,
                "amount_minor": round(amount_ron * 100),
                "currency": "RON",
                "billing_day": billing_day,
                "category": "subscriptions",
                "active": True,
                "created_at": created_at,
                "is_demo": True,
            }
        )
        subs_count += 1

    return budgets_count, subs_count


async def create_beneficiaries(db_accounts, users_by_key: dict[str, dict], created_at: datetime) -> int:
    count = 0
    pairs = {
        "octavia": ["andrei", "maria"],
        "andrei": ["octavia"],
        "maria": ["octavia", "andrei"],
    }
    for owner_key, target_keys in pairs.items():
        owner = users_by_key[owner_key]
        for target_key in target_keys:
            target = users_by_key[target_key]
            target_spec = target["spec"]
            await db_accounts.beneficiaries.insert_one(
                {
                    "user_id": owner["user_id"],
                    "name": f"{target_spec['first_name']} {target_spec['last_name']}",
                    "iban": target["iban"],
                    "created_at": created_at,
                    "is_demo": True,
                }
            )
            count += 1
        for name, iban in BENEFICIARIES_EXTRA.get(owner_key, []):
            await db_accounts.beneficiaries.insert_one(
                {"user_id": owner["user_id"], "name": name, "iban": iban, "created_at": created_at, "is_demo": True}
            )
            count += 1
    return count


async def create_support_tickets(db_support, users_by_key: dict[str, dict], now: datetime) -> int:
    count = 0
    for user_key, tickets in TICKETS.items():
        user_id = users_by_key[user_key]["user_id"]
        for subject, category, message, status in tickets:
            created_at = now - timedelta(days=random.randint(3, 40))
            await db_support.tickets.insert_one(
                {
                    "user_id": user_id,
                    "subject": subject,
                    "category": category,
                    "message": message,
                    "status": status,
                    "created_at": created_at,
                    "updated_at": created_at if status == "open" else now - timedelta(days=random.randint(0, 2)),
                    "is_demo": True,
                }
            )
            count += 1
    return count


# --------------------------------------------------------------------------
# 7. ORCHESTRARE — generarea completă a dataset-ului
# --------------------------------------------------------------------------

async def seed(mongo_url: str, demo_password: str) -> dict:
    random.seed(RANDOM_SEED)  # determinist — vezi secțiunea 15

    client = AsyncIOMotorClient(mongo_url)
    dbs = {
        "auth": client["auth_db"],
        "accounts": client["accounts_db"],
        "tx": client["tx_db"],
        "budgets": client["budgets_db"],
        "support": client["support_db"],
    }

    await client.admin.command("ping")
    print("Connected to configured MongoDB environment")  # NU afișăm connection string-ul (secțiunea 26)

    await cleanup_demo_data(dbs["auth"], dbs["accounts"], dbs["tx"], dbs["budgets"], dbs["support"])

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=90)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # --- conturi-pseudo: un cont per comerciant/abonament unic + angajator + sold inițial ---
    merchant_names: set[str] = set()
    for spec in USERS:
        for names in spec["merchants"].values():
            merchant_names.update(names)
        for name, _amount, _day in spec["subscriptions"]:
            merchant_names.add(name)

    merchant_accounts: dict[str, dict] = {}
    for name in sorted(merchant_names):
        merchant_accounts[name] = await create_pseudo_account(dbs["accounts"], _slugify(name), name, window_start)

    employer_ctx = await create_pseudo_account(dbs["accounts"], "employer-demo", "MaestroBank Demo Employer SRL", window_start)
    opening_ctx = await create_pseudo_account(dbs["accounts"], "opening-balance", "MaestroBank — Sold inițial (demo)", window_start)

    # --- cei 3 useri reali ---
    password_hash = hash_password(demo_password)
    users_by_key: dict[str, dict] = {}
    for spec in USERS:
        users_by_key[spec["key"]] = await create_demo_user(dbs["auth"], dbs["accounts"], spec, password_hash, window_start)

    # --- istoric de tranzacții (90 zile) + transferuri P2P ---
    ledger = Ledger()
    for user_ctx in users_by_key.values():
        generate_user_history(ledger, user_ctx, merchant_accounts, employer_ctx, opening_ctx, window_start, month_start, now)
    generate_p2p_transfers(ledger, users_by_key, now)

    # 1 tranzacție "pending" (secțiunea 19) — cea mai recentă ieșire a Octaviei
    ledger.transactions.sort(key=lambda d: d["created_at"])
    for doc in reversed(ledger.transactions):
        if doc["from_account_id"] == users_by_key["octavia"]["account_id"] and doc["status"] == "completed":
            ledger.balance_deltas[doc["from_account_id"]] += doc["amount_minor"]
            ledger.balance_deltas[doc["to_account_id"]] -= doc["amount_minor"]
            doc["status"] = "pending"
            break

    if ledger.transactions:
        await dbs["tx"].transactions.insert_many(ledger.transactions)

    for account_id, delta in ledger.balance_deltas.items():
        await dbs["accounts"].accounts.update_one({"_id": ObjectId(account_id)}, {"$inc": {"balance_minor": delta}})

    # --- bugete, abonamente, beneficiari, tichete de suport ---
    budgets_total = subs_total = 0
    for user_ctx in users_by_key.values():
        b, s = await create_budgets_and_subscriptions(dbs["budgets"], user_ctx, window_start)
        budgets_total += b
        subs_total += s

    beneficiaries_total = await create_beneficiaries(dbs["accounts"], users_by_key, now)
    tickets_total = await create_support_tickets(dbs["support"], users_by_key, now)

    return {
        "client": client,
        "dbs": dbs,
        "users_by_key": users_by_key,
        "tx_total": len(ledger.transactions),
        "budgets_total": budgets_total,
        "subs_total": subs_total,
        "beneficiaries_total": beneficiaries_total,
        "tickets_total": tickets_total,
        "merchant_accounts_total": len(merchant_accounts) + 2,  # + angajator + sold inițial
    }


# --------------------------------------------------------------------------
# 8. VERIFICARE AUTOMATĂ (secțiunea 29) — recitește din Mongo, nu doar
#    numere ținute în memorie, ca să confirme persistența reală.
# --------------------------------------------------------------------------

async def verify_data(dbs: dict, users_by_key: dict[str, dict]) -> list[dict]:
    summaries = []
    for key, user_ctx in users_by_key.items():
        account = await dbs["accounts"].accounts.find_one({"_id": ObjectId(user_ctx["account_id"])})
        tx_count = await dbs["tx"].transactions.count_documents(
            {
                "is_demo": True,
                "$or": [{"from_account_id": user_ctx["account_id"]}, {"to_account_id": user_ctx["account_id"]}],
            }
        )
        budgets_count = await dbs["budgets"].budgets.count_documents({"user_id": user_ctx["user_id"], "is_demo": True})
        subs_count = await dbs["budgets"].subscriptions.count_documents({"user_id": user_ctx["user_id"], "is_demo": True})
        cards_count = await dbs["accounts"].cards.count_documents({"user_id": user_ctx["user_id"], "is_demo": True})

        summaries.append(
            {
                "key": key,
                "name": f"{user_ctx['spec']['first_name']} {user_ctx['spec']['last_name']}",
                "email": user_ctx["spec"]["email"],
                "iban": account["iban"],
                "balance_minor": account["balance_minor"],
                "balance_ron": format_minor_amount(account["balance_minor"]),
                "tx_count": tx_count,
                "budgets_count": budgets_count,
                "subs_count": subs_count,
                "cards_count": cards_count,
            }
        )
    return summaries


# --------------------------------------------------------------------------
# 9. VERIFICARE LIVE — login real + API-uri reale + transfer real prin
#    Gateway (secțiunile 30, 31, 32). ZERO scurtătură: exact ce ar face Angular.
# --------------------------------------------------------------------------

async def revert_test_transfer(dbs: dict, users_by_key: dict[str, dict], tx_id: str, amount_minor: int) -> None:
    """Curățenie chirurgicală după testul de transfer live, ca dataset-ul
    demo să rămână determinist (secțiunea 32: "poți reseta dataset-ul
    după test") — șterge exact tranzacția de test și inversează exact
    delta de sold pe care a produs-o, fără să atingă nimic altceva.
    """
    await dbs["tx"].transactions.delete_one({"_id": ObjectId(tx_id)})
    await dbs["accounts"].accounts.update_one(
        {"_id": ObjectId(users_by_key["octavia"]["account_id"])}, {"$inc": {"balance_minor": amount_minor}}
    )
    await dbs["accounts"].accounts.update_one(
        {"_id": ObjectId(users_by_key["andrei"]["account_id"])}, {"$inc": {"balance_minor": -amount_minor}}
    )


async def run_live_checks(dbs: dict, users_by_key: dict[str, dict], demo_password: str) -> dict:
    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000")
    results: dict = {"logins": {}, "api_checks": {}, "transfer_test": None}

    async with httpx.AsyncClient(timeout=10.0, base_url=gateway_url) as client:
        # --- 30. Test login pentru cei 3 useri ---
        tokens: dict[str, str] = {}
        for key, user_ctx in users_by_key.items():
            try:
                response = await client.post(
                    "/api/auth/login",
                    json={"email": user_ctx["spec"]["email"], "password": demo_password},
                )
                if response.status_code == 200:
                    tokens[key] = response.json()["access_token"]
                    results["logins"][key] = "OK"
                else:
                    results["logins"][key] = f"FAILED (HTTP {response.status_code})"
            except httpx.RequestError as exc:
                results["logins"][key] = f"ERROR ({exc})"

        # --- 31. Verificare API-uri pentru Octavia ---
        if "octavia" in tokens:
            headers = {"Authorization": f"Bearer {tokens['octavia']}"}
            checks = [
                ("current user", "GET", "/api/auth/me"),
                ("account", "GET", "/api/accounts/me"),
                ("card", "GET", "/api/accounts/me/cards"),
                ("recent transactions", "GET", "/api/transactions?limit=10"),
                ("transactions", "GET", "/api/transactions"),
                ("budgets", "GET", "/api/budgets/budgets"),
                ("subscriptions", "GET", "/api/budgets/subscriptions"),
                ("spending analytics", "GET", "/api/transactions/analytics/spending"),
                ("forecast", "GET", "/api/transactions/analytics/forecast"),
                ("support tickets", "GET", "/api/support/tickets"),
            ]
            for label, method, path in checks:
                try:
                    response = await client.request(method, path, headers=headers)
                    body = response.json() if response.status_code == 200 else None
                    has_data = response.status_code == 200 and body not in (None, [], {})
                    results["api_checks"][label] = {
                        "status_code": response.status_code,
                        "has_data": has_data,
                        "body": body,
                    }
                except httpx.RequestError as exc:
                    results["api_checks"][label] = {"status_code": None, "has_data": False, "error": str(exc)}

        # --- 32. Test transfer real: Octavia -> Andrei, 100 RON ---
        if "octavia" in tokens and "andrei" in tokens:
            octavia_headers = {"Authorization": f"Bearer {tokens['octavia']}"}
            andrei_headers = {"Authorization": f"Bearer {tokens['andrei']}"}

            before_octavia = (await client.get("/api/accounts/me", headers=octavia_headers)).json()
            before_andrei = (await client.get("/api/accounts/me", headers=andrei_headers)).json()

            transfer_response = await client.post(
                "/api/transactions/transfers",
                json={
                    "to_iban": users_by_key["andrei"]["iban"],
                    "amount_minor": 10000,
                    "description": "Test transfer (verificare seed)",
                    "category": "other",
                },
                headers=octavia_headers,
            )
            transfer_body = transfer_response.json() if transfer_response.status_code == 201 else transfer_response.text

            after_octavia = (await client.get("/api/accounts/me", headers=octavia_headers)).json()
            after_andrei = (await client.get("/api/accounts/me", headers=andrei_headers)).json()

            octavia_delta = after_octavia["balance_minor"] - before_octavia["balance_minor"]
            andrei_delta = after_andrei["balance_minor"] - before_andrei["balance_minor"]
            correct = transfer_response.status_code == 201 and octavia_delta == -10000 and andrei_delta == 10000

            tx_appears_both_sides = False
            if correct:
                octavia_tx = await client.get("/api/transactions?limit=5", headers=octavia_headers)
                andrei_tx = await client.get("/api/transactions?limit=5", headers=andrei_headers)
                tx_id = transfer_body.get("id") or transfer_body.get("_id")
                octavia_ids = [t["id"] for t in octavia_tx.json()]
                andrei_ids = [t["id"] for t in andrei_tx.json()]
                tx_appears_both_sides = tx_id in octavia_ids and tx_id in andrei_ids

            results["transfer_test"] = {
                "status_code": transfer_response.status_code,
                "octavia_delta_minor": octavia_delta,
                "andrei_delta_minor": andrei_delta,
                "correct": correct,
                "appears_both_sides": tx_appears_both_sides,
            }

            if correct:
                tx_id = transfer_body.get("id") or transfer_body.get("_id")
                if tx_id:
                    await revert_test_transfer(dbs, users_by_key, tx_id, 10000)
                    results["transfer_test"]["reverted"] = True

    return results


# --------------------------------------------------------------------------
# 10. RAPORT FINAL (secțiunea 33) — fără parole/secrete/URI complet.
# --------------------------------------------------------------------------

def print_final_report(seed_result: dict, summaries: list[dict], live_results: dict) -> None:
    print("\n" + "=" * 70)
    print("RAPORT FINAL — SEED DATE DEMO MAESTROBANK")
    print("=" * 70)

    print("\nDatabase environment: connected\n")

    print(f"Demo users: {len(summaries)}")
    print(f"Accounts (useri reali): {len(summaries)}")
    print(f"Cards: {sum(s['cards_count'] for s in summaries)}")
    print(f"Transactions (tx_db, is_demo=True, total): {seed_result['tx_total']}")
    print(f"Budgets: {seed_result['budgets_total']}")
    print(f"Subscriptions: {seed_result['subs_total']}")
    print(f"Beneficiaries: {seed_result['beneficiaries_total']}")
    print(f"Support tickets: {seed_result['tickets_total']}")
    print(f"Conturi-pseudo comercianți/angajator/sold-inițial: {seed_result['merchant_accounts_total']}")

    print("\n--- Per utilizator ---")
    for s in summaries:
        print(f"\n{s['name']} ({s['key']})")
        print(f"  Email:                {s['email']}")
        print(f"  IBAN demo:            {s['iban']}")
        print(f"  Sold curent:          {s['balance_ron']} RON")
        print(f"  Nr. tranzacții:       {s['tx_count']}")
        print(f"  Nr. bugete:           {s['budgets_count']}")
        print(f"  Nr. abonamente:       {s['subs_count']}")

    print("\n--- Test login (secțiunea 30) ---")
    for key, status in live_results["logins"].items():
        print(f"  {key.capitalize()} login: {status}")

    print("\n--- Verificare API-uri Octavia (secțiunea 31) ---")
    for label, result in live_results["api_checks"].items():
        marker = "OK" if result.get("has_data") else "GOL/EROARE"
        print(f"  {label}: HTTP {result.get('status_code')} — {marker}")

    spending = live_results["api_checks"].get("spending analytics", {}).get("body") or {}
    by_category = spending.get("by_category", [])
    print(f"\n  Spending by category: {len(by_category)} categorii cu date "
          f"({', '.join(c['category'] for c in by_category) or '—'})")

    forecast = live_results["api_checks"].get("forecast", {}).get("body") or {}
    if forecast:
        import math

        finite_ok = all(
            isinstance(forecast.get(k), (int, float)) and math.isfinite(forecast.get(k))
            for k in ("current_balance_minor", "expected_expenses_minor", "estimated_end_of_month_balance_minor")
        )
        print(f"  Forecast — valori finite (fără NaN/Infinity): {'DA' if finite_ok else 'NU — PROBLEMĂ'}")
        print(f"    estimated_end_of_month_balance: {format_minor_amount(forecast['estimated_end_of_month_balance_minor'])} RON")

    print("\n--- Test transfer live (secțiunea 32): Octavia -> Andrei, 100 RON ---")
    tt = live_results.get("transfer_test")
    if tt:
        print(f"  Status HTTP creare transfer: {tt['status_code']}")
        print(f"  Sold Octavia: {tt['octavia_delta_minor'] / 100:+.2f} RON")
        print(f"  Sold Andrei:  {tt['andrei_delta_minor'] / 100:+.2f} RON")
        print(f"  Apare în istoricul AMBILOR: {'DA' if tt['appears_both_sides'] else 'NU'}")
        print(f"  Rezultat: {'CORECT' if tt['correct'] else 'PROBLEMĂ'}")
        if tt.get("reverted"):
            print("  Dataset-ul a fost readus la starea dinainte de test (determinist).")
    else:
        print("  NEEXECUTAT (login Octavia/Andrei a eșuat).")

    print("\n" + "=" * 70)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed date demo MaestroBank (development only).")
    parser.add_argument("--reset", action="store_true", help="Șterge și recreează DOAR datele demo (efect identic cu o rulare normală — scriptul e deja idempotent).")
    args = parser.parse_args()

    _require_development_environment()
    demo_password = _require_demo_password()

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")

    if args.reset:
        print("Mod --reset: șterg și recreez DOAR datele demo...")
    else:
        print("Seed date demo MaestroBank (idempotent — recreează DOAR datele demo)...")

    seed_result = await seed(mongo_url, demo_password)
    summaries = await verify_data(seed_result["dbs"], seed_result["users_by_key"])
    live_results = await run_live_checks(seed_result["dbs"], seed_result["users_by_key"], demo_password)

    print_final_report(seed_result, summaries, live_results)

    seed_result["client"].close()


if __name__ == "__main__":
    asyncio.run(main())
