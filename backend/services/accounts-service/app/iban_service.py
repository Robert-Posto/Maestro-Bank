"""Generator de IBAN DEMO pentru MaestroBank.

⚠️ IMPORTANT: acesta NU este un IBAN emis de o bancă reală și NU trebuie
prezentat vreodată ca atare. Are doar o structură similară unui IBAN
real (aceeași lungime, același prefix de țară), suficientă pentru un UI
de prototip:

    RO<2 cifre>MAES<16 caractere numerice>
    (RO + 2 + MAES(4) + 16 = 24 caractere, ca un IBAN real din România)

Exemplu: RO49MAES1234567890123456

Notă tehnică: un IBAN real calculează cele 2 "cifre de control" cu
algoritmul MOD-97 (ISO 7064), pornind de la codul băncii + contul.
Aici cifrele sunt generate PSEUDO-ALEATOR (nu calculate conform
standardului) — suficient pentru a fi credibil vizual într-un demo, dar
NU valid conform standardului bancar real și NU trebuie folosit pentru
altceva decât acest prototip.
"""

import random
import string

from motor.motor_asyncio import AsyncIOMotorDatabase

DEMO_BANK_CODE = "MAES"
_MAX_GENERATION_ATTEMPTS = 10


def generate_demo_iban() -> str:
    check_digits = f"{random.randint(0, 99):02d}"
    account_digits = "".join(random.choices(string.digits, k=16))
    return f"RO{check_digits}{DEMO_BANK_CODE}{account_digits}"


async def generate_unique_demo_iban(database: AsyncIOMotorDatabase) -> str:
    """Generează un IBAN demo garantat unic în accounts_db.accounts."""
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        candidate = generate_demo_iban()
        existing = await database.accounts.find_one({"iban": candidate})
        if existing is None:
            return candidate
    raise RuntimeError(f"Nu s-a putut genera un IBAN demo unic după {_MAX_GENERATION_ATTEMPTS} încercări.")
