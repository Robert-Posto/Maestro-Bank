"""Percentilă prin interpolare liniară (metoda "numpy default") — fără
numpy/scipy în acest proiect (grep confirmă: nicio dependență de calcul
numeric în requirements.txt), și oricum vrem o implementare simplă,
determinist testabilă pe cazuri cu numere rotunde, nu o dependență de
comportamentul intern al modulului `statistics`.
"""


def percentile(values: list[int] | list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
