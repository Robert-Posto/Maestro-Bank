"""Catalogul de recompense — ofertă CURATORIATĂ, fixă, la fel ca tabelul de
rate de la Depozite sau catalogul de instrumente de la Investiții — NU o
piață deschisă unde userul alege o sumă arbitrară de răscumpărat.

Fiecare recompensă se răscumpără ca un credit REAL de RON în contul curent
al userului (nu un voucher simulat) — vezi app/service.py::redeem_reward,
care reutilizează exact primitivele deja construite la accounts-service
pentru Depozite/Investiții.
"""

REWARDS_CATALOG: list[dict] = [
    {
        "id": "cashback_10",
        "title": "10 lei cashback",
        "description": "Convertește 500 de puncte în 10 lei, creditați direct în contul tău curent.",
        "cost_points": 500,
        "reward_value_minor": 1_000,
    },
    {
        "id": "cashback_25",
        "title": "25 lei cashback",
        "description": "Convertește 1.200 de puncte în 25 lei, creditați direct în contul tău curent.",
        "cost_points": 1_200,
        "reward_value_minor": 2_500,
    },
    {
        "id": "cashback_40",
        "title": "40 lei cashback",
        "description": "Convertește 2.000 de puncte în 40 lei, creditați direct în contul tău curent.",
        "cost_points": 2_000,
        "reward_value_minor": 4_000,
    },
    {
        "id": "cashback_100",
        "title": "100 lei cashback",
        "description": "Convertește 4.500 de puncte în 100 lei, creditați direct în contul tău curent.",
        "cost_points": 4_500,
        "reward_value_minor": 10_000,
    },
]


def get_reward(reward_id: str) -> dict | None:
    return next((r for r in REWARDS_CATALOG if r["id"] == reward_id), None)
