"""Text-to-speech pentru citirea cu voce tare a răspunsurilor agenților
(MaestroAssistent + Support Agent) — vezi app/routers/speech.py.

De ce edge-tts, nu Azure OpenAI (ca restul agenților, vezi app/llm/azure_openai.py):
resursa Azure OpenAI shared, folosită de academy pentru chat/embeddings, NU are
niciun model TTS provizionat (confirmat live: `DeploymentNotFound` la orice
model TTS încercat) — noi nu avem acces admin pe resursa aia ca să adăugăm
unul. `edge-tts` e o bibliotecă gratuită care apelează serviciul online
public "Read Aloud" al Microsoft Edge — FĂRĂ cheie API, FĂRĂ deployment Azure,
și — important — FĂRĂ nicio dependență de vocile instalate local pe mașina
userului (spre deosebire de Web Speech API din browser, folosit ca fallback
dacă acest endpoint eșuează — vezi frontend/src/app/services/speech.service.ts).
"""

import logging

import edge_tts

logger = logging.getLogger("ai-orchestrator-service")

# Voce feminină română — "Neural", cea mai naturală disponibilă în
# catalogul Edge TTS pentru ro-RO (confirmat live: doar 2 voci ro-RO
# există, Alina=femeie și Emil=bărbat — vezi feedback userul, "voce de
# femeie"). Fixă, nu configurabilă per-request (fără nevoie reală acum).
_VOICE = "ro-RO-AlinaNeural"

# Puțin mai rar decât ritmul implicit — la cererea userului ("nu asa de
# repede"), consistent cu `utterance.rate` din fallback-ul browser.
_RATE = "-10%"

# Cap defensiv — un răspuns de agent tipic are câteva sute de caractere;
# 4000 acoperă generos orice răspuns real, fără să lăsăm endpoint-ul
# deschis la cereri arbitrar de mari (timp de generare, lățime de bandă).
MAX_TEXT_LENGTH = 4000


async def synthesize_speech(text: str) -> bytes:
    """Generează audio MP3 pentru `text`, în română, voce feminină.

    Ridică `edge_tts.exceptions`-urile brute mai departe — apelantul
    (app/routers/speech.py) le prinde generic și întoarce un 502 curat
    către frontend (care oricum cade automat pe Web Speech API din browser
    dacă acest apel eșuează, vezi speech.service.ts — nimic nu rămâne mut).
    """
    text = text.strip()[:MAX_TEXT_LENGTH]
    communicate = edge_tts.Communicate(text, _VOICE, rate=_RATE)

    chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.extend(chunk["data"])

    if not chunks:
        # S-a întâmplat (rar) ca serviciul Edge să întoarcă un stream gol
        # fără nicio eroare explicită — tratăm ca eșec, nu ca succes tăcut.
        raise RuntimeError("edge-tts nu a generat niciun audio.")

    return bytes(chunks)
