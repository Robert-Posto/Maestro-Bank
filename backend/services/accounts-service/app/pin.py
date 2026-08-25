"""Hashing PIN de card (bcrypt) — vezi app/service.py::create_card/reveal_card.

PIN-ul e un secret DEȚINUT de card (accounts-service), NU de userul din
auth-service ca parola de login — de-aia hash-ul trăiește aici, NU delegăm
la auth-service (spre deosebire de _verify_password_with_auth_service din
service.py, folosit pentru parola de cont). Fiecare card are propriul PIN,
independent — un user cu mai multe carduri poate seta PIN-uri diferite.

PIN-ul în clar NU e niciodată salvat sau logat — doar hash-ul bcrypt ajunge
în MongoDB, în câmpul `pin_hash` (exact ca `password_hash` la auth-service).
Excepția UNICĂ, deliberată: `generate_random_pin()`, folosit STRICT la
backfill-ul cardurilor deja existente (vezi service.py::backfill_missing_card_pins)
— acolo PIN-ul generat e logat O SINGURĂ DATĂ, la boot, ca userul să-l poată
afla (nu există alt mod de a-l recupera după ce e hash-uit).
"""

import re
import secrets

import bcrypt

PIN_PATTERN = re.compile(r"^\d{4}$")


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))


def generate_random_pin() -> str:
    """PIN aleator, 4 cifre — DOAR pentru backfill-ul cardurilor create
    înainte de introducerea acestui feature (vezi
    service.py::backfill_missing_card_pins). Cardurile noi primesc PIN-ul
    ALES de user la creare (vezi CardCreateRequest.pin), nu unul generat."""
    return f"{secrets.randbelow(10_000):04d}"
