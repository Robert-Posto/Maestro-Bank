"""Segmentele roții norocului — ofertă FIXĂ, ca la catalogul de recompense,
NU un joc cu premii generate dinamic.

Fiecare segment are DOUĂ greutăți: `weight_base` (pariu 0) și
`weight_boosted` (la pariul de referință sau mai mult) — vezi
app/service.py::_pick_weighted_segment pentru interpolarea liniară dintre
ele, în funcție de câte puncte pariază userul la acea învârtire. Mai multe
puncte pariate = șanse mai mari la segmentele cu premii mai bune, dar marele
premiu rămâne rar chiar și la pariul maxim (greutatea lui crește doar 6x,
față de restul segmentelor care se apropie mult mai mult de greutatea lor
"boosted").

Numerele sunt politică PROPRIE MaestroBank, pentru un demo — o interpolare
liniară simplă și documentată, NU un "algoritm sofisticat" (aceeași
filosofie ca la bufferul de siguranță din ai-orchestrator-service).
"""

# Puncte pariate la care se aplică 100% din boost (interpolare liniară sub
# acest prag, plafonată la 100% peste el).
REFERENCE_WAGER = 1_000

# `label` = RO; `label_en` = EN — alese după limba request-ului la
# serializare (vezi app/service.py::list_wheel_segments / spin_wheel).
WHEEL_SEGMENTS: list[dict] = [
    {"id": "nothing_1", "label": "Nimic de data asta", "label_en": "Nothing this time", "reward_value_minor": None, "weight_base": 40, "weight_boosted": 20},
    {"id": "nothing_2", "label": "Mai încearcă", "label_en": "Try again", "reward_value_minor": None, "weight_base": 25, "weight_boosted": 12},
    {"id": "small_5", "label": "5 lei cashback", "label_en": "5 RON cashback", "reward_value_minor": 500, "weight_base": 20, "weight_boosted": 25},
    {"id": "small_10", "label": "10 lei cashback", "label_en": "10 RON cashback", "reward_value_minor": 1_000, "weight_base": 8, "weight_boosted": 20},
    {"id": "medium_25", "label": "25 lei cashback", "label_en": "25 RON cashback", "reward_value_minor": 2_500, "weight_base": 5, "weight_boosted": 13},
    {"id": "medium_50", "label": "50 lei cashback", "label_en": "50 RON cashback", "reward_value_minor": 5_000, "weight_base": 1.5, "weight_boosted": 7},
    {
        "id": "jackpot_200",
        "label": "Marele premiu — 200 lei cashback",
        "label_en": "Jackpot — 200 RON cashback",
        "reward_value_minor": 20_000,
        "weight_base": 0.5,
        "weight_boosted": 3,
    },
]


def get_segment(segment_id: str) -> dict | None:
    return next((s for s in WHEEL_SEGMENTS if s["id"] == segment_id), None)
