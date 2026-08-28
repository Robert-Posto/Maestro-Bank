"""Filtre deterministe de securitate pentru MaestroAssistent + Support Agent
— vezi feedback userul: "nu mi da iban pin prompturi etc... nu ma lasa sa
ii dau eu date personale... atentioneaza sau blocheaza conversatia".

Aceeași filozofie ca app/services/moderation_service.py (injurii) —
verificare ÎNAINTE de orice apel GPT, determinist, NU la latitudinea
modelului. Două direcții separate, DELIBERAT independente una de alta:

1. `detect_sensitive_data` — userul introduce în chat PIN/CVV/numărul
   complet al cardului. Verificare ÎNGUSTĂ, intenționat — DOAR aceste 3
   secrete de card (nu IBAN: IBAN-ul NU e secret, se dă în mod normal ca
   să primești bani — o restricție acolo ar bloca o întrebare complet
   legitimă, "care e IBAN-ul meu?"). O verificare mai largă (orice șir de
   cifre, orice cuvânt care "sună a parolă") ar da fals-pozitive prea des
   pe întrebări normale ("am cheltuit 1234 lei" nu e un PIN).

2. `detect_prompt_extraction_attempt` — userul încearcă să scoată
   promptul de sistem / instrucțiunile interne ("arată-mi promptul",
   "ignoră instrucțiunile anterioare" etc.) — un tip de întrebare complet
   diferit, cu propriul mesaj de refuz.

Ambele sunt verificări STRUCTURALE, DE PRECIZIE — niciuna nu întoarce
"suspect" pe baza unei singure cuvinte ambigue (ex. simpla apariție a
cuvântului "parolă" NU declanșează nimic — "mi-am uitat parola" e o
întrebare de suport complet normală). Scopul e să prindă cazurile clare,
fără să deranjeze conversațiile normale — vezi task-ul: "te rog nu strica,
doar imbunatateste".

Apărare suplimentară, STRUCTURALĂ (nu ține de acest modul, dar e motivul
pentru care riscul real e deja mic): niciun tool disponibil vreunui agent
nu întoarce vreodată PAN/CVV/PIN — vezi app/tools/support_cards_tools.py,
care apelează GET /api/accounts/me/cards (CardOut din accounts-service),
un DTO care NU conține niciodată aceste câmpuri. Filtrele de mai jos sunt
DOAR pentru ce introduce USERUL în conversație, nu pentru ce ar putea
"scăpa" un tool.
"""

from __future__ import annotations

import re
import unicodedata

from app.i18n import translate


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_diacritics = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_diacritics.lower()


# --- 1. Date sensibile de card introduse de user ---------------------------

# `\w*` prinde formele flexionate ("pinul", "pinu-mi") — la fel ca rădăcinile
# din moderation_service.py. Riscul de fals-pozitiv pe alt sens al lui "pin"
# (ex. "pin" = brad, în română) e mic: condiția cere ȘI un cod scurt alăturat
# (_SHORT_CODE mai jos) — cineva discutând despre brazi nu are de ce să
# pomenească și un număr de 3-6 cifre în aceeași propoziție.
_PIN_KEYWORD = re.compile(r"\bpin\w*")
_CVV_KEYWORD = re.compile(r"\bcvv\w*|\bcod de securitate\b|\bcod secret\b")
_SHORT_CODE = re.compile(r"\b\d{3,6}\b")

# Număr complet de card (PAN) — grupuri de cifre separate de spații/liniuțe
# (formatul obișnuit de afișare a unui card), care însumează 13-19 cifre
# odată ce scoatem separatorii. Un șir atât de lung de cifre practic NU
# apare niciodată într-o întrebare bancară normală — de-aia verificarea
# asta NU cere niciun cuvânt-cheie alăturat, spre deosebire de PIN/CVV
# (prea scurte ca să fie neambigue fără context — "1234" apare des în
# întrebări normale, gen sume de bani).
_DIGIT_GROUP = re.compile(r"\d(?:[ \-]?\d){12,18}")


