# Persistent Chat History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `ai-orchestrator-service` its own MongoDB and persist MaestroAgent/Support Agent conversations, so users can list, reopen, and delete past conversations from a "Conversații" card on both chat pages — replacing today's in-memory (MaestroAgent) and `sessionStorage` (Support) approaches.

**Architecture:** One new `conversations` collection (shared by both agents, distinguished by an `agent` field), owned by a brand-new `app/database.py` in `ai-orchestrator-service`. Both routers gain `/conversations` (list/get/delete) endpoints and change their `/chat` contract from client-sent `history` to a server-loaded `conversation_id`. The agents' own reasoning/tool-calling code (`agents/spending_forecast.py`, `agents/support.py`, `services/support_service.py`) is never touched — routers load history before calling them and persist the turn after, exactly as they do today except the history comes from Mongo instead of the request body.

**Tech Stack:** FastAPI, Motor (async MongoDB driver), Pydantic v2, Angular 22 signals, RxJS.

**Spec:** `docs/superpowers/specs/2026-08-26-persistent-chat-history-design.md`

## Global Constraints

- Money/dates: N/A to this feature (no monetary values).
- Every service owns its own MongoDB database — never reads another's. New db name: `ai_orchestrator_db`.
- `user_id` for conversation ownership comes ONLY from the verified JWT `sub` claim, never from client input.
- A resource owned by another user returns 404, not 403 (never confirms existence) — same rule as every other service.
- No migrations exist in this project — indexes are created idempotently in `lifespan`.
- Agents' existing history-truncation limits (`_MAX_HISTORY_MESSAGES` in each agent module) are untouched; this plan only changes where history comes from.
- Romanian-language UI text/comments; English code identifiers — matches the rest of the codebase.

---

## Task 1: Give `ai-orchestrator-service` a database

**Files:**
- Create: `backend/services/ai-orchestrator-service/app/database.py`
- Modify: `backend/services/ai-orchestrator-service/app/config.py`
- Modify: `backend/services/ai-orchestrator-service/app/main.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: `get_database() -> AsyncIOMotorDatabase`, `ping_database() -> bool`, `close_database_connection() -> None` (all in `app/database.py`, identical shape to every other service's `database.py` — e.g. `backend/services/budgets-service/app/database.py`).

- [ ] **Step 1: Create `app/database.py`**

```python
"""Conexiunea la MongoDB pentru ai-orchestrator-service.

Primul database.py al acestui serviciu — până acum era complet stateless
(vezi comentariile din app/models/spending_forecast.py și
app/models/support.py despre "fără memorie pe termen lung", o decizie
inversată explicit pentru persistența conversațiilor, vezi
docs/superpowers/specs/2026-08-26-persistent-chat-history-design.md).
Folosește exclusiv baza `ai_orchestrator_db`, colecția `conversations`
(vezi app/services/conversation_service.py).
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_url)
database: AsyncIOMotorDatabase = client.get_default_database()


def get_database() -> AsyncIOMotorDatabase:
    return database


async def ping_database() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False


async def close_database_connection() -> None:
    client.close()
```

- [ ] **Step 2: Add `mongo_url` to `app/config.py`**

Add this line inside the `Settings` class (anywhere near the top, alongside `jwt_secret`):

```python
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/ai_orchestrator_db")
```

- [ ] **Step 3: Add a `lifespan` to `app/main.py`**

Replace the full file content with:

```python
"""ai-orchestrator-service — locuiește agenții AI ai MaestroBank, peste
Azure OpenAI.

Doi agenți montați aici, fiecare cu propriul router/agent/tools:
  - Spending + Forecast Agent (vezi app/agents/spending_forecast.py) — RAG,
    forecast/affordability determinist, propose-not-execute pentru bugete.
  - Support Agent (vezi app/agents/support.py) — ajutor cont/card/tranzacții/
    tichete, propose-not-execute pentru scrierea unui tichet.

