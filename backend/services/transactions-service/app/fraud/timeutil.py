"""Normalizare datetime pentru pachetul fraud/.

Motor (fără `tz_aware=True` configurat în app/database.py) întoarce
datetime-uri NAIVE (fără tzinfo) la citire din Mongo, chiar dacă au fost
scrise ca aware (UTC) — comportament implicit pymongo. Restul acestui
serviciu nu face niciodată aritmetică Python directă pe datetime-uri citite
din DB (doar le pasează înapoi în filtre Mongo, unde comparația se face la
nivel BSON și tzinfo nu contează).

Pachetul fraud/ FACE aritmetică Python directă (ex. "cât de vechi e ultimul
transfer", "e ora în banda personală de activitate") — de-aia orice
datetime care intră în fraud/ (evaluated_at din create_transfer, e aware;
tot ce vine din Mongo sau din JSON-ul auth-service-ului, e naiv) trebuie
normalizat la naive-UTC chiar la graniță, ca să nu amestece aware cu naive
și să pice cu TypeError la un `-`.
"""

from datetime import datetime


def to_naive_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value
