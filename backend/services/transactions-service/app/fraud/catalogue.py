"""Registrul FIX al celor 26 de reguli SCORATE implementate — BEN-04
(blocklist) NU e aici, e un refuz direct, dinainte de scoring, vezi
app/service.py::create_transfer și planul fazei.

Ordinea de aici e ordinea de EVALUARE (irelevantă pentru scor, care
grupează pe familie și sortează descrescător după greutate — vezi
scoring.py), dar fixă și determinist — aceeași ordine, mereu.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.fraud.models import RuleContext, RuleOutcome
from app.fraud.ruleset_config import RulesetConfig
from app.fraud.rules_amount import check_amt_01, check_amt_02, check_amt_03, check_amt_04, check_amt_05
from app.fraud.rules_behaviour import check_beh_01, check_beh_02, check_beh_03
from app.fraud.rules_beneficiary import check_ben_01, check_ben_03, check_ben_05
from app.fraud.rules_device import check_dev_01, check_dev_02, check_dev_03, check_dev_04, check_dev_05, check_dev_06
from app.fraud.rules_structuring import check_str_01, check_str_02
from app.fraud.rules_temporal import check_time_01, check_time_02
from app.fraud.rules_velocity import check_vel_01, check_vel_02, check_vel_03, check_vel_04, check_vel_05

CheckFn = Callable[[RuleContext, RulesetConfig], RuleOutcome | None]


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    check_fn: CheckFn


# Reguli a căror condiție e mereu ADEVĂRATĂ ori de câte ori condiția uneia
# dintre regulile-mamă listate e adevărată — o IMPLICAȚIE LOGICĂ STRICTĂ, nu
# doar o corelație tipică — deci scorarea AMBELOR nu aduce niciun semnal nou,
# doar umflă artificial scorul. Aplicat în scoring.py::apply_diminishing_returns,
# ÎNAINTE de gruparea pe familie — regula subsumată tot apare în audit
# (fired_rules), doar cu contribution=0 (excluded_from_score=True), exact ca
# BEN-05. NU folosi acest mecanism pentru reguli doar CORELATE (ex. VEL-01/
# VEL-03) — diminishing-returns per familie e suficient acolo.
SUBSUMED_BY: dict[str, tuple[str, ...]] = {
    # AMT-04 (>= 98% din sold) implică matematic AMT-03 (> 70% din sold) —
    # aceeași bază de comparație (source_balance_minor), prag strict mai mare.
    "AMT-03": ("AMT-04",),
    # O țară CHIAR nouă (BEN-03) nu poate proveni decât de la un beneficiar
    # niciodată plătit înainte (BEN-01) — profile.py agregă țările DIN
    # beneficiarii plătiți, deci un beneficiar văzut deja ar fi lăsat deja
    # țara lui în istoric. DEV-06 e al doilea "părinte" posibil — vezi mai jos.
    "BEN-01": ("BEN-03", "DEV-06"),
    # DEV-06 e LITERAL combo-ul DEV-01 + beneficiar nou + AMT-01 (vezi
    # rules_device.py::check_dev_06) — nu corelație, ACEEAȘI dovadă
    # restatată. AMT-01 e cross-familie (fără diminishing-returns automat),
    # deci fără asta ar lua credit PLIN suplimentar de fiecare dată.
    "DEV-01": ("DEV-06",),
    "AMT-01": ("DEV-06",),
}


RULES: tuple[RuleSpec, ...] = (
    RuleSpec("AMT-01", check_amt_01),
    RuleSpec("AMT-02", check_amt_02),
    RuleSpec("AMT-03", check_amt_03),
    RuleSpec("AMT-04", check_amt_04),
    RuleSpec("AMT-05", check_amt_05),
    RuleSpec("VEL-01", check_vel_01),
    RuleSpec("VEL-02", check_vel_02),
    RuleSpec("VEL-03", check_vel_03),
    RuleSpec("VEL-04", check_vel_04),
    RuleSpec("VEL-05", check_vel_05),
    RuleSpec("BEN-01", check_ben_01),
    RuleSpec("BEN-03", check_ben_03),
    RuleSpec("BEN-05", check_ben_05),
    RuleSpec("TIME-01", check_time_01),
    RuleSpec("TIME-02", check_time_02),
    RuleSpec("DEV-01", check_dev_01),
    RuleSpec("DEV-02", check_dev_02),
    RuleSpec("DEV-03", check_dev_03),
    RuleSpec("DEV-04", check_dev_04),
    RuleSpec("DEV-05", check_dev_05),
    RuleSpec("DEV-06", check_dev_06),
    RuleSpec("BEH-01", check_beh_01),
    RuleSpec("BEH-02", check_beh_02),
    RuleSpec("BEH-03", check_beh_03),
    RuleSpec("STR-01", check_str_01),
    RuleSpec("STR-02", check_str_02),
)
