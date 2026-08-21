"""Configurația motorului de reguli fraud — greutăți, praguri, benzi de
decizie, versiune ruleset.

Gap CUNOSCUT și ACCEPTAT pentru Faza 1 (discutat explicit înainte de
implementare): toate constantele de mai jos sunt Python simplu, NU un store
configurabil live (fără deploy). `get_active_ruleset()` e singurul seam prin
care se citește ruleset-ul activ — dimensionat ca un store Mongo/UI de admin
să încapă mai târziu fără să atingă context.py/scoring.py.
"""

from dataclasses import dataclass

RULESET_VERSION = "2026-08-20.1"
COLD_START_MIN_TRANSACTIONS = 20


@dataclass(frozen=True)
class RulesetConfig:
    version: str = RULESET_VERSION

    # --- Amount ---------------------------------------------------------
    amt01_weight: int = 25
    amt01_multiplier: float = 2.0
    amt01_cold_start_weight: int = 12
    amt01_cold_start_multiplier: float = 3.0

    amt02_weight: int = 20
    amt02_multiplier: float = 4.0
    amt02_cold_start_weight: int = 10
    amt02_cold_start_multiplier: float = 6.0

    amt03_weight: int = 20
    amt03_ratio: float = 0.7

    amt04_weight: int = 40
    amt04_ratio: float = 0.98

    amt05_weight: int = 15
    amt05_cold_start_weight: int = 10
    amt05_multiplier: float = 5.0
    amt05_max_prior_transactions: int = 20

    # --- Velocity ---------------------------------------------------------
    vel01_weight: int = 20
    vel01_max_count_10min: int = 5

    vel02_weight: int = 30
    vel02_multiplier: float = 3.0

    vel05_weight: int = 40
    vel05_min_sequence: int = 3  # include tranzacția curentă

    # --- Beneficiary --------------------------------------------------------
    ben01_weight: int = 15
    ben03_weight: int = 20
    ben05_weight: int = 50
    ben05_min_distinct_senders: int = 5

    # --- Temporal -----------------------------------------------------------
    time01_weight: int = 15
    time01_cold_start_weight: int = 7
    time02_weight: int = 25
    time02_dormant_days: int = 90

    # --- Device (doar DEV-03 în Faza 1) --------------------------------------
    dev03_weight: int = 40
    dev03_window_minutes: int = 60

    # --- Behaviour ------------------------------------------------------------
    beh01_weight: int = 15
    beh02_weight: int = 10
    beh02_max_share: float = 0.05
    beh03_weight: int = 40
    beh03_tolerance_ratio: float = 0.02
    beh03_window_hours: int = 2

    # --- Structuring ----------------------------------------------------------
    str02_weight: int = 35
    str02_min_distinct_beneficiaries: int = 3
    str02_window_minutes: int = 60

    # --- Scoring --------------------------------------------------------------
    diminishing_multipliers: tuple[float, ...] = (1.0, 0.6, 0.3)  # a 3-a+ regulă dintr-o familie = ultima valoare
    score_cap: int = 100

    # Benzile de decizie oglindesc benzile REALE din specificația sursă
    # (nu un placeholder inventat) — ca datele din shadow mode să poată fi
    # folosite direct la calibrarea comportamentului real, mai târziu.
    band_notify_min: int = 30   # 30-59 -> "notify"
    band_step_up_min: int = 60  # 60-79 -> "step_up"
    band_hold_min: int = 80     # 80+   -> "hold"; sub 30 -> "pass"

    cold_start_min_transactions: int = COLD_START_MIN_TRANSACTIONS
    percentile_window_days: int = 90
    cohort_baseline_ttl_hours: int = 24
    cohort_sample_size: int = 10_000


def get_active_ruleset() -> RulesetConfig:
    """Singurul seam prin care se citește ruleset-ul activ — vezi nota
    de mai sus despre gap-ul de configurabilitate.

    `cohort_baseline_ttl_hours` e singura valoare care CHIAR vine din
    settings (env var, FRAUD_COHORT_BASELINE_TTL_HOURS) — restul greutăților/
    pragurilor sunt constante Python, per gap-ul documentat mai sus."""
    from app.config import settings  # import local — evită ciclu la import-time

    return RulesetConfig(cohort_baseline_ttl_hours=settings.fraud_cohort_baseline_ttl_hours)
