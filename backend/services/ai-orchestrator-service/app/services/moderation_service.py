"""Filtru determinist pentru injurii/limbaj vulgar — vezi feedback userului:
"la injurii vreau sa nu raspunda... sa roage sa reformulezez".

Verificarea se face ÎNAINTE de orice apel GPT (vezi
app/agents/spending_forecast.py::handle_message) — la fel ca restul
deciziilor critice din acest agent (vezi forecast_service.py, docstring-ul
modulului), NU lăsăm asta la latitudinea modelului: un filtru determinist
e mai rapid (fără roundtrip la Azure), mai ieftin, și 100% consecvent,
indiferent cât de bine ar respecta GPT o regulă din system prompt.

NU e un filtru exhaustiv de moderare a conținutului (ar fi un serviciu
separat, mult mai complex, cu ML) — acoperă DOAR cele mai comune injurii/
vulgarități în limba română (+ câteva echivalente uzuale în engleză),
suficient pentru cazul de utilizare real: un user frustrat care înjură
asistentul, nu detectarea oricărei forme de conținut toxic.
"""

from __future__ import annotations

import re
import unicodedata

# Rădăcini de cuvinte, NU forme flexionate complete — regexul de mai jos
# adaugă `\w*` după fiecare rădăcină, ca să prindă și flexiunile uzuale
# (ex. "prost" -> "proastă", "proștilor" etc.) fără o listă infinită.
_PROFANITY_ROOTS = [
    "pul[aă]",
    "pizd[aă]",
    "muie",
    "fut[eu]?",
    "c[au]cat",
    "labagi",
    "curv[aă]",
    "jigodi",
    "nenorocit",
    "handicapat",
    "retardat",
    "prost",
    "proast",
    "idiot",
    "imbecil",
    "cretin",
    "tampit",
    "fuck",
    "shit",
    "bitch",
    "asshole",
]

_PROFANITY_PATTERN = re.compile(r"\b(?:" + "|".join(_PROFANITY_ROOTS) + r")\w*", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Lowercase + elimină diacriticele — ca "proastă"/"proasta" sau
    "pulă"/"pula" să fie tratate identic, indiferent cum tastează userul."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_diacritics = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_diacritics.lower()


def contains_profanity(text: str) -> bool:
    return bool(_PROFANITY_PATTERN.search(_normalize(text)))


# Mesaj determinist (NU generat de GPT — vezi docstring-ul modulului) —
# scurt, respectuos, fără ton moralizator, cere reformularea fără să
# repete/citeze limbajul jignitor primit.
REPHRASE_REQUEST_ANSWER = (
    "Hai să păstrăm un ton respectuos, ca să te pot ajuta eficient — poți reformula, te rog?"
)
