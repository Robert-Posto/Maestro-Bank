"""Teste pentru app/services/moderation_service.py — vezi feedback
userului: "la injurii vreau sa nu raspunda... sa roage sa reformulezez".
"""

from app.services import moderation_service


def test_clean_message_has_no_profanity():
    assert moderation_service.contains_profanity("Cât am cheltuit luna asta pe restaurante?") is False


def test_detects_profanity_lowercase():
    assert moderation_service.contains_profanity("esti prost si nu intelegi nimic") is True


def test_detects_profanity_with_diacritics():
    assert moderation_service.contains_profanity("ești proastă, nu-mi dai un răspuns bun") is True


def test_detects_profanity_uppercase():
    assert moderation_service.contains_profanity("EȘTI IDIOT") is True


def test_detects_english_profanity():
    assert moderation_service.contains_profanity("this app is shit") is True


def test_word_boundary_does_not_false_positive_on_substrings():
    # "prostie"/"prost" ca substring într-un cuvânt nelegat nu există des în
    # română, dar verificăm totuși granița de cuvânt pe un caz plauzibil:
    # "constient" nu conține nicio rădăcină din listă -> fals pozitiv 0.
    assert moderation_service.contains_profanity("sunt constient de asta") is False


def test_rephrase_answer_does_not_echo_the_profanity():
    # Mesajul determinist NU repetă cuvântul jignitor primit.
    answer = moderation_service.REPHRASE_REQUEST_ANSWER
    assert "prost" not in answer.lower()
    assert len(answer) < 200
