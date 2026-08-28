"""Teste pentru app/services/safety_guard.py — în special bug-ul raportat
de user: un răspuns normal, cu un IBAN MaestroBank (nesensibil, se dă în
mod normal), era înlocuit integral cu avertismentul de PIN/CVV, pentru că
partea numerică a unui IBAN (RO + 2 cifre + MAES + 16 cifre) cade exact
în intervalul "13-19 cifre la rând" folosit pentru a detecta un număr
complet de card (PAN).
"""

from app.services import safety_guard

# IBAN demo real (format MaestroBank) — partea numerică ("689589684861247903"
# minus separatori) are 18 cifre, direct în intervalul 13-19 verificat pentru PAN.
_DEMO_IBAN = "RO68MAES9589684861247903"


def test_detect_sensitive_data_flags_real_card_pan_in_user_input():
    """Comportamentul ORIGINAL, pentru ce tastează userul — un șir de 16
    cifre (număr de card real) TREBUIE detectat, neschimbat de fix."""
    assert safety_guard.detect_sensitive_data("cardul meu e 4111 1111 1111 1111") is True


def test_detect_sensitive_data_pan_check_can_be_disabled():
    assert safety_guard.detect_sensitive_data(_DEMO_IBAN, include_pan_check=True) is True
    assert safety_guard.detect_sensitive_data(_DEMO_IBAN, include_pan_check=False) is False


def test_redact_if_sensitive_does_not_flag_a_normal_answer_containing_an_iban():
    """Bug-ul raportat: agentul răspunde normal la o întrebare de sold, dar
    include IBAN-ul contului (complet legitim — IBAN-ul NU e secret) — nu
    trebuie înlocuit cu avertismentul de PIN/CVV."""
    answer = f"Soldul contului tău ({_DEMO_IBAN}) este 0,00 RON."
    assert safety_guard.redact_if_sensitive(answer) == answer


def test_redact_if_sensitive_still_catches_real_pin_mention():
    """Verificarea pe cuvinte-cheie (PIN/CVV + cod scurt alăturat) rămâne
    activă pe output — doar verificarea de PAN (13-19 cifre) e dezactivată."""
    answer = "PIN-ul tău este 4821."
    assert safety_guard.redact_if_sensitive(answer) == safety_guard.SENSITIVE_DATA_WARNING


def test_redact_if_sensitive_passes_through_clean_answer():
    answer = "Cardul tău este activ, plățile internaționale sunt dezactivate."
    assert safety_guard.redact_if_sensitive(answer) == answer
