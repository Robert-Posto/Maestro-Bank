#!/usr/bin/env python3
"""
scripts/create_staff_user.py — Creează (idempotent) un cont de PERSONAL.

Motivul pentru care există un script separat, nu o rută API: role="staff"
nu poate fi cerut NICIODATĂ prin înregistrare publică (`UserRegister` nu
are câmp `role` — vezi auth-service/app/models.py) — e o decizie de design
deliberată, nu o omisiune. Singura cale prin care există un user
ne-auto-înregistrat în acest cod este deja scripts/seed_demo_data.py
(scriere directă în Mongo) — acest script urmează exact același precedent.

Spre deosebire de seed_demo_data.py::create_demo_user, acest script NU
provizionează cont bancar/card — personalul nu are nevoie de unul (un cont
de personal cu cont curent + card ar fi semantic greșit).

STRICT PENTRU DEVELOPMENT — reutilizează exact aceeași gardă de siguranță
ca celelalte scripturi (importată, nu duplicată).

Rulare (din interiorul containerului auth-service):

    docker compose exec \\
        -e APP_ENV=development \\
        -e ALLOW_DEMO_SEED=true \\
        -e STAFF_EMAIL='staff@maestrobank.local' \\
        -e STAFF_PASSWORD='ParolaPersonal123' \\
        -e MONGO_URL=mongodb://mongodb:27017 \\
        auth-service python scripts/create_staff_user.py

Idempotent — dacă un user cu STAFF_EMAIL există deja, îi actualizează
parola/rolul în loc să creeze un duplicat.

Verificare finală LIVE, prin API-ul real (Gateway) — ZERO scurtătură,
exact ce ar face un browser: login -> cere un JWT cu role="staff" ->
apelează GET /api/transactions/staff/fraud-evaluations cu el -> confirmă
200 (nu 403) -> dovada că tot lanțul (rol pe document -> rol în JWT ->
require_staff care îl citește corect) funcționează cap-coadă.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seed_demo_data import _require_development_environment, hash_password  # noqa: E402


def _require_staff_credentials() -> tuple[str, str]:
    email = os.getenv("STAFF_EMAIL")
    password = os.getenv("STAFF_PASSWORD")
    if not email or not password:
        print("REFUZ: variabilele STAFF_EMAIL / STAFF_PASSWORD nu sunt setate.", file=sys.stderr)
        sys.exit(1)
    return email.strip().lower(), password


async def create_or_update_staff_user(db_auth, email: str, password: str) -> str:
    password_hash = hash_password(password)
    existing = await db_auth.users.find_one({"email": email})
    if existing is not None:
        await db_auth.users.update_one(
            {"_id": existing["_id"]},
            {"$set": {"password_hash": password_hash, "role": "staff", "is_active": True}},
        )
        print(f"Cont de personal existent actualizat: {email}")
        return str(existing["_id"])

    result = await db_auth.users.insert_one(
        {
            "first_name": "Staff",
            "last_name": "MaestroBank",
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.now(timezone.utc),
            "is_active": True,
            "role": "staff",
            "is_demo": True,
        }
    )
    print(f"Cont de personal nou creat: {email}")
    return str(result.inserted_id)


async def run_live_check(gateway_url: str, email: str, password: str) -> None:
    async with httpx.AsyncClient(timeout=10.0, base_url=gateway_url) as client:
        login_response = await client.post("/api/auth/login", json={"email": email, "password": password})
        if login_response.status_code != 200:
            print(f"EȘUAT: login personal -> HTTP {login_response.status_code}: {login_response.text}", file=sys.stderr)
            sys.exit(1)
        token = login_response.json()["access_token"]

        staff_response = await client.get(
            "/api/transactions/staff/fraud-evaluations", headers={"Authorization": f"Bearer {token}"}
        )
        if staff_response.status_code != 200:
            print(
                f"EȘUAT: GET /api/transactions/staff/fraud-evaluations -> HTTP {staff_response.status_code}: "
                f"{staff_response.text}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"Verificare live: OK — login + acces la rutele de personal confirmate (HTTP {staff_response.status_code}).")


async def main() -> None:
    _require_development_environment()
    email, password = _require_staff_credentials()
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000")

    client_mongo = AsyncIOMotorClient(mongo_url)
    db_auth = client_mongo["auth_db"]
    await client_mongo.admin.command("ping")

    await create_or_update_staff_user(db_auth, email, password)
    client_mongo.close()

    await run_live_check(gateway_url, email, password)


if __name__ == "__main__":
    asyncio.run(main())