Niciunul dintre ei NU accesează MongoDB direct — toate datele de cont vin
prin API Gateway (vezi app/tools/*), exact ca un client extern (Angular)
ar face. Excepția e conversations_db (vezi app/database.py), care ține
DOAR istoricul conversațiilor, nu date financiare/de cont.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import close_database_connection, ping_database
from app.routers.speech import router as speech_router
from app.routers.spending_forecast import router as spending_forecast_router
from app.routers.support import router as support_router
from app.services.conversation_service import ensure_conversation_indexes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ai-orchestrator-service] %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_conversation_indexes()
    yield
    await close_database_connection()


app = FastAPI(title="MaestroBank AI Orchestrator Service", lifespan=lifespan)


@app.get("/health")
async def health_check():
    is_connected = await ping_database()
    return {
        "status": "ok" if is_connected else "error",
        "service": "ai-orchestrator-service",
        "database": "connected" if is_connected else "disconnected",
        "azure_openai_configured": settings.azure_openai_configured,
    }


app.include_router(spending_forecast_router)
app.include_router(support_router)
app.include_router(speech_router)
```

(`ensure_conversation_indexes` is created in Task 2 — this step will not run successfully until Task 2 is done; that's fine, they're committed together.)

- [ ] **Step 4: Add `MONGO_URL` to `docker-compose.yml`**

In the `ai-orchestrator-service` block, change this comment+line:

```yaml
      # Agentul NU accesează MongoDB — vorbește STRICT prin Gateway,
      # exact ca un client extern (Angular), propagând JWT-ul userului.
      - GATEWAY_URL=http://gateway:8000
```

to:

```yaml
      # Datele de cont/tranzacții tot vin STRICT prin Gateway (vezi
      # app/tools/*) — MONGO_URL de mai jos ține DOAR istoricul
      # conversațiilor (vezi app/database.py), nu date financiare.
      - GATEWAY_URL=http://gateway:8000
      - MONGO_URL=${MONGODB_URI_BASE}/ai_orchestrator_db?appName=maestrobank
```

- [ ] **Step 5: Rebuild and verify**

```bash
docker compose up -d --build ai-orchestrator-service
curl -s http://localhost:8080/api/system/health
```

Expected: the ai-orchestrator entry in the health response (or a direct `curl http://localhost:8008/health` if you want to bypass the gateway/system aggregate) shows `"database": "connected"`.

- [ ] **Step 6: Commit**

```bash
git add backend/services/ai-orchestrator-service/app/database.py backend/services/ai-orchestrator-service/app/config.py backend/services/ai-orchestrator-service/app/main.py docker-compose.yml
git commit -m "feat(ai-orchestrator): give the service its own MongoDB"
```

---

## Task 2: Conversation persistence layer (models + service)

**Files:**
- Create: `backend/services/ai-orchestrator-service/app/models/conversation.py`
- Create: `backend/services/ai-orchestrator-service/app/services/conversation_service.py`
- Test: `backend/services/ai-orchestrator-service/tests/test_conversation_service.py`
- Modify: `backend/services/ai-orchestrator-service/tests/conftest.py`

**Interfaces:**
- Consumes: `get_database()` from `app/database.py` (Task 1).
- Produces (used by Task 3/4/5 routers):
  - `ensure_conversation_indexes() -> None`
  - `list_conversations(user_id: str, agent: Literal["spending_forecast", "support"]) -> list[dict]`
  - `get_conversation(user_id: str, agent: str, conversation_id: str) -> dict` (raises `HTTPException` 400 on malformed id, 404 if missing/not owned)
  - `create_conversation(user_id: str, agent: str, first_message: str) -> dict`
  - `append_turn(conversation_id: ObjectId, user_content: str, assistant_content: str, assistant_response: dict) -> None`
  - `delete_conversation(user_id: str, agent: str, conversation_id: str) -> None`
  - `to_history_dicts(conversation: dict) -> list[dict]` — each dict is `{"role": ..., "content": ...}`
  - `ConversationSummary`, `ConversationDetail`, `to_summary(doc) -> ConversationSummary`, `to_detail(doc) -> ConversationDetail` (in `models/conversation.py`)

- [ ] **Step 1: Add the test-database fixture to `tests/conftest.py`**

Add this fixture anywhere in the file (it must run for every test, autouse):

```python
from motor.motor_asyncio import AsyncIOMotorClient

import app.database as db_module


@pytest.fixture(autouse=True)
async def fresh_database():
    db_module.client = AsyncIOMotorClient(settings.mongo_url)
    db_module.database = db_module.client.get_default_database()
    yield
    await db_module.database.conversations.delete_many({})
    db_module.client.close()
```

(This mirrors `backend/services/budgets-service/tests/conftest.py` exactly, plus a cleanup of the `conversations` collection so tests don't leak data into each other — the budgets one doesn't need this because its tests already clean up explicitly per-file; conversation tests below rely on this fixture instead, to keep test files shorter.)

- [ ] **Step 2: Write the failing tests — `tests/test_conversation_service.py`**

```python
"""
Rulare (cu stack-ul pornit prin `docker compose up`, bază de TEST separată):

    docker compose exec ai-orchestrator-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 httpx==0.27.2 -q
    docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest -q
"""

import pytest
from fastapi import HTTPException

from app.services import conversation_service

pytestmark = pytest.mark.asyncio

USER_ID = "68a0f0f0f0f0f0f0f0f0f0f0"
OTHER_USER_ID = "68a0f0f0f0f0f0f0f0f0f0f1"


async def test_create_conversation_sets_title_from_first_message():
    conversation = await conversation_service.create_conversation(USER_ID, "spending_forecast", "Îmi permit un city break de 2000 lei?")
    assert conversation["title"] == "Îmi permit un city break de 2000 lei?"
    assert conversation["agent"] == "spending_forecast"
    assert conversation["user_id"] == USER_ID
    assert conversation["messages"] == []


async def test_create_conversation_truncates_long_title():
    long_message = "a" * 80
    conversation = await conversation_service.create_conversation(USER_ID, "support", long_message)
    assert conversation["title"] == "a" * 50 + "…"


async def test_list_conversations_scoped_to_user_and_agent():
    await conversation_service.create_conversation(USER_ID, "spending_forecast", "primul mesaj")
    await conversation_service.create_conversation(USER_ID, "support", "alt agent")
    await conversation_service.create_conversation(OTHER_USER_ID, "spending_forecast", "alt user")

    mine = await conversation_service.list_conversations(USER_ID, "spending_forecast")
    assert len(mine) == 1
    assert mine[0]["title"] == "primul mesaj"


async def test_list_conversations_sorted_by_updated_at_desc():
    first = await conversation_service.create_conversation(USER_ID, "spending_forecast", "primul")
    second = await conversation_service.create_conversation(USER_ID, "spending_forecast", "al doilea")

    conversations = await conversation_service.list_conversations(USER_ID, "spending_forecast")
    assert [c["_id"] for c in conversations] == [second["_id"], first["_id"]]


async def test_get_conversation_returns_owned_conversation():
    created = await conversation_service.create_conversation(USER_ID, "support", "bună")
    fetched = await conversation_service.get_conversation(USER_ID, "support", str(created["_id"]))
    assert fetched["_id"] == created["_id"]


async def test_get_conversation_404_for_wrong_user():
    created = await conversation_service.create_conversation(USER_ID, "support", "bună")
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(OTHER_USER_ID, "support", str(created["_id"]))
    assert exc_info.value.status_code == 404


async def test_get_conversation_404_for_wrong_agent():
    created = await conversation_service.create_conversation(USER_ID, "support", "bună")
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(USER_ID, "spending_forecast", str(created["_id"]))
    assert exc_info.value.status_code == 404


async def test_get_conversation_400_for_malformed_id():
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(USER_ID, "support", "not-an-object-id")
    assert exc_info.value.status_code == 400


async def test_append_turn_adds_both_messages_and_bumps_updated_at():
    created = await conversation_service.create_conversation(USER_ID, "spending_forecast", "prima întrebare")
    original_updated_at = created["updated_at"]

    await conversation_service.append_turn(
        created["_id"], "prima întrebare", "răspunsul agentului", {"answer": "răspunsul agentului"}
    )

    reloaded = await conversation_service.get_conversation(USER_ID, "spending_forecast", str(created["_id"]))
    assert len(reloaded["messages"]) == 2
    assert reloaded["messages"][0] == {
        "role": "user",
        "content": "prima întrebare",
        "response": None,
        "created_at": reloaded["messages"][0]["created_at"],
    }
    assert reloaded["messages"][1]["role"] == "assistant"
    assert reloaded["messages"][1]["response"] == {"answer": "răspunsul agentului"}
    assert reloaded["updated_at"] >= original_updated_at


async def test_to_history_dicts_strips_response_and_created_at():
    created = await conversation_service.create_conversation(USER_ID, "spending_forecast", "întrebare")
    await conversation_service.append_turn(created["_id"], "întrebare", "răspuns", {"answer": "răspuns"})
    reloaded = await conversation_service.get_conversation(USER_ID, "spending_forecast", str(created["_id"]))

    history = conversation_service.to_history_dicts(reloaded)
    assert history == [
        {"role": "user", "content": "întrebare"},
        {"role": "assistant", "content": "răspuns"},
    ]


async def test_delete_conversation_removes_it():
    created = await conversation_service.create_conversation(USER_ID, "support", "de șters")
    await conversation_service.delete_conversation(USER_ID, "support", str(created["_id"]))

    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.get_conversation(USER_ID, "support", str(created["_id"]))
    assert exc_info.value.status_code == 404


async def test_delete_conversation_404_for_wrong_user():
    created = await conversation_service.create_conversation(USER_ID, "support", "nu al tău")
    with pytest.raises(HTTPException) as exc_info:
        await conversation_service.delete_conversation(OTHER_USER_ID, "support", str(created["_id"]))
    assert exc_info.value.status_code == 404
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_conversation_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.conversation_service'` (or `ImportError`).

- [ ] **Step 4: Implement `app/services/conversation_service.py`**

```python
"""Persistență pentru conversațiile MaestroAgent (spending_forecast) și
Support Agent — un document Mongo per conversație, mesajele embedded
(conversațiile sunt scurte, deja plafonate la 40 de ture de fiecare agent
— vezi _MAX_HISTORY_MESSAGES în app/agents/spending_forecast.py și
app/agents/support.py). Vezi
docs/superpowers/specs/2026-08-26-persistent-chat-history-design.md.

Ambii agenți își păstrează logica de reasoning/tool-calling neschimbată —
routerele (app/routers/spending_forecast.py, app/routers/support.py) apelează
funcțiile de aici ÎNAINTE (încarcă istoricul) și DUPĂ (salvează tura) fiecare
apel de chat, fără să modifice deloc agenții.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status

from app.database import get_database

Agent = Literal["spending_forecast", "support"]

_TITLE_MAX_LENGTH = 50


def _make_title(first_message: str) -> str:
    """Titlu determinist, fără niciun apel LLM suplimentar doar pentru
    cosmetică — primele caractere ale primului mesaj, ca la orice chat
    client simplu."""
    trimmed = first_message.strip()
    if len(trimmed) <= _TITLE_MAX_LENGTH:
        return trimmed
    return trimmed[:_TITLE_MAX_LENGTH].rstrip() + "…"


async def ensure_conversation_indexes() -> None:
    db = get_database()
    await db.conversations.create_index([("user_id", 1), ("agent", 1), ("updated_at", -1)])


async def list_conversations(user_id: str, agent: Agent) -> list[dict]:
    db = get_database()
    cursor = db.conversations.find(
        {"user_id": user_id, "agent": agent},
        {"title": 1, "updated_at": 1},
    ).sort("updated_at", -1)
    return await cursor.to_list(length=200)


async def get_conversation(user_id: str, agent: Agent, conversation_id: str) -> dict:
    db = get_database()
    try:
        object_id = ObjectId(conversation_id)
    except InvalidId as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID de conversație invalid.") from exc

    doc = await db.conversations.find_one({"_id": object_id})
    if doc is None or doc["user_id"] != user_id or doc["agent"] != agent:
        # 404, NU 403 — nu confirmăm că o conversație a altcuiva există.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversația nu există.")
    return doc


async def create_conversation(user_id: str, agent: Agent, first_message: str) -> dict:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "agent": agent,
        "title": _make_title(first_message),
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    result = await db.conversations.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def append_turn(conversation_id: ObjectId, user_content: str, assistant_content: str, assistant_response: dict) -> None:
    db = get_database()
    now = datetime.now(timezone.utc)
    await db.conversations.update_one(
        {"_id": conversation_id},
        {
            "$push": {
                "messages": {
                    "$each": [
                        {"role": "user", "content": user_content, "response": None, "created_at": now},
                        {
                            "role": "assistant",
                            "content": assistant_content,
                            "response": assistant_response,
                            "created_at": now,
                        },
                    ]
                }
            },
            "$set": {"updated_at": now},
        },
    )


async def delete_conversation(user_id: str, agent: Agent, conversation_id: str) -> None:
    # Reutilizează get_conversation pentru verificarea de proprietate (400
    # pe ID invalid, 404 dacă nu există/nu e a userului) — un singur loc
    # de adevăr pentru regula asta.
    conversation = await get_conversation(user_id, agent, conversation_id)
    db = get_database()
    await db.conversations.delete_one({"_id": conversation["_id"]})


def to_history_dicts(conversation: dict) -> list[dict[str, Any]]:
    """Mesajele stocate, în forma minimă cerută de agenți ca istoric
    ({role, content}) — fără `response`/`created_at`, pe care agenții nu le
    așteaptă (vezi ChatHistoryMessage din app/models/spending_forecast.py,
    ChatMessage din app/models/support.py)."""
    return [{"role": m["role"], "content": m["content"]} for m in conversation["messages"]]
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_conversation_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Create `app/models/conversation.py`**

(No test needed for this file alone — it's pure DTOs, exercised indirectly by Task 4/5's router tests.)

```python
"""DTO-uri pentru endpoint-urile de conversații (listă/detaliu/ștergere) —
comune ambilor agenți, vezi app/services/conversation_service.py."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ConversationSummary(BaseModel):
    id: str
    title: str
    updated_at: datetime


class ConversationMessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    response: dict[str, Any] | None = None
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageOut]


def to_summary(doc: dict) -> ConversationSummary:
    return ConversationSummary(id=str(doc["_id"]), title=doc["title"], updated_at=doc["updated_at"])


def to_detail(doc: dict) -> ConversationDetail:
    return ConversationDetail(
        id=str(doc["_id"]),
        title=doc["title"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        messages=[ConversationMessageOut(**m) for m in doc["messages"]],
    )
```

- [ ] **Step 7: Commit**

```bash
git add backend/services/ai-orchestrator-service/app/models/conversation.py backend/services/ai-orchestrator-service/app/services/conversation_service.py backend/services/ai-orchestrator-service/tests/test_conversation_service.py backend/services/ai-orchestrator-service/tests/conftest.py
git commit -m "feat(ai-orchestrator): add conversation persistence layer"
```

---

## Task 3: `CurrentUserId` dependency for Support Agent's router

**Files:**
- Modify: `backend/services/ai-orchestrator-service/app/security.py`
- Test: `backend/services/ai-orchestrator-service/tests/test_security.py`

**Interfaces:**
- Produces: `CurrentUserId` (a `Depends(...)` resolving to `str`) — used ONLY by the new conversation endpoints and the modified `/support` chat route (Task 5), never passed into the agent/tools.

**Why this task exists:** `support.py`'s existing `get_authorization` dependency deliberately returns only the raw header, not a decoded `user_id` — by design, so the agent's tool-calling logic never makes authorization decisions off a client-derived value (see the comment already in `security.py`). Persisting conversations needs a `user_id` purely as a storage/ownership key, a different concern from that — so this adds a second, narrow dependency instead of changing the existing one's meaning.

- [ ] **Step 1: Write the failing test**

Open `tests/test_security.py` and add (check the file's existing imports first — it already imports `make_token` from `conftest`; add these test functions at the end):

```python
from app.security import get_current_user_id


async def test_get_current_user_id_returns_sub_claim():
    user_id = "68a0f0f0f0f0f0f0f0f0f0f0"
    token = make_token(user_id)
    result = await get_current_user_id(authorization=f"Bearer {token}")
    assert result == user_id


async def test_get_current_user_id_rejects_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(authorization=None)
    assert exc_info.value.status_code == 401


async def test_get_current_user_id_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(authorization="Bearer not-a-real-token")
    assert exc_info.value.status_code == 401
```

Make sure `HTTPException` and `pytest` are imported at the top of the test file (add `from fastapi import HTTPException` if it's not already there).

- [ ] **Step 2: Run to verify it fails**

```bash
docker compose exec ai-orchestrator-service python -m pytest tests/test_security.py -k get_current_user_id -v
```

Expected: FAIL with `ImportError: cannot import name 'get_current_user_id'`.

- [ ] **Step 3: Add the dependency to `app/security.py`**

Add this at the end of the file (after the existing `get_authorization`/`CurrentAuthorization`):

```python
# --- Persistență de conversații (vezi app/services/conversation_service.py) -
# user_id folosit STRICT ca cheie de proprietate a unei conversații stocate
# — NU e trecut agentului/tool-urilor (acelea rămân pe get_authorization de
# mai sus, neschimbat) — deci nu încalcă principiul de mai sus.
async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lipsește header-ul Authorization: Bearer <token>.",
        )
    token = authorization.split(" ", 1)[1]
    payload = _decode(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid: lipsește subiectul.")
    return user_id


CurrentUserId = Depends(get_current_user_id)
```

- [ ] **Step 4: Run to verify it passes**

```bash
docker compose exec ai-orchestrator-service python -m pytest tests/test_security.py -v
```

Expected: all tests PASS (the 3 new ones plus every existing test in the file, unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/services/ai-orchestrator-service/app/security.py backend/services/ai-orchestrator-service/tests/test_security.py
git commit -m "feat(ai-orchestrator): add CurrentUserId dependency for conversation ownership"
```

---

## Task 4: MaestroAgent (`spending_forecast`) — conversations endpoints + `/chat` contract change

**Files:**
- Modify: `backend/services/ai-orchestrator-service/app/models/spending_forecast.py`
- Modify: `backend/services/ai-orchestrator-service/app/routers/spending_forecast.py`
- Modify: `backend/services/ai-orchestrator-service/tests/conftest.py` (gains the shared `mock_tools` fixture, moved from `test_agent.py`)
- Modify: `backend/services/ai-orchestrator-service/tests/test_agent.py` (loses its now-local `mock_tools`/fixture constants; two history tests rewritten)
- Test: `backend/services/ai-orchestrator-service/tests/test_spending_forecast_conversations.py`

**Interfaces:**
- Consumes: `conversation_service.*` (Task 2), `ConversationSummary`/`ConversationDetail`/`to_summary`/`to_detail` (Task 2), `CurrentAuth`/`AuthContext` (already exists).
- Produces: `POST /spending-forecast/chat` now takes `{message, conversation_id}` and returns a response with `conversation_id` populated; `GET/DELETE /spending-forecast/conversations[/{id}]`.

- [ ] **Step 1: Update `app/models/spending_forecast.py`**

Replace the `ChatRequest` class:

```python
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Istoricul nu mai vine de la client (vezi conversation_id) — serverul
    # îl încarcă din Mongo, prin app/services/conversation_service.py.
    # None = pornește o conversație nouă (titlu din acest mesaj).
    conversation_id: str | None = None
```

(This removes the `history` field entirely — nothing else in this file or `agents/spending_forecast.py` reads `ChatRequest.history` directly; the router builds `history` itself now, from Mongo.)

Add a field to `SpendingForecastResponse` (keep every other field as-is, just add this one — put it near the top, after `requested_amount_minor`):

```python
    # Setat de router DUPĂ ce agent.handle_message întoarce (vezi
    # routers/spending_forecast.py) — niciodată de agentul însuși.
    conversation_id: str = ""
```

`ChatHistoryMessage` stays exactly as-is (still used internally by the router and by `agent.handle_message`).

- [ ] **Step 2: Write the failing tests — `tests/test_spending_forecast_conversations.py`**

`test_agent.py` (already in the repo) mocks Azure OpenAI by monkeypatching `app.agents.spending_forecast.chat_completion` directly (a module-level function, not an injected client object) and drives everything through real HTTP calls via the `client`/`mock_tools` fixtures already in that file. Match that pattern exactly — do not invent a second mocking style.

```python
"""
Rulare: vezi header-ul tests/test_conversation_service.py pentru comanda
completă (aceeași bază de test, `ai_orchestrator_db_test`).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from app.config import settings

pytestmark = pytest.mark.asyncio


def make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


USER_ID = "68a0f0f0f0f0f0f0f0f0f0f0"
OTHER_USER_ID = "68a0f0f0f0f0f0f0f0f0f0f1"


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


def _fake_chat_completion(answer: str):
    async def fake(messages, tools=None):
        return FakeMessage(content=answer)

    return fake


async def test_chat_without_conversation_id_creates_one(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("Bună ziua!"))

    response = await client.post(
        "/spending-forecast/chat", json={"message": "Bună"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["answer"] == "Bună ziua!"


async def test_chat_reuses_existing_conversation(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("Primul răspuns"))
    first = await client.post(
        "/spending-forecast/chat", json={"message": "Primul mesaj"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    conversation_id = first.json()["conversation_id"]

    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("Al doilea răspuns"))
    second = await client.post(
        "/spending-forecast/chat",
        json={"message": "Al doilea mesaj", "conversation_id": conversation_id},
        headers={"Authorization": f"Bearer {make_token(USER_ID)}"},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    detail = await client.get(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    contents = [m["content"] for m in detail.json()["messages"]]
    assert contents == ["Primul mesaj", "Primul răspuns", "Al doilea mesaj", "Al doilea răspuns"]


async def test_list_conversations_returns_only_mine(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("a"))
    await client.post("/spending-forecast/chat", json={"message": "a mea"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"})

    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("b"))
    await client.post(
        "/spending-forecast/chat", json={"message": "a altcuiva"}, headers={"Authorization": f"Bearer {make_token(OTHER_USER_ID)}"}
    )

    response = await client.get("/spending-forecast/conversations", headers={"Authorization": f"Bearer {make_token(USER_ID)}"})
    assert [c["title"] for c in response.json()] == ["a mea"]


async def test_get_conversation_404_for_other_user(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("privat"))
    created = await client.post(
        "/spending-forecast/chat", json={"message": "privat"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    conversation_id = created.json()["conversation_id"]

    response = await client.get(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(OTHER_USER_ID)}"}
    )
    assert response.status_code == 404


async def test_delete_conversation(client: AsyncClient, monkeypatch, mock_tools):
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _fake_chat_completion("de șters"))
    created = await client.post(
        "/spending-forecast/chat", json={"message": "de șters"}, headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    conversation_id = created.json()["conversation_id"]

    delete_response = await client.delete(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/spending-forecast/conversations/{conversation_id}", headers={"Authorization": f"Bearer {make_token(USER_ID)}"}
    )
    assert get_response.status_code == 404
```

`mock_tools` is the autouse-able fixture already defined at the top of `test_agent.py` — it lives in that file, not in `conftest.py`, so pytest can only see it for THIS new test file if it's either (a) moved to `conftest.py`, or (b) this new test file is testing through the same session and pytest's fixture discovery picks up `test_agent.py`'s fixture because it's a plain module-level fixture, which pytest does NOT share across test files by default. **Move the `mock_tools` fixture (and its `ACCOUNT`/`SPENDING_SUMMARY`/`FORECAST`/`SUBSCRIPTIONS`/`CASH_FLOW`/`BUDGETS` constants it closes over) from `test_agent.py` into `conftest.py`** as part of this step, then delete them from `test_agent.py` and rely on the shared one from `conftest.py` there too (pytest auto-discovers fixtures from `conftest.py` for every test file in the directory, no import needed).

- [ ] **Step 3: Rewrite the two `test_agent.py` tests that send `history` directly in the request body**

`test_agent.py` has two existing tests — `test_conversation_history_is_forwarded_to_the_model` and `test_conversation_history_is_truncated_defensively` — that construct history by putting a `"history": [...]` key straight into the POST body. That field no longer exists on `ChatRequest` after Step 1, so these two tests are now testing a contract that's gone. Replace both (same file, same names, same intent — just built through real conversation turns instead of injected history):

```python
async def test_conversation_history_is_forwarded_to_the_model(client: AsyncClient, monkeypatch, mock_tools):
    """Istoricul dintr-o conversație salvată ajunge efectiv în mesajele
    către GPT — fără el, agentul "uită" tot ce s-a discutat anterior.
    Istoricul vine acum din Mongo, nu din request body — simulăm asta cu
    un prim tur real, apoi al doilea cu `conversation_id` din primul."""
    first_responses = [FakeMessage(content="Estimăm că rămâi cu 26.487,90 lei.")]
    monkeypatch.setattr("app.agents.spending_forecast.chat_completion", _make_fake_chat_completion(first_responses))
    first = await client.post(
        "/spending-forecast/chat",
        json={"message": "Cu cât estimezi că rămân la finalul lunii?"},
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    conversation_id = first.json()["conversation_id"]

    captured: list = []
    monkeypatch.setattr(
        "app.agents.spending_forecast.chat_completion",
        _make_fake_chat_completion([FakeMessage(content="Da, ține minte.")], captured),
    )
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "Deci cât mi-ai zis că rămâne?", "conversation_id": conversation_id},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    sent_messages = captured[0]
    contents = [m["content"] for m in sent_messages]
    assert any("26.487,90 lei" in c for c in contents), "istoricul trebuie să ajungă în promptul trimis modelului"
    assert contents[-1] == "Deci cât mi-ai zis că rămâne?"


async def test_conversation_history_is_truncated_defensively(client: AsyncClient, monkeypatch, mock_tools):
    """Chiar dacă o conversație salvată ar acumula foarte multe mesaje,
    serverul trunchiază la ultimele — nu lasă contextul să crească
    nemărginit. Populăm o conversație lungă direct prin conversation_service
    (mai simplu decât 39 de tururi HTTP reale), apoi verificăm turul următor."""
    from app.services import conversation_service

    conversation = await conversation_service.create_conversation(
        "68a0f0f0f0f0f0f0f0f0f0f0", "spending_forecast", "mesaj 0"
    )
    for i in range(1, 40):
        await conversation_service.append_turn(
            conversation["_id"], f"mesaj {i}", f"răspuns {i}", {"answer": f"răspuns {i}"}
        )

    captured: list = []
    monkeypatch.setattr(
        "app.agents.spending_forecast.chat_completion", _make_fake_chat_completion([FakeMessage(content="OK")], captured)
    )
    response = await client.post(
        "/spending-forecast/chat",
        json={"message": "ultima întrebare", "conversation_id": str(conversation["_id"])},
        headers={"Authorization": f"Bearer {make_token()}"},
    )

    assert response.status_code == 200
    sent_messages = captured[0]
    history_contents = [
        m["content"] for m in sent_messages if m["content"].startswith("mesaj ") or m["content"].startswith("răspuns ")
    ]
    assert len(history_contents) < 78  # 39 tururi × 2 mesaje = 78 dacă n-ar trunchia deloc
    assert history_contents[-1] == "răspuns 39"  # cel mai recent, păstrat
```

Both replacements reuse `make_token`, `FakeMessage`, and `_make_fake_chat_completion` already defined at the top of `test_agent.py` — no new imports needed beyond what Step 2 already added to `conftest.py`.

- [ ] **Step 4: Run to verify failure**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_spending_forecast_conversations.py -v
```

Expected: FAIL — `conversation_id` not a valid field yet / 404 on `/spending-forecast/conversations` (route doesn't exist).

- [ ] **Step 5: Implement the router changes**

Replace `app/routers/spending_forecast.py` in full:

```python
"""Rute protejate (JWT) ale agentului Spending + Forecast.

Extern (prin Gateway) devin:
  POST   /api/ai/spending-forecast/chat
  POST   /api/ai/spending-forecast/actions/confirm
  GET    /api/ai/spending-forecast/conversations
  GET    /api/ai/spending-forecast/conversations/{conversation_id}
  DELETE /api/ai/spending-forecast/conversations/{conversation_id}
"""

from fastapi import APIRouter, HTTPException, status

from app.agents import spending_forecast as agent
from app.models.conversation import ConversationDetail, ConversationSummary, to_detail, to_summary
from app.models.spending_forecast import (
    ChatHistoryMessage,
    ChatRequest,
    ConfirmActionRequest,
    ConfirmActionResponse,
    SpendingForecastResponse,
)
from app.security import AuthContext, CurrentAuth
from app.services import budget_actions_service, conversation_service
from app.tools.errors import ToolError

router = APIRouter(prefix="/spending-forecast", tags=["spending-forecast"])

_AGENT: conversation_service.Agent = "spending_forecast"


@router.post("/chat", response_model=SpendingForecastResponse)
async def chat(payload: ChatRequest, auth: AuthContext = CurrentAuth):
    if payload.conversation_id:
        conversation = await conversation_service.get_conversation(auth.user_id, _AGENT, payload.conversation_id)
    else:
        conversation = await conversation_service.create_conversation(auth.user_id, _AGENT, payload.message)

    history = [ChatHistoryMessage(**m) for m in conversation_service.to_history_dicts(conversation)]
    response = await agent.handle_message(auth, payload.message, history=history)

    await conversation_service.append_turn(conversation["_id"], payload.message, response.answer, response.model_dump())
    response.conversation_id = str(conversation["_id"])
    return response


@router.post("/actions/confirm", response_model=ConfirmActionResponse)
async def confirm_action(payload: ConfirmActionRequest, auth: AuthContext = CurrentAuth):
    """Execuția REALĂ a unei acțiuni de buget PROPUSE anterior de agent
    (vezi `pending_action` din răspunsul de chat) — apelată STRICT după ce
    userul apasă explicit "Confirmă" în UI. NU trece prin GPT — e un apel
    determinist, direct, către budgets-service prin Gateway.
    """
    try:
        result = await budget_actions_service.execute_confirmed_action(payload.type, payload.payload, auth.authorization_header)
    except ToolError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ConfirmActionResponse(**result)


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(auth: AuthContext = CurrentAuth):
    docs = await conversation_service.list_conversations(auth.user_id, _AGENT)
    return [to_summary(d) for d in docs]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, auth: AuthContext = CurrentAuth):
    doc = await conversation_service.get_conversation(auth.user_id, _AGENT, conversation_id)
    return to_detail(doc)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, auth: AuthContext = CurrentAuth):
    await conversation_service.delete_conversation(auth.user_id, _AGENT, conversation_id)
```

- [ ] **Step 6: Run to verify the tests pass**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_spending_forecast_conversations.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run the full existing test file for this agent to confirm nothing broke**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_agent.py tests/test_prompt.py tests/test_relevant_cards.py -v
```

Expected: all PASS — including the two rewritten history tests from Step 3.

- [ ] **Step 8: Commit**

```bash
git add backend/services/ai-orchestrator-service/app/models/spending_forecast.py backend/services/ai-orchestrator-service/app/routers/spending_forecast.py backend/services/ai-orchestrator-service/tests/test_spending_forecast_conversations.py backend/services/ai-orchestrator-service/tests/test_agent.py backend/services/ai-orchestrator-service/tests/conftest.py
git commit -m "feat(ai-orchestrator): persist MaestroAgent conversations, replace client-sent history with conversation_id"
```

---

## Task 5: Support Agent — conversations endpoints + `/chat` contract change

**Files:**
- Modify: `backend/services/ai-orchestrator-service/app/models/support.py`
- Modify: `backend/services/ai-orchestrator-service/app/routers/support.py`
- Test: `backend/services/ai-orchestrator-service/tests/test_support_conversations.py`

**Interfaces:**
- Consumes: `conversation_service.*` (Task 2), `CurrentUserId` (Task 3), `CurrentAuthorization` (existing), `FakeLLMClient`/`support_auth_header` fixtures (existing, from `conftest.py`).
- Produces: `POST /support` now takes `{message, conversation_id, pending_action}` (no more client-sent `history`) and returns `conversation_id`; `GET/DELETE /support/conversations[/{id}]`.

**Why `handle_chat`'s signature doesn't change:** `support_service.handle_chat(payload, authorization)` reads `payload.history` internally. Rather than touching that function (and every existing test that constructs a `ChatRequest`), the router builds a copy of the incoming payload with `history` populated from Mongo before calling it — `handle_chat` itself never learns persistence exists.

- [ ] **Step 1: Update `app/models/support.py`**

Add one field to `ChatRequest` (keep `message`, `history`, `pending_action` exactly as they are):

```python
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    # Populat de router DIN Mongo (vezi conversation_service.to_history_dicts),
    # NU de client — clientul trimite conversation_id în loc (mai jos).
    # Rămâne aici (nu doar parametru de funcție, ca la spending_forecast)
    # pentru că support_service.handle_chat citește payload.history direct.
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
    pending_action: PendingAction | None = None
    # None = pornește o conversație nouă (titlu din acest mesaj).
    conversation_id: str | None = None
```

Add one field to `ChatResponse`:

```python
class ChatResponse(BaseModel):
    answer: str
    intent: Intent
    context: dict[str, Any] = Field(default_factory=dict)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Setat de router DUPĂ ce support_service.handle_chat întoarce — niciodată
    # de handle_chat însuși.
    conversation_id: str = ""
```

- [ ] **Step 2: Write the failing tests — `tests/test_support_conversations.py`**

The verified pattern for driving the Support Agent through a real HTTP request with a mocked LLM (see `tests/test_security.py::test_profanity_gets_deterministic_reply_without_calling_llm`) is monkeypatching the `.complete` method on the shared `_default_llm_client` instance living in `app.agents.support` — NOT `app.routers.support`, and NOT swapping the whole client object. (`test_support_agent.py`'s tests call `support_service.handle_chat` directly with an injected `llm_client=` argument, bypassing the router entirely — that pattern doesn't exercise the HTTP layer this task changes, so it's not the one to copy here.)

```python
"""
Rulare: vezi header-ul tests/test_conversation_service.py.
"""

import pytest

pytestmark = pytest.mark.asyncio


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = []


def _fake_complete(answer: str):
    async def complete(messages, tools):
        return _FakeMessage(answer)

    return complete


async def test_chat_without_conversation_id_creates_one(client, support_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Bună ziua!"))

    response = await client.post("/support", json={"message": "Bună"}, headers=support_auth_header)
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["answer"] == "Bună ziua!"


async def test_chat_reuses_existing_conversation(client, support_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Primul răspuns"))
    first = await client.post("/support", json={"message": "Primul mesaj"}, headers=support_auth_header)
    conversation_id = first.json()["conversation_id"]

    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("Al doilea răspuns"))
    second = await client.post(
        "/support", json={"message": "Al doilea mesaj", "conversation_id": conversation_id}, headers=support_auth_header
    )
    assert second.json()["conversation_id"] == conversation_id

    detail = await client.get(f"/support/conversations/{conversation_id}", headers=support_auth_header)
    contents = [m["content"] for m in detail.json()["messages"]]
    assert contents == ["Primul mesaj", "Primul răspuns", "Al doilea mesaj", "Al doilea răspuns"]


async def test_list_conversations_returns_only_mine(client, support_auth_header, support_other_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("a"))
    await client.post("/support", json={"message": "a mea"}, headers=support_auth_header)

    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("b"))
    await client.post("/support", json={"message": "a altcuiva"}, headers=support_other_auth_header)

    response = await client.get("/support/conversations", headers=support_auth_header)
    titles = [c["title"] for c in response.json()]
    assert titles == ["a mea"]


async def test_get_conversation_404_for_other_user(client, support_auth_header, support_other_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("privat"))
    created = await client.post("/support", json={"message": "privat"}, headers=support_auth_header)
    conversation_id = created.json()["conversation_id"]

    response = await client.get(f"/support/conversations/{conversation_id}", headers=support_other_auth_header)
    assert response.status_code == 404


async def test_delete_conversation(client, support_auth_header, monkeypatch):
    monkeypatch.setattr("app.agents.support._default_llm_client.complete", _fake_complete("de șters"))
    created = await client.post("/support", json={"message": "de șters"}, headers=support_auth_header)
    conversation_id = created.json()["conversation_id"]

    delete_response = await client.delete(f"/support/conversations/{conversation_id}", headers=support_auth_header)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/support/conversations/{conversation_id}", headers=support_auth_header)
    assert get_response.status_code == 404
```

`client`, `support_auth_header`, and `support_other_auth_header` are the shared fixtures already in `conftest.py` (Task 2 research confirmed all three exist there) — no new fixtures needed for this file.

- [ ] **Step 3: Run to verify failure**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_support_conversations.py -v
```

Expected: FAIL — no `/support/conversations` route yet, `conversation_id` missing from response.

- [ ] **Step 4: Implement the router changes**

Replace `app/routers/support.py` in full:

```python
"""Endpoint-urile Support Agent.

Intern: POST /support, GET/DELETE /support/conversations[/{id}]. Extern,
prin Gateway: POST /api/ai/support, GET/DELETE /api/ai/support/conversations[/{id}]
(vezi backend/gateway/app/routers/proxy.py — service="ai", internal_prefix="").

Authorization e validat AICI (defense in depth, ca la orice alt
microserviciu — vezi app/security.py) și propagat neschimbat de-a lungul
întregului flux, la fiecare tool call către Gateway.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from openai import APIError

from app.models.conversation import ConversationDetail, ConversationSummary, to_detail, to_summary
from app.models.support import ChatRequest, ChatResponse
from app.security import CurrentAuthorization, CurrentUserId
from app.services import conversation_service, support_service

logger = logging.getLogger("ai-orchestrator-service")

router = APIRouter(prefix="/support", tags=["support-agent"])

_AGENT: conversation_service.Agent = "support"


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, authorization: str = CurrentAuthorization, user_id: str = CurrentUserId
) -> ChatResponse:
    if payload.conversation_id:
        conversation = await conversation_service.get_conversation(user_id, _AGENT, payload.conversation_id)
    else:
        conversation = await conversation_service.create_conversation(user_id, _AGENT, payload.message)

    # ChatRequest(message=..., history=...), NU payload.model_copy(update=...)
    # — model_copy nu re-validează, deci `history` ar rămâne o listă de
    # dict-uri brute, iar run_support_agent (app/agents/support.py:304) face
    # acces pe atribut (`m.role`, `m.content`), nu pe cheie de dict; ar
    # arunca AttributeError. Constructorul explicit forțează validarea
    # Pydantic normală, care transformă dict-urile în ChatMessage.
    history_dicts = conversation_service.to_history_dicts(conversation)
    payload_with_history = ChatRequest(
        message=payload.message,
        history=history_dicts,
        pending_action=payload.pending_action,
        conversation_id=payload.conversation_id,
    )

    try:
        response = await support_service.handle_chat(payload_with_history, authorization)
    except RuntimeError as exc:
        # Ridicată de app/llm/azure_openai.py când AZURE_OPENAI_ENDPOINT /
        # AZURE_OPENAI_API_KEY lipsesc — răspuns curat, NU un 500 brut.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except APIError as exc:
        # Eroare REALĂ de la Azure (endpoint/deployment greșit, cheie
        # invalidă, model indisponibil etc.) — nu propagăm mesajul brut al
        # providerului (poate conține detalii interne), doar tipul erorii.
        logger.error("Azure OpenAI a răspuns cu eroare: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Azure OpenAI a răspuns cu eroare ({type(exc).__name__}). Verifică endpoint/deployment/cheia din .env.",
        ) from exc

    await conversation_service.append_turn(conversation["_id"], payload.message, response.answer, response.model_dump())
    response.conversation_id = str(conversation["_id"])
    return response


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(user_id: str = CurrentUserId):
    docs = await conversation_service.list_conversations(user_id, _AGENT)
    return [to_summary(d) for d in docs]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, user_id: str = CurrentUserId):
    doc = await conversation_service.get_conversation(user_id, _AGENT, conversation_id)
    return to_detail(doc)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user_id: str = CurrentUserId):
    await conversation_service.delete_conversation(user_id, _AGENT, conversation_id)
```


- [ ] **Step 5: Run to verify the tests pass**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_support_conversations.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run the full existing Support Agent test suite to confirm nothing broke**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest tests/test_support_agent.py tests/test_confirmation_flow.py tests/test_security.py -v
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/ai-orchestrator-service/app/models/support.py backend/services/ai-orchestrator-service/app/routers/support.py backend/services/ai-orchestrator-service/tests/test_support_conversations.py
git commit -m "feat(ai-orchestrator): persist Support Agent conversations, replace client-sent history with conversation_id"
```

---

## Task 6: Run the FULL backend test suite once, before touching the frontend

**Files:** none (verification-only task).

- [ ] **Step 1: Run every test in the service**

```bash
docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest -q
```

Expected: all PASS. This is the last point where a backend regression is cheap to isolate — do not proceed to frontend work with a red suite.

- [ ] **Step 2: Update CLAUDE.md's per-service test table**

`ai-orchestrator-service` is no longer stateless — it now has a test database like the other six. In `CLAUDE.md`, find this line (under "Backend tests"):

```
Service → db_name: `auth-service`→`auth_db`, `accounts-service`→`accounts_db`, `transactions-service`→`tx_db`, `budgets-service`→`budgets_db`, `support-service`→`support_db`, `exchange-service`→`exchange_db`.
```

Change it to:

```
Service → db_name: `auth-service`→`auth_db`, `accounts-service`→`accounts_db`, `transactions-service`→`tx_db`, `budgets-service`→`budgets_db`, `support-service`→`support_db`, `exchange-service`→`exchange_db`, `ai-orchestrator-service`→`ai_orchestrator_db`.
```

Also find the line describing `verification-service`/`ai-orchestrator-service` as stateless (near "Per-service internal structure") and update it to note that `ai-orchestrator-service` now has a `database.py` for conversation history only (not account/financial data, which still comes exclusively through the Gateway) — `verification-service` remains the only fully stateless one.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: ai-orchestrator-service is no longer fully stateless"
```

---

## Task 7: Frontend service layer — `ai-copilot.service.ts`

**Files:**
- Modify: `frontend/src/app/services/ai-copilot.service.ts`

**Interfaces:**
- Produces: `ConversationSummary`, `ConversationMessage`, `ConversationDetail` interfaces; `listConversations()`, `getConversation(id)`, `deleteConversation(id)` methods; `sendMessage(message, conversationId)` (signature changed — second param is now `string | null`, not `ChatHistoryMessage[]`); `SpendingForecastResponse.conversation_id: string` (new field).

- [ ] **Step 1: Edit the file**

Remove the `ChatHistoryMessage` interface entirely (lines 91-97 in the current file) — replace it and the section around `sendMessage` with:

```typescript
export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  response: SpendingForecastResponse | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}
```

Add `conversation_id: string;` as a field on `SpendingForecastResponse` (anywhere in the interface, e.g. right after `requested_amount_minor`).

Replace the `sendMessage` method and add the three new ones:

```typescript
  sendMessage(message: string, conversationId: string | null): Observable<SpendingForecastResponse> {
    return this.http.post<SpendingForecastResponse>(`${API_BASE_URL}/ai/spending-forecast/chat`, {
      message,
      conversation_id: conversationId,
    });
  }

  listConversations(): Observable<ConversationSummary[]> {
    return this.http.get<ConversationSummary[]>(`${API_BASE_URL}/ai/spending-forecast/conversations`);
  }

  getConversation(id: string): Observable<ConversationDetail> {
    return this.http.get<ConversationDetail>(`${API_BASE_URL}/ai/spending-forecast/conversations/${id}`);
  }

  deleteConversation(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/ai/spending-forecast/conversations/${id}`);
  }
```

(`confirmAction` stays exactly as-is.)

- [ ] **Step 2: Verify it compiles**

This file has no consumers left in a valid state yet (Task 8 fixes `copilot.ts`) — a full app compile will show errors in `copilot.ts` until then. Just confirm THIS file alone has no syntax errors by checking the dev server log for `ai-copilot.service.ts`-specific errors only:

```bash
docker logs maestrobank-frontend --tail 30
```

Expected: errors mentioning `copilot.ts` (expected, fixed in Task 8) but none mentioning `ai-copilot.service.ts` itself.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/services/ai-copilot.service.ts
git commit -m "feat(frontend): add conversation list/get/delete to AiCopilotService"
```

---

## Task 8: Frontend service layer — `ai-support.service.ts`

**Files:**
- Modify: `frontend/src/app/services/ai-support.service.ts`

**Interfaces:**
- Produces: same shape as Task 7, for the Support Agent — `ConversationSummary`, `ConversationMessage` (with `response: AiChatResponse | null`), `ConversationDetail`; `listConversations()`, `getConversation(id)`, `deleteConversation(id)`; `AiChatRequest.conversation_id?: string | null` (replaces `history?`); `AiChatResponse.conversation_id: string`.

- [ ] **Step 1: Edit the file**

Replace `AiChatRequest`:

```typescript
export interface AiChatRequest {
  message: string;
  conversation_id?: string | null;
  pending_action?: AiPendingAction | null;
}
```

Add `conversation_id: string;` to `AiChatResponse`.

Add after `AiChatResponse`:

```typescript
export interface ConversationSummary {
  id: string;
  title: string;
  updated_at: string;
}

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  response: AiChatResponse | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ConversationMessage[];
}
```

Add methods to the `AiSupportService` class (after `chat`):

```typescript
  listConversations(): Observable<ConversationSummary[]> {
    return this.http.get<ConversationSummary[]>(`${API_BASE_URL}/ai/support/conversations`);
  }

  getConversation(id: string): Observable<ConversationDetail> {
    return this.http.get<ConversationDetail>(`${API_BASE_URL}/ai/support/conversations/${id}`);
  }

  deleteConversation(id: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/ai/support/conversations/${id}`);
  }
```

- [ ] **Step 2: Verify (same caveat as Task 7 — `support.ts` isn't fixed yet)**

```bash
docker logs maestrobank-frontend --tail 30
```

Expected: errors mentioning `support.ts` (fixed in Task 9), none mentioning `ai-support.service.ts` itself.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/services/ai-support.service.ts
git commit -m "feat(frontend): add conversation list/get/delete to AiSupportService"
```

---

## Task 9: MaestroAgent page — conversations UI

**Files:**
- Modify: `frontend/src/app/features/copilot/copilot.ts`
- Modify: `frontend/src/app/features/copilot/copilot.html`
- Modify: `frontend/src/app/features/copilot/copilot.css`

**Interfaces:**
- Consumes: `AiCopilotService.listConversations/getConversation/deleteConversation/sendMessage` (Task 7).

- [ ] **Step 1: Edit `copilot.ts`**

Change the import line:

```typescript
import { AiCopilotService, ConversationDetail, ConversationSummary, SpendingForecastResponse } from '../../services/ai-copilot.service';
```

Add `OnInit` to the imports from `@angular/core` and to `implements`:

```typescript
import { Component, ElementRef, OnDestroy, OnInit, computed, effect, inject, signal, viewChild } from '@angular/core';
```

```typescript
export class Copilot implements OnInit, OnDestroy {
```

Add `DatePipe` to the component's `imports` array and its import line:

```typescript
import { DatePipe } from '@angular/common';
```

```typescript
  imports: [FormsModule, DatePipe, PageHeader, Icon, MoneyPipe, MarkdownLitePipe],
```

Add two new signals right after `chatMessages`:

```typescript
  protected readonly chatMessages = signal<ChatMessage[]>([]);
  protected readonly conversations = signal<ConversationSummary[]>([]);
  protected readonly activeConversationId = signal<string | null>(null);
```

Inject `ToastService` and `error-utils` (add these two imports at the top):

```typescript
import { ToastService } from '../../shared/components/toast/toast.service';
```

```typescript
  private readonly toast = inject(ToastService);
```

Add `ngOnInit`:

```typescript
  ngOnInit(): void {
    this.loadConversations();
  }
```

Add these methods (anywhere after `ngOnDestroy`, before `sendMessage`):

```typescript
  private loadConversations(): void {
    this.copilotApi.listConversations().subscribe({
      next: (list) => this.conversations.set(list),
    });
  }

  protected startNewConversation(): void {
    this.activeConversationId.set(null);
    this.chatMessages.set([]);
  }

  protected openConversation(id: string): void {
    if (id === this.activeConversationId()) return;
    this.copilotApi.getConversation(id).subscribe({
      next: (detail: ConversationDetail) => {
        this.activeConversationId.set(detail.id);
        this.chatMessages.set(
          detail.messages.map((m, index) => ({
            id: index,
            role: m.role,
            text: m.content,
            time: formatChatTime(new Date(m.created_at)),
            response: m.response ?? undefined,
            actionState: m.response?.pending_action ? 'pending' : undefined,
          })),
        );
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut încărca conversația.')),
    });
  }

  protected deleteConversation(event: Event, id: string): void {
    event.stopPropagation();
    this.copilotApi.deleteConversation(id).subscribe({
      next: () => {
        this.conversations.update((list) => list.filter((c) => c.id !== id));
        if (this.activeConversationId() === id) this.startNewConversation();
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut șterge conversația.')),
    });
  }
```

Replace the `ask` method's body — remove the `buildHistory()` call and change the `sendMessage` call:

```typescript
  private ask(message: string): void {
    this.pushMessage({ id: Date.now(), role: 'user', text: message, time: formatChatTime(new Date()) });
    this.sending.set(true);
    this.sendingSlow.set(false);
    this.slowTimer = setTimeout(() => this.sendingSlow.set(true), 15_000);

    this.copilotApi.sendMessage(message, this.activeConversationId()).subscribe({
      next: (response) => {
        this.stopSending();
        if (!this.activeConversationId()) {
          this.activeConversationId.set(response.conversation_id);
          this.loadConversations();
        }
        this.pushMessage({
          id: Date.now(),
          role: 'assistant',
          text: response.answer,
          time: formatChatTime(new Date()),
          response,
          actionState: response.pending_action ? 'pending' : undefined,
        });
      },
      error: (err) => {
        this.stopSending();
        const errorText = extractErrorMessage(err, 'Nu am putut obține un răspuns acum. Te rugăm să încerci din nou.');
        this.pushMessage({ id: Date.now(), role: 'assistant', text: '', time: formatChatTime(new Date()), errorText });
      },
    });
  }
```

Delete the entire `buildHistory` method (it's now unused) — search for `private buildHistory` and remove that whole method block.

- [ ] **Step 2: Edit `copilot.html`**

Insert this new card as the FIRST child of `<aside class="copilot-side">`, before the existing "Context financiar" `<div class="copilot-side-card">`:

```html
    <div class="copilot-side-card">
      <div class="copilot-side-card__header">
        <strong>Conversații</strong>
        <button type="button" class="copilot-conversations__new" (click)="startNewConversation()">
          <app-icon name="plus" [size]="14" /> Nouă
        </button>
      </div>
      @if (conversations().length === 0) {
        <p class="copilot-conversations__empty">Nicio conversație salvată încă.</p>
      } @else {
        <div class="copilot-conversations__list">
          @for (conversation of conversations(); track conversation.id) {
            <button
              type="button"
              class="copilot-conversations__item"
              [class.copilot-conversations__item--active]="conversation.id === activeConversationId()"
              (click)="openConversation(conversation.id)"
            >
              <span class="copilot-conversations__item-title">{{ conversation.title }}</span>
              <span class="copilot-conversations__item-date">{{ conversation.updated_at | date: 'dd MMM, HH:mm' }}</span>
              <span class="copilot-conversations__item-delete" (click)="deleteConversation($event, conversation.id)">
                <app-icon name="trash" [size]="13" />
              </span>
            </button>
          }
        </div>
      }
    </div>

```

- [ ] **Step 3: Edit `copilot.css`**

Find the winning `.copilot-side-card__header` rule (the one with the negative-margin bleed, near line 967) and add flex layout to it:

```css
.copilot-side-card__header {
  margin: calc(var(--mb-space-5) * -1) calc(var(--mb-space-5) * -1) var(--mb-space-4);
  padding: var(--mb-space-4) var(--mb-space-5);
  border-bottom: 1px solid var(--mb-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--mb-space-2);
}
```

Add these new rules anywhere after that block:

```css
.copilot-conversations__new {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--mb-border-strong);
  border-radius: var(--mb-radius-pill);
  background: var(--mb-surface-muted);
  color: var(--mb-text-secondary);
  font: inherit;
  font-size: var(--mb-font-size-xs);
  font-weight: var(--mb-font-weight-medium);
  cursor: pointer;
  transition: background var(--mb-transition-fast), color var(--mb-transition-fast);
}

.copilot-conversations__new:hover {
  background: var(--mb-blue-50);
  color: var(--mb-blue-600);
}

.copilot-conversations__empty {
  margin: 0;
  color: var(--mb-text-tertiary);
  font-size: var(--mb-font-size-xs);
}

.copilot-conversations__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 220px;
  overflow-y: auto;
}

.copilot-conversations__item {
  display: flex;
  align-items: center;
  gap: var(--mb-space-2);
  width: 100%;
  padding: 0.5rem 0.6rem;
  border: none;
  border-radius: var(--mb-radius-sm);
  background: transparent;
  color: var(--mb-text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.copilot-conversations__item:hover {
  background: var(--mb-surface-muted);
}

.copilot-conversations__item--active {
  background: var(--mb-blue-50);
  color: var(--mb-blue-600);
}

.copilot-conversations__item-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--mb-font-size-sm);
}

.copilot-conversations__item-date {
  flex-shrink: 0;
  font-size: var(--mb-font-size-xs);
  color: var(--mb-text-tertiary);
}

.copilot-conversations__item--active .copilot-conversations__item-date {
  color: var(--mb-blue-600);
}

.copilot-conversations__item-delete {
  flex-shrink: 0;
  display: inline-flex;
  padding: 3px;
  border-radius: var(--mb-radius-sm);
  color: var(--mb-text-tertiary);
}

.copilot-conversations__item-delete:hover {
  background: var(--mb-negative-bg);
  color: var(--mb-negative);
}
```

- [ ] **Step 4: Verify it compiles and works**

```bash
docker logs maestrobank-frontend --tail 40
```

Expected: clean compile, no errors mentioning `copilot.ts`/`copilot.html`/`copilot.css`.

Then manually in the browser (`http://localhost:4200/app/copilot`): send a message, confirm a "Conversații" entry appears with the message truncated as its title; refresh the page, confirm the conversation list persists and clicking the entry reloads the same messages including any cards; click "Nouă", confirm the chat clears and a second message creates a second list entry; delete one, confirm it disappears from the list and (if it was active) the chat clears.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/features/copilot/copilot.ts frontend/src/app/features/copilot/copilot.html frontend/src/app/features/copilot/copilot.css
git commit -m "feat(frontend): conversation list/switch/delete UI on MaestroAgent page"
```

---

## Task 10: Support page — conversations UI + remove `sessionStorage`

**Files:**
- Modify: `frontend/src/app/features/support/support.ts`
- Modify: `frontend/src/app/features/support/support.html`
- Modify: `frontend/src/app/features/support/support.css`

**Interfaces:**
- Consumes: `AiSupportService.listConversations/getConversation/deleteConversation/chat` (Task 8).

- [ ] **Step 1: Edit `support.ts` — remove the `sessionStorage` mechanism**

Delete the `SUPPORT_CHAT_STORAGE_KEY` import line:

```typescript
import { SUPPORT_CHAT_STORAGE_KEY } from '../../core/storage-keys';
```

Delete the entire comment block + `_MAX_PERSISTED_MESSAGES` constant + `loadPersistedMessages` + `persistMessages` functions (everything between the `formatChatTime` function and the component's `@Component` decorator — roughly lines 87-118 of the current file).

Change the `chatMessages` signal initializer:

```typescript
  protected readonly chatMessages = signal<ChatMessage[]>(loadPersistedMessages());
```
becomes:
```typescript
  protected readonly chatMessages = signal<ChatMessage[]>([]);
```

Remove the second `effect()` in the constructor (the one that calls `persistMessages`):

```typescript
    // Persistă conversația la fiecare schimbare — separat de efectul de
    // mai sus (ăla mai reacționează și la `supportTyping`, ceea ce ar
    // însemna scrieri inutile în sessionStorage la fiecare tick de "scrie...").
    effect(() => {
      persistMessages(this.chatMessages());
    });
```

Delete that whole block (keep the first `effect()` in the constructor, which does the auto-scroll — untouched).

- [ ] **Step 2: Edit `support.ts` — add conversations UI plumbing**

Change the import line for `AiSupportService`:

```typescript
import {
  AiChatMessage as AiHistoryMessage,
  AiPendingAction,
  AiRecommendedAction,
  AiSupportService,
  ConversationDetail,
  ConversationSummary,
} from '../../services/ai-support.service';
```

Add `DatePipe` import and to the component `imports` array:

```typescript
import { DatePipe } from '@angular/common';
```

```typescript
  imports: [FormsModule, DatePipe, MoneyPipe, MarkdownLitePipe, PageHeader, ActionButton, StatusBadge, Modal, Icon, TransactionRow],
```

Add two new signals after `chatMessages`:

```typescript
  protected readonly chatMessages = signal<ChatMessage[]>([]);
  protected readonly conversations = signal<ConversationSummary[]>([]);
  protected readonly activeConversationId = signal<string | null>(null);
```

Update `ngOnInit` (it already exists — add the call, keep the ticket-modal logic):

```typescript
  ngOnInit(): void {
    this.loadConversations();
    const shouldOpen = this.route.snapshot.queryParamMap.get('newTicket') === '1';
    const presetCategory = this.route.snapshot.queryParamMap.get('category') as TicketCategory | null;
    if (presetCategory) this.category.set(presetCategory);
    if (shouldOpen) this.openModal();
  }
```

Add these methods (anywhere after `ngOnDestroy`):

```typescript
  private loadConversations(): void {
    this.aiSupport.listConversations().subscribe({
      next: (list) => this.conversations.set(list),
    });
  }

  protected startNewConversation(): void {
    this.activeConversationId.set(null);
    this.pendingAction.set(null);
    this.chatMessages.set([]);
  }

  protected openConversation(id: string): void {
    if (id === this.activeConversationId()) return;
    this.aiSupport.getConversation(id).subscribe({
      next: (detail: ConversationDetail) => {
        this.activeConversationId.set(detail.id);
        this.pendingAction.set(null);
        this.chatMessages.set(
          detail.messages.map((m, index) => {
            const response = m.response;
            const context = response?.context as ChatContext | undefined;
            return {
              id: index,
              role: m.role === 'assistant' ? 'support' : 'user',
              text: m.content,
              time: formatChatTime(new Date(m.created_at)),
              context: context && Object.keys(context).length > 0 ? context : undefined,
              recommendedActions:
                response?.recommended_actions && response.recommended_actions.length > 0
                  ? response.recommended_actions
                  : undefined,
            };
          }),
        );
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut încărca conversația.')),
    });
  }

  protected deleteConversation(event: Event, id: string): void {
    event.stopPropagation();
    this.aiSupport.deleteConversation(id).subscribe({
      next: () => {
        this.conversations.update((list) => list.filter((c) => c.id !== id));
        if (this.activeConversationId() === id) this.startNewConversation();
      },
      error: (err) => this.toast.error(extractErrorMessage(err, 'Nu am putut șterge conversația.')),
    });
  }
```

- [ ] **Step 3: Edit `support.ts` — update `askAgent`**

Replace the whole method:

```typescript
  private askAgent(text: string): void {
    if (!text || this.supportTyping()) return;

    const pending = this.pendingAction();
    this.pendingAction.set(null);

    this.chatMessages.update((messages) => [
      ...messages,
      { id: Date.now(), role: 'user', text, time: formatChatTime(new Date()) },
    ]);
    this.supportTyping.set(true);
    this.supportTypingSlow.set(false);
    this.slowTimer = setTimeout(() => this.supportTypingSlow.set(true), 15_000);

    this.aiSupport.chat({ message: text, conversation_id: this.activeConversationId(), pending_action: pending }).subscribe({
      next: (response) => {
        this.stopTyping();
        if (!this.activeConversationId()) {
          this.activeConversationId.set(response.conversation_id);
          this.loadConversations();
        }
        const context = response.context as ChatContext | undefined;
        this.chatMessages.update((messages) => [
          ...messages,
          {
            id: Date.now() + 1,
            role: 'support',
            text: response.answer,
            time: formatChatTime(new Date()),
            context: context && Object.keys(context).length > 0 ? context : undefined,
            recommendedActions: response.recommended_actions.length > 0 ? response.recommended_actions : undefined,
          },
        ]);
        const nextPending = response.metadata?.['pending_action'] as AiPendingAction | undefined;
        if (response.requires_confirmation && nextPending) {
          this.pendingAction.set(nextPending);
        }
      },
      error: (err) => {
        this.stopTyping();
        this.toast.error(extractErrorMessage(err, 'Chat-ul de suport nu a putut răspunde. Încearcă din nou.'));
      },
    });
  }
```

(The only real changes from the original: no more `history` built from `chatMessages()`, and the new `conversation_id`-tracking block right after `this.stopTyping()`.) `AiHistoryMessage` import becomes unused after this — remove it from the import line at the top (leave `AiPendingAction`, `AiRecommendedAction`, `AiSupportService`, `ConversationDetail`, `ConversationSummary`).

- [ ] **Step 4: Edit `support.html`**

Insert this new section as the FIRST child of `<aside class="support-sidebar">`, before the existing `<section class="support-panel support-panel--agent">`:

```html
    <section class="support-panel support-panel--conversations">
      <div class="support-panel__header">
        <strong>Conversații</strong>
        <button type="button" class="support-conversations__new" (click)="startNewConversation()">
          <app-icon name="plus" [size]="14" /> Nouă
        </button>
      </div>
      @if (conversations().length === 0) {
        <p class="support-conversations__empty">Nicio conversație salvată încă.</p>
      } @else {
        <div class="support-conversations__list">
          @for (conversation of conversations(); track conversation.id) {
            <button
              type="button"
              class="support-conversations__item"
              [class.support-conversations__item--active]="conversation.id === activeConversationId()"
              (click)="openConversation(conversation.id)"
            >
              <span class="support-conversations__item-title">{{ conversation.title }}</span>
              <span class="support-conversations__item-date">{{ conversation.updated_at | date: 'dd MMM, HH:mm' }}</span>
              <span class="support-conversations__item-delete" (click)="deleteConversation($event, conversation.id)">
                <app-icon name="trash" [size]="13" />
              </span>
            </button>
          }
        </div>
      }
    </section>

```

- [ ] **Step 5: Edit `support.css`**

Add these rules anywhere in the file (they mirror `copilot.css`'s conversation list styles exactly, plus a header rule copilot already had and support didn't):

```css
.support-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--mb-space-2);
  margin-bottom: var(--mb-space-4);
  font-size: var(--mb-font-size-sm);
  color: var(--mb-text-primary);
}

.support-conversations__new {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--mb-border-strong);
  border-radius: var(--mb-radius-pill);
  background: var(--mb-surface-muted);
  color: var(--mb-text-secondary);
  font: inherit;
  font-size: var(--mb-font-size-xs);
  font-weight: var(--mb-font-weight-medium);
  cursor: pointer;
  transition: background var(--mb-transition-fast), color var(--mb-transition-fast);
}

.support-conversations__new:hover {
  background: var(--mb-blue-50);
  color: var(--mb-blue-600);
}

.support-conversations__empty {
  margin: 0;
  color: var(--mb-text-tertiary);
  font-size: var(--mb-font-size-xs);
}

.support-conversations__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 220px;
  overflow-y: auto;
}

.support-conversations__item {
  display: flex;
  align-items: center;
  gap: var(--mb-space-2);
  width: 100%;
  padding: 0.5rem 0.6rem;
  border: none;
  border-radius: var(--mb-radius-sm);
  background: transparent;
  color: var(--mb-text-primary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.support-conversations__item:hover {
  background: var(--mb-surface-muted);
}

.support-conversations__item--active {
  background: var(--mb-blue-50);
  color: var(--mb-blue-600);
}

.support-conversations__item-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--mb-font-size-sm);
}

.support-conversations__item-date {
  flex-shrink: 0;
  font-size: var(--mb-font-size-xs);
  color: var(--mb-text-tertiary);
}

.support-conversations__item--active .support-conversations__item-date {
  color: var(--mb-blue-600);
}

.support-conversations__item-delete {
  flex-shrink: 0;
  display: inline-flex;
  padding: 3px;
  border-radius: var(--mb-radius-sm);
  color: var(--mb-text-tertiary);
}

.support-conversations__item-delete:hover {
  background: var(--mb-negative-bg);
  color: var(--mb-negative);
}
```

- [ ] **Step 6: Verify it compiles and works**

```bash
docker logs maestrobank-frontend --tail 40
```

Expected: clean compile.

Manually in the browser (`http://localhost:4200/app/support`): same checklist as Task 9 Step 4 (send message → list entry appears → refresh persists → "Nouă" clears → delete works) — plus confirm a fresh incognito/private window (or `sessionStorage.clear()` in devtools) no longer resurrects an old conversation transcript, since that mechanism is gone.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/features/support/support.ts frontend/src/app/features/support/support.html frontend/src/app/features/support/support.css
git commit -m "feat(frontend): conversation list/switch/delete UI on Support page, remove sessionStorage persistence"
```

---

## Task 11: Delete the now-unused `sessionStorage` key file

**Files:**
- Delete: `frontend/src/app/core/storage-keys.ts`
- Modify: `frontend/src/app/services/auth.service.ts`

**Interfaces:** none — this is pure cleanup after Task 10 removed the last usage of `SUPPORT_CHAT_STORAGE_KEY` on the write side; this task removes the read side (logout cleanup) and the constant itself.

- [ ] **Step 1: Confirm nothing else references it**

```bash
grep -rn "SUPPORT_CHAT_STORAGE_KEY\|storage-keys" frontend/src/app
```

Expected output: only `frontend/src/app/services/auth.service.ts` (the import and the `removeItem` call) — if `support.ts` still shows up here, Task 10 wasn't fully applied; go back and finish it before continuing.

- [ ] **Step 2: Edit `auth.service.ts`**

Remove the import line:

```typescript
import { SUPPORT_CHAT_STORAGE_KEY } from '../core/storage-keys';
```

In `logout()`, remove these lines:

```typescript
    // Conversația cu Support Agent e persistată per-tab (vezi
    // features/support/support.ts) — ștearsă aici ca userul următor de pe
    // același tab/browser să nu vadă conversația celui dinainte.
    sessionStorage.removeItem(SUPPORT_CHAT_STORAGE_KEY);
```

`logout()` should now read:

```typescript
  logout(): void {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    this.currentUser.set(null);
  }
```

- [ ] **Step 3: Delete the file**

```bash
rm frontend/src/app/core/storage-keys.ts
```

- [ ] **Step 4: Verify it compiles**

```bash
docker logs maestrobank-frontend --tail 30
```

Expected: clean compile, no errors.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/app/core/storage-keys.ts frontend/src/app/services/auth.service.ts
git commit -m "chore(frontend): remove unused sessionStorage chat persistence, superseded by backend history"
```

---

## Final verification

- [ ] Run the full backend suite once more: `docker compose exec -e MONGO_URL=mongodb://mongodb:27017/ai_orchestrator_db_test ai-orchestrator-service python -m pytest -q` — expect all PASS.
- [ ] In the browser, exercise both pages end-to-end: MaestroAgent — ask a financial question, confirm cards render; switch to a second conversation; delete one; refresh and confirm persistence. Support Agent — same checklist, plus confirm a pending-action confirmation flow (e.g. "creează un tichet...") still works across the `conversation_id` change.
- [ ] `git log --oneline` should show one commit per task above — do NOT push (per this session's standing instruction: pushes are only ever done by the user themselves).
