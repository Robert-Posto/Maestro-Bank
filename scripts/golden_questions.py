#!/usr/bin/env python3
"""
scripts/golden_questions.py — Set de "golden questions" pentru orchestrator
(clasificare Support vs. MaestroAgent) + calitatea REALĂ a răspunsurilor
celor doi agenți — verificare LIVE, prin API-ul real (Gateway), cu Azure
OpenAI REAL, NU mock-uit.

De ce separat de suita pytest din ai-orchestrator-service/tests: acolo
LLM-ul e mock-uit deliberat (vezi docstring-ul acelor teste) — verifică
CABLAJUL (orchestrarea, tool-calling loop-ul, DTO-urile), nu judecata
reală a modelului. Scriptul ăsta face exact opusul: nu-i pasă de cablaj,
verifică dacă modelul REAL răspunde corect la întrebări reprezentative,
inclusiv scenarii multi-tură (continuitate de context) — exact genul de
bug pe care teste mock-uite nu-l pot prinde niciodată (vezi bug-ul
"Ce buffer?" care a dus la acest script).

Verificările de conținut sunt DELIBERAT permisive (căutăm concepte-cheie,
nu propoziții exacte) — răspunsul unui LLM variază puțin de la o rulare la
alta chiar la același prompt; scriptul verifică fapte/cifre-cheie, nu
formulare.

Rulare (din rădăcina proiectului, cu stack-ul deja pornit):

    docker compose exec auth-service python scripts/golden_questions.py

(auth-service, nu ai-orchestrator-service, fiindcă e singurul serviciu cu
./scripts montat — vezi docker-compose.yml; scriptul oricum vorbește doar
cu Gateway-ul, prin HTTP, ca orice client extern, nu cu auth-service direct.)

Cod de ieșire: 0 dacă toate întrebările au trecut, 1 dacă vreuna a eșuat
(util și ca gate manual înainte de un commit pe orchestrator/agenți).
"""

from __future__ import annotations

import asyncio
import os
import sys
import unicodedata
from dataclasses import dataclass, field

import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000")
TEST_EMAIL = os.getenv("GOLDEN_TEST_EMAIL", "golden.questions@maestrobank.dev")
TEST_PASSWORD = os.getenv("GOLDEN_TEST_PASSWORD", "GoldenTest123!")