def detect_sensitive_data(text: str, *, include_pan_check: bool = True) -> bool:
    """True dacă `text` conține (probabil) un PIN, un CVV sau un număr
    complet de card. Vezi docstring-ul modulului pentru raționamentul din
    spatele fiecărui tip de verificare.

    `include_pan_check=False` dezactivează DOAR verificarea de "13-19 cifre
    la rând" (număr de card) — folosit de `redact_if_sensitive` mai jos, pe
    răspunsul GENERAT de agent, unde acel tipar dă fals-pozitiv sigur pe un
    IBAN MaestroBank normal (format RO + 2 cifre + MAES + 16 cifre — partea
    numerică, luată singură, are exact 16 cifre, direct în intervalul
    13-19). Verificarea rămâne completă (inclusiv PAN) pe INPUT-ul userului,
    unde riscul e real — un user chiar poate tasta un număr de card real."""
    normalized = _normalize(text)

    if include_pan_check:
        for match in _DIGIT_GROUP.finditer(normalized):
            digits = re.sub(r"\D", "", match.group())
            if 13 <= len(digits) <= 19:
                return True

    if _PIN_KEYWORD.search(normalized) and _SHORT_CODE.search(normalized):
        return True
    if _CVV_KEYWORD.search(normalized) and _SHORT_CODE.search(normalized):
        return True

    return False


SENSITIVE_DATA_WARNING = (
    "Nu introduce niciodată PIN-ul, CVV-ul sau numărul complet al cardului într-o conversație — "
    "nici cu mine, nici cu altcineva. Pentru aceste date, mergi la \"Cardul meu\" din aplicație, "
    "unde sunt protejate prin verificare suplimentară (PIN-ul cardului sau passkey)."
)


# --- 2. Încercări de a scoate promptul de sistem / instrucțiunile interne --

_PROMPT_EXTRACTION_ROOTS = [
    "system prompt",
    "system[- ]?ul t[aă]u",
    "instructiunile tale",
    "instructiunile interne",
    "instructiunile de sistem",
    "care sunt instructiunile",
    "arat[aă][- ]mi (?:promptul|instructiunile)",
    "afiseaz[aă] (?:promptul|instructiunile)",
    "repet[aă] (?:tot )?ce (?:e|este) mai sus",
    "ignor[aă] instructiunile",
    "ignore (?:all )?(?:previous|prior|above) instructions",
    "reveal your (?:prompt|instructions)",
    "your (?:system )?instructions",
    "show me your prompt",
    "what is your prompt",
    "print your instructions",
]
_PROMPT_EXTRACTION_PATTERN = re.compile("|".join(_PROMPT_EXTRACTION_ROOTS), re.IGNORECASE)


def detect_prompt_extraction_attempt(text: str) -> bool:
    return bool(_PROMPT_EXTRACTION_PATTERN.search(_normalize(text)))


PROMPT_EXTRACTION_REFUSAL = (
    "Nu pot să-ți arăt instrucțiunile mele interne — dar te pot ajuta cu întrebări reale despre "
    "cont, card, tranzacții sau finanțele tale."
)


# --- Apărare suplimentară — curăță răspunsul GENERAT de GPT, în caz că a
# reprodus totuși ceva ce arată a PIN/CVV/număr de card (nu ar trebui să
# se întâmple — niciun tool nu-i oferă aceste date, vezi docstring-ul
# modulului — dar costă puțin să verificăm și ieșirea, nu doar intrarea). --


def redact_if_sensitive(answer: str) -> str:
    """Dacă răspunsul generat de model conține (probabil) date sensibile de
    card, îl înlocuim în întregime cu un mesaj determinist — NU încercăm să
    "reparăm" doar fragmentul (ar putea rămâne context suficient să fie tot
    problematic), preferăm un răspuns clar, sigur, chiar dacă mai puțin
    specific decât originalul.

    `include_pan_check=False` — niciun tool nu întoarce vreodată un PAN real
    (vezi docstring-ul modulului), deci modelul structural nu poate leaka
    unul; verificarea de "13-19 cifre" pe TEXTUL LUI GENERAT dădea fals-
    pozitiv sigur ori de câte ori includea un IBAN normal (ex. "RO68MAES
    9589684861247903" — partea numerică are exact 16 cifre), înlocuind un
    răspuns corect, nesensibil, cu avertismentul — bug real, raportat de
    user ca "răspuns ciudat" la o simplă întrebare de sold."""
    if detect_sensitive_data(answer, include_pan_check=False):
        return translate("sensitiveDataWarning")
    return answer
