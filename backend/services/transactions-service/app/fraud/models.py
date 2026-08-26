"""DTO-uri imuabile pentru motorul de scoring fraud — vezi scoring.py.

Toate modelele de aici sunt `frozen=True`: scoring.py și rules_*.py NU au
voie să atingă DB/HTTP/ceasul — orice fapt de care au nevoie e adunat în
avans de context.py și împachetat aici. Asta e ce face `scoring.evaluate`
testabil ca funcție pură (aceleași input-uri -> exact același rezultat,
mereu, cerință explicită de determinism din spec).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class TransactionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount_minor: int
    category: str
    to_iban: str
    from_account_id: str
    to_account_id: str


class HistorySample(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount_minor: int
    category: str
    hour_utc: int
    created_at: datetime


class UserProfileSnapshot(BaseModel):
    """Instantaneu al profilului materializat (tx_db.fraud_profiles), citit
    ÎNAINTE ca tranzacția curentă să fie inclusă în el — profilul e
    actualizat doar în hook-ul POST-completare (vezi fraud/service.py),
    deci ordinea garantează că nicio tranzacție nu se scorează față de ea
    însăși. Absența unui profil (userul e la prima tranzacție) e un profil
    "gol" (empty()), NU o eroare — vezi profile.py::get_profile."""

    model_config = ConfigDict(frozen=True)

    transaction_count: int = 0
    first_transaction_at: datetime | None = None
    last_transaction_at: datetime | None = None
    history_samples: tuple[HistorySample, ...] = ()
    category_counts: dict[str, int] = {}
    beneficiary_countries: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> "UserProfileSnapshot":
        return cls()


class CohortBaseline(BaseModel):
    """Baseline agregat, non-personal — folosit DOAR la cold start (vezi
    rules_amount.py, rules_temporal.py). Un singur cohort GLOBAL în Faza 1,
    fără segmentare pe vechime/tip cont — gap documentat pentru Faza 2."""

    model_config = ConfigDict(frozen=True)

    sample_size: int = 0
    p95_amount_minor: int = 0
    median_amount_minor: int = 0
    average_amount_minor: int = 0
    median_amount_minor_by_category: dict[str, int] = {}
    hour_p5: int = 0
    hour_p95: int = 23


class BeneficiaryWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    seen_before: bool = False
    # Sumele trimise ACESTUI beneficiar în ultimele 30 min, cronologic —
    # include tranzacția curentă (interogarea rulează DUPĂ insert, vezi
    # context.py), exact ce vrea VEL-05 pentru secvența escaladantă.
    recent_amounts_same_beneficiary: tuple[int, ...] = ()
    distinct_senders_last_24h: int = 0  # BEN-05 — post-core, informativ, exclus din scor


class WindowFacts(BaseModel):
    """Rezultatele interogărilor "live" pe fereastră de timp (tx_db.transactions),
    adunate de context.py DUPĂ ce tranzacția curentă a fost inserată — astfel
    interogările o includ automat pe ea, fără cod special de "current +
    istoric"."""

    model_config = ConfigDict(frozen=True)

    count_last_10min: int = 0
    amount_last_1h_minor: int = 0
    beneficiary: BeneficiaryWindow = BeneficiaryWindow()
    identical_amount_distinct_beneficiaries_60min: int = 0
    recent_incoming_credit_minor: int | None = None  # cel mai recent credit intrat, în fereastră, pt BEH-03
    new_beneficiaries_last_60min: int = 0  # VEL-03
    near_threshold_count_last_24h: int = 0  # STR-01


class DeviceFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    latest_passkey_created_at: datetime | None = None
    data_available: bool = True  # False dacă auth-service a picat/timeout — fail-open, regula nu se declanșează


class LoginEvent(BaseModel):
    """O încercare de login, succes SAU eșec — vezi auth-service
    app/login_events.py. `device_signature` e o aproximare (hash IP+UA),
    NU un fingerprint real de dispozitiv — vezi planul fazei."""

    model_config = ConfigDict(frozen=True)

    success: bool
    device_signature: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    created_at: datetime


class CredentialEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: Literal["enrolled", "revoked"]
    created_at: datetime


class SecurityFacts(BaseModel):
    """Istoric login/credențiale — UN SINGUR apel către auth-service
    (/internal/security-facts/{user_id}), consumat de VEL-04 și de
    DEV-01/02/04/05/06. Separat de DeviceFacts (DOAR DEV-03, apel diferit,
    deja existent înainte de această fază) — vezi planul fazei.
    `recent_logins` vine deja sortat descrescător (cele mai recente
    primele) de la auth-service."""

    model_config = ConfigDict(frozen=True)

    recent_logins: tuple[LoginEvent, ...] = ()
    password_changed_at: datetime | None = None
    recent_credential_events: tuple[CredentialEvent, ...] = ()
    data_available: bool = True  # False dacă auth-service a picat/timeout — fail-open


class RuleContext(BaseModel):
    """Tot ce au nevoie rules_*.py + scoring.py — niciun import de DB/HTTP
    dincolo de acest punct."""

    model_config = ConfigDict(frozen=True)

    transaction: TransactionSnapshot
    source_balance_minor: int
    profile: UserProfileSnapshot
    window: WindowFacts
    cohort: CohortBaseline
    device: DeviceFacts
    security: SecurityFacts
    evaluated_at: datetime


class RuleOutcome(BaseModel):
    """Ce întoarce un check_fn când o regulă se declanșează (None altfel)."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    family: str
    weight: int
    contributes_to_score: bool
    values: dict[str, Any]


class ScoredRule(BaseModel):
    """RuleOutcome + rezultatul aplicării diminishing-returns — forma
    scrisă efectiv în audit log (fraud_evaluations.fired_rules)."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    family: str
    weight: int
    contribution: float
    excluded_from_score: bool
    values: dict[str, Any]


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: int
    fired_rules: tuple[ScoredRule, ...]
    decision_would_apply: str
    ruleset_version: str


class EvaluationReview(BaseModel):
    """Adnotarea unui membru al personalului pe o evaluare deja scrisă —
    NICIODATĂ nu modifică score/fired_rules/decision_would_apply (acelea
    rămân decizia automată originală, imuabilă — vezi fraud/staff.py).
    În Faza 1 (shadow mode, nicio aplicare reală) e strict o adnotare de
    calibrare; devine un veritabil "override" abia când există o
    aplicare reală de contestat (faza de PENDING hold)."""

    model_config = ConfigDict(frozen=True)

    reviewed_by: str
    reviewed_at: datetime
    outcome: Literal["confirmed_fraud", "false_positive", "legitimate"]
    note: str = ""
