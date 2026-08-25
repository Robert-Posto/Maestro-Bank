"""Registrul FIX al celor 20 de reguli implementate.

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
from app.fraud.rules_device import check_dev_03
from app.fraud.rules_structuring import check_str_01, check_str_02
from app.fraud.rules_temporal import check_time_01, check_time_02
from app.fraud.rules_velocity import check_vel_01, check_vel_02, check_vel_03, check_vel_05

CheckFn = Callable[[RuleContext, RulesetConfig], RuleOutcome | None]


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    check_fn: CheckFn


RULES: tuple[RuleSpec, ...] = (
    RuleSpec("AMT-01", check_amt_01),
    RuleSpec("AMT-02", check_amt_02),
    RuleSpec("AMT-03", check_amt_03),
    RuleSpec("AMT-04", check_amt_04),
    RuleSpec("AMT-05", check_amt_05),
    RuleSpec("VEL-01", check_vel_01),
    RuleSpec("VEL-02", check_vel_02),
    RuleSpec("VEL-03", check_vel_03),
    RuleSpec("VEL-05", check_vel_05),
    RuleSpec("BEN-01", check_ben_01),
    RuleSpec("BEN-03", check_ben_03),
    RuleSpec("BEN-05", check_ben_05),
    RuleSpec("TIME-01", check_time_01),
    RuleSpec("TIME-02", check_time_02),
    RuleSpec("DEV-03", check_dev_03),
    RuleSpec("BEH-01", check_beh_01),
    RuleSpec("BEH-02", check_beh_02),
    RuleSpec("BEH-03", check_beh_03),
    RuleSpec("STR-01", check_str_01),
    RuleSpec("STR-02", check_str_02),
)
