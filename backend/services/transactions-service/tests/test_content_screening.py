"""Teste pentru app/content_screening.py — vezi feedback userului:
"vreau ca atunci cand fac o tranzactie si pun o descriere ciudata gen
cuvinte precum isis bombe etc sa primesti un avertisment"."""

from app.content_screening import screen_description


def test_clean_description_has_no_warning():
    assert screen_description("Chirie august") is None


def test_empty_description_has_no_warning():
    assert screen_description("") is None


def test_flags_isis():
    assert screen_description("pentru ISIS") is not None


def test_flags_bomba_with_diacritics():
    assert screen_description("bombă la aeroport") is not None


def test_flags_bomba_without_diacritics():
    assert screen_description("bomba") is not None


def test_flags_terrorist_inflections():
    assert screen_description("atac terorist planificat") is not None


def test_flags_atentat():
    assert screen_description("finanțare atentat") is not None


def test_word_boundary_does_not_false_positive():
    # "terorist"/"bomba" ca substring într-un cuvânt nelegat nu există des
    # în română, dar verificăm granița de cuvânt pe un caz plauzibil.
    assert screen_description("cadou pentru bunica") is None


def test_warning_does_not_repeat_raw_flagged_word_only_generic_notice():
    # Mesajul e generic, nu ecou-ează cuvântul exact găsit.
    warning = screen_description("bomba")
    assert warning is not None
    assert "bomba" not in warning.lower()


def test_warning_message_is_neutral_about_transfer_status():
    # Funcția e folosită ȘI la verificarea LIVE, înainte ca vreun transfer
    # să existe (vezi POST /transfers/screen-description) — mesajul NU
    # trebuie să presupună că transferul "a fost procesat", ar fi fals în
    # acel context.
    warning = screen_description("bomba")
    assert warning is not None
    assert "procesat" not in warning.lower()
