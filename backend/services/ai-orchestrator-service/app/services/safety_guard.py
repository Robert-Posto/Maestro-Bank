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

Filtrele de mai jos verifică DOAR ce introduce USERUL în conversație — NU
răspunsul GENERAT de model. A existat, o vreme, și o verificare simetrică
pe OUTPUT (`redact_if_sensitive`, eliminată — vezi istoricul git dacă ai
nevoie de context) — eliminată după DOUĂ fals-pozitive reale, confirmate
live, pe răspunsuri complet normale: un IBAN obișnuit (partea numerică are
exact 16 cifre, în intervalul "13-19 cifre" verificat pentru un număr de
card) și mențiunea "PIN" din contextul plăților/confirmării (o setare de
securitate complet normală de discutat) apărând ORIUNDE în același răspuns
cu ultimele 4 cifre ale cardului (`last_four`, un cod de 4 cifre — nu
adiacent cuvântului "PIN", verificarea nu cerea proximitate). Motivul
pentru care verificarea pe output era oricum doar teoretică: niciun tool
disponibil vreunui agent nu întoarce vreodată PAN/CVV/PIN — vezi
app/tools/support_cards_tools.py, care apelează GET /api/accounts/me/cards
(CardOut din accounts-service), un DTO care NU conține niciodată aceste
câmpuri — modelul nu are, structural, de unde să "scape" un secret real,
deci apăra împotriva unui risc care nu există, cu un cost real (răspunsuri
corecte, transformate în avertismente confuze).
"""

from __future__ import annotations

import re
import unicodedata


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


def detect_sensitive_data(text: str) -> bool:
    """True dacă `text` conține (probabil) un PIN, un CVV sau un număr
    complet de card. Vezi docstring-ul modulului pentru raționamentul din
    spatele fiecărui tip de verificare — DOAR pentru text introdus de USER,
    niciodată pentru răspunsul generat de model (vezi docstring-ul
    modulului pentru motiv)."""
    normalized = _normalize(text)

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