def _normalize(text: str) -> str:
    """Fără diacritice, minuscule, cratime tratate ca spațiu — verificările
    de conținut nu trebuie să pice pentru "buget" vs "Buget", "economii"
    vs "economíi", sau "nu-ți permiți" vs "nu îți permiți" (contracție cu
    cratimă, formă complet normală în română)."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_diacritics = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_diacritics.lower().replace("-", " ")


def _contains_any(haystack: str, needles: list[str]) -> bool:
    normalized = _normalize(haystack)
    return any(_normalize(n) in normalized for n in needles)


@dataclass
class ClassifyCase:
    """Verifică DOAR clasificarea (POST /assistant/classify), fără să mai
    ceară un răspuns complet de la agent — mai ieftin, mai rapid, potrivit
    pentru un set mare de formulări diverse."""

    label: str
    message: str
    expected_agent: str
    allow_llm_fallback: bool = True


@dataclass
class ChatCase:
    """Verifică fluxul COMPLET (clasificare + răspunsul real al agentului)
    — `content_checks`: liste de sinonime, cel puțin unul TREBUIE să apară
    în răspuns (case/diacritice-insensitive)."""

    label: str
    message: str
    expected_agent: str
    content_checks: list[list[str]] = field(default_factory=list)


@dataclass
class MultiTurnCase:
    """Scenariu cu 2+ ture — verifică CONTINUITATEA (agentul corect rămâne
    angajat, cu context, la un follow-up ambiguu) sau un SWITCH real (cuvânt-
    cheie clar schimbă agentul la mijlocul conversației)."""

    label: str
    turns: list[tuple[str, str, list[list[str]]]]  # (message, expected_agent, content_checks)


CLASSIFY_CASES: list[ClassifyCase] = [
    ClassifyCase("buget explicit", "Vreau să-mi fac un buget pentru groceries", "spending_forecast"),
    ClassifyCase("cheltuit explicit", "Cât am cheltuit luna asta?", "spending_forecast"),
    ClassifyCase("imi permit explicit", "Îmi permit un city break de 2000 lei luna asta?", "spending_forecast"),
    ClassifyCase(
        "afford fara cuvant-cheie exact (regresie fallback LLM)",
        "Pot să-mi cumpăr un laptop de 3000 de lei luna asta?",
        "spending_forecast",
    ),
    ClassifyCase("card status", "Cardul meu e activ?", "support"),
    ClassifyCase(
        "cont de economii NU e buget (regresie cuvant 'economii')",
        "Vreau să deschid un cont de economii",
        "support",
    ),
    ClassifyCase("listare tranzactii, nu rezumat", "Ce tranzacții am făcut luna trecută?", "support"),
    ClassifyCase("schimb valutar", "Cât ar fi 100 RON în EUR?", "support"),
    ClassifyCase("salut generic", "Bună ziua", "support"),
    ClassifyCase("engleza - spend", "How much did I spend this month?", "spending_forecast"),
]

CHAT_CASES: list[ChatCase] = [
    ChatCase(
        "sold cont real",
        "Care este soldul contului meu curent?",
        "support",
        content_checks=[["RON", "lei"]],
    ),
    ChatCase(
        "status card real",
        "Cardul meu e activ?",
        "support",
        content_checks=[["activ", "blocat", "inghetat", "frozen"]],
    ),
    ChatCase(
        "cotatie schimb valutar reala",
        "Cât ar fi 100 RON în EUR?",
        "support",
        # Modelul variază formularea de la o rulare la alta ("curs BNR",
        # "Rata aplicată", "cotația aplicată" — toate observate live) —
        # grup larg, verifică doar că MENȚIONEAZĂ conceptul de curs/rată,
        # nu formularea exactă.
        content_checks=[["EUR"], ["rata", "curs", "bnr", "cotati"]],
    ),
    ChatCase(
        "tranzactii luna trecuta - foloseste tool-ul de perioada",
        "Ce tranzacții am făcut luna trecută?",
        "support",
        content_checks=[["luna trecuta", "nicio tranzactie", "tranzacti"]],
    ),
    ChatCase(
        "interval explicit de date",
        "Tranzacțiile de pe 15 august până pe 20",
        "support",
        content_checks=[["15 august", "20 august"]],
    ),
    ChatCase(
        "rezumat cheltuieli real",
        "Cât am cheltuit luna aceasta?",
        "spending_forecast",
        content_checks=[["lei", "ron"]],
    ),
    ChatCase(
        "afordabilitate cu verdict clar",
        "Îmi permit o vacanță de 2000 lei luna asta?",
        "spending_forecast",
        # "nu, nu ti permit" — forma reală, contractată ("nu-ți"), tratată
        # ca "nu ti" după _normalize (cratima -> spațiu). Grup larg, ca să
        # prindă atât un refuz cât și o aprobare — verdictul poate varia
        # legitim în funcție de soldul real al userului de test.
        content_checks=[["nu ti permit", "iti permit", "nu recoman", "poti"]],
    ),
    ChatCase(
        "credite - nu inventeaza sume",
        "Cât mai am de plătit la creditul meu?",
        "support",
        content_checks=[["credite", "credit"]],
    ),
    ChatCase(
        "puncte si recompense",
        "Câte puncte am acumulat?",
        "support",
        content_checks=[["punct"]],
    ),
]

MULTI_TURN_CASES: list[MultiTurnCase] = [
    MultiTurnCase(
        "bug raportat: follow-up ambiguu ('Ce buffer?') nu pierde contextul MaestroAgent",
        turns=[
            (
                "Îmi permit să cheltui 5000 lei pe o vacanță luna asta?",
                "spending_forecast",
                [["nu iti permit", "nu recoman"]],
            ),
            (
                "Ce buffer?",
                "spending_forecast",
                [["rezerva", "buffer", "neprevazut"]],
            ),
        ],
    ),
    MultiTurnCase(
        "switch real: cuvant-cheie clar schimba agentul de pe Support pe Maestro",
        turns=[
            ("Cardul meu e activ?", "support", [["activ", "blocat", "inghetat"]]),
            ("Cât am cheltuit luna asta?", "spending_forecast", [["lei", "ron"]]),
        ],
    ),
    MultiTurnCase(
        "continuitate Support: follow-up ambiguu NU sare la Maestro fara motiv",
        turns=[
            ("Cardul meu e activ?", "support", [["activ", "blocat", "inghetat"]]),
            # Fara niciun cuvant-cheie de buget — trebuie sa ramana Support,
            # nu sa fie interpretat gresit ca schimbare de agent.
            ("De ce anume?", "support", []),
        ],
    ),
]


@dataclass
class Result:
    label: str
    passed: bool
    detail: str


async def ensure_test_user(client: httpx.AsyncClient) -> str:
    """Login idempotent — înregistrează userul de test dacă nu există încă.
    Întoarce access_token-ul."""
    login = await client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if login.status_code == 200:
        return login.json()["access_token"]

    register = await client.post(
        "/api/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "first_name": "Golden",
            "last_name": "Questions",
            "phone_number": "+40700000000",
        },
    )
    if register.status_code not in (200, 201):
        print(f"EȘUAT: nu am putut înregistra userul de test -> HTTP {register.status_code}: {register.text}", file=sys.stderr)
        sys.exit(1)

    login = await client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    if login.status_code != 200:
        print(f"EȘUAT: login după înregistrare -> HTTP {login.status_code}: {login.text}", file=sys.stderr)
        sys.exit(1)
    return login.json()["access_token"]


async def classify(client: httpx.AsyncClient, headers: dict, message: str, allow_llm_fallback: bool) -> str:
    response = await client.post(
        "/api/ai/assistant/classify",
        json={"message": message, "allow_llm_fallback": allow_llm_fallback},
        headers=headers,
    )
    response.raise_for_status()
    return response.json()["agent"]


async def chat_with_agent(
    client: httpx.AsyncClient, headers: dict, agent: str, message: str, conversation_id: str | None
) -> tuple[str, str]:
    """Trimite mesajul către agentul dat, întoarce (answer, conversation_id)."""
    if agent == "spending_forecast":
        response = await client.post(
            "/api/ai/spending-forecast/chat",
            json={"message": message, "conversation_id": conversation_id},
            headers=headers,
        )
    else:
        response = await client.post(
            "/api/ai/support",
            json={"message": message, "conversation_id": conversation_id},
            headers=headers,
        )
    response.raise_for_status()
    body = response.json()
    return body["answer"], body["conversation_id"]


async def run_classify_case(client: httpx.AsyncClient, headers: dict, case: ClassifyCase) -> Result:
    agent = await classify(client, headers, case.message, case.allow_llm_fallback)
    passed = agent == case.expected_agent
    detail = f"clasificat={agent} (așteptat={case.expected_agent})"
    return Result(f"[classify] {case.label}", passed, detail)


async def run_chat_case(client: httpx.AsyncClient, headers: dict, case: ChatCase) -> Result:
    agent = await classify(client, headers, case.message, allow_llm_fallback=True)
    if agent != case.expected_agent:
        return Result(f"[chat] {case.label}", False, f"clasificat={agent} (așteptat={case.expected_agent}) — nu mai apelăm agentul")

    answer, _ = await chat_with_agent(client, headers, agent, case.message, conversation_id=None)
    missing = [group for group in case.content_checks if not _contains_any(answer, group)]
    passed = not missing
    detail = f"agent={agent} OK" if passed else f"agent={agent} OK, dar lipsesc din răspuns: {missing}\n    răspuns: {answer[:300]!r}"
    return Result(f"[chat] {case.label}", passed, detail)


async def run_multi_turn_case(client: httpx.AsyncClient, headers: dict, case: MultiTurnCase) -> Result:
    conversation_ids: dict[str, str | None] = {"support": None, "spending_forecast": None}
    last_agent: str | None = None
    details: list[str] = []

    for turn_index, (message, expected_agent, content_checks) in enumerate(case.turns, start=1):
        # Prima tură a scenariului: clasificare completă (hibridă). Turele
        # următoare: allow_llm_fallback=False DOAR dacă un agent e deja
        # angajat — exact logica din support.ts::askAgent.
        allow_llm_fallback = last_agent is None
        agent = await classify(client, headers, message, allow_llm_fallback)

        # "support" fără cuvânt-cheie clar, cu un agent deja angajat, NU e
        # o decizie fermă (vezi support.ts::askAgent) — rămânem pe agentul
        # angajat, exact ca frontend-ul.
        effective_agent = agent if (agent == "spending_forecast" or last_agent is None) else last_agent

        if effective_agent != expected_agent:
            details.append(f"tura {turn_index} ({message!r}): agent efectiv={effective_agent} (așteptat={expected_agent})")
            return Result(f"[multi-turn] {case.label}", False, "; ".join(details))

        answer, conv_id = await chat_with_agent(
            client, headers, effective_agent, message, conversation_ids[effective_agent]
        )
        conversation_ids[effective_agent] = conv_id
        last_agent = effective_agent

        missing = [group for group in content_checks if not _contains_any(answer, group)]
        if missing:
            details.append(f"tura {turn_index} ({message!r}): lipsesc din răspuns {missing} — răspuns: {answer[:300]!r}")
            return Result(f"[multi-turn] {case.label}", False, "; ".join(details))

        details.append(f"tura {turn_index}: agent={effective_agent} OK")

    return Result(f"[multi-turn] {case.label}", True, "; ".join(details))


async def main() -> None:
    async with httpx.AsyncClient(timeout=90.0, base_url=GATEWAY_URL) as client:
        print(f"Login/înregistrare user de test ({TEST_EMAIL})...")
        token = await ensure_test_user(client)
        headers = {"Authorization": f"Bearer {token}"}

        results: list[Result] = []

        print(f"\n{len(CLASSIFY_CASES)} cazuri de clasificare...")
        for case in CLASSIFY_CASES:
            result = await run_classify_case(client, headers, case)
            results.append(result)
            print(f"  {'OK ' if result.passed else 'FAIL'}  {result.label} — {result.detail}")

        print(f"\n{len(CHAT_CASES)} cazuri de chat complet (clasificare + răspuns real)...")
        for case in CHAT_CASES:
            result = await run_chat_case(client, headers, case)
            results.append(result)
            print(f"  {'OK ' if result.passed else 'FAIL'}  {result.label} — {result.detail}")

        print(f"\n{len(MULTI_TURN_CASES)} scenarii multi-tură (continuitate/switch)...")
        for case in MULTI_TURN_CASES:
            result = await run_multi_turn_case(client, headers, case)
            results.append(result)
            print(f"  {'OK ' if result.passed else 'FAIL'}  {result.label} — {result.detail}")

        passed_count = sum(1 for r in results if r.passed)
        total = len(results)
        print(f"\n{'=' * 60}\nRezultat: {passed_count}/{total} au trecut.")

        failed = [r for r in results if not r.passed]
        if failed:
            print("\nEȘUATE:")
            for r in failed:
                print(f"  - {r.label}: {r.detail}")
            sys.exit(1)

        print("Toate cazurile au trecut.")


if __name__ == "__main__":
    asyncio.run(main())
