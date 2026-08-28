"""Teste pentru app/services/safety_guard.py.

`detect_sensitive_data` se aplică DOAR pe ce introduce USERUL — verificarea
simetrică pe răspunsul GENERAT de model (`redact_if_sensitive`) a fost
eliminată după DOUĂ fals-pozitive reale, confirmate live (vezi docstring-ul
modulului): un IBAN normal (partea numerică are exact 16 cifre, în
intervalul "13-19" verificat pentru un număr de card) și mențiunea "PIN"
din contextul plăților apărând oriunde în același răspuns cu ultimele 4
cifre ale unui card (`last_four`) — ambele răspunsuri complet legitime,
transformate în avertismente confuze. Testele de mai jos verifică doar ce
a rămas: comportamentul pe INPUT-ul userului, unde riscul e real.
"""

from app.services import safety_guard


def test_detect_sensitive_data_flags_real_card_pan_in_user_input():
    """Un șir de 16 cifre (număr de card real), tastat de user, TREBUIE detectat."""
    assert safety_guard.detect_sensitive_data("cardul meu e 4111 1111 1111 1111") is True


def test_detect_sensitive_data_flags_pin_with_short_code_in_user_input():
    assert safety_guard.detect_sensitive_data("PIN-ul meu e 4821") is True


def test_detect_sensitive_data_flags_cvv_with_short_code_in_user_input():
    assert safety_guard.detect_sensitive_data("cvv-ul e 123") is True


def test_detect_sensitive_data_ignores_iban_when_the_question_does_not_quote_it():
    """"care e IBAN-ul meu?" (întrebarea REALĂ, tipică — userul nu-l știe,
    de-aia întreabă) e complet legitimă, nu trebuie blocată. NU testăm aici
    varianta în care userul ar cita explicit un IBAN complet în mesaj — acel
    caz e deja detectat ca "posibil PAN" (partea numerică a unui IBAN are
    16 cifre, în intervalul verificat), un compromis acceptat, existent
    dinainte de acest fix — vezi _DIGIT_GROUP din safety_guard.py."""
    assert safety_guard.detect_sensitive_data("care e IBAN-ul meu?") is False


def test_detect_sensitive_data_does_not_flag_a_normal_amount():
    """"1234 lei" nu e un PIN — cuvântul "pin"/"cvv" trebuie să existe
    explicit, nu doar orice număr scurt."""
    assert safety_guard.detect_sensitive_data("am cheltuit 1234 lei luna asta") is False


def test_detect_sensitive_data_does_not_flag_forgotten_password_question():
    """"parolă" nu declanșează nimic — doar PIN/CVV, verificare îngustă,
    intenționată (vezi docstring-ul modulului)."""
    assert safety_guard.detect_sensitive_data("mi-am uitat parola") is False
