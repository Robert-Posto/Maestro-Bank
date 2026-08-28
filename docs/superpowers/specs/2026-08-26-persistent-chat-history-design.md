# Persistent chat history — MaestroAgent & Support Agent

## Context

Today neither AI chat is truly persistent:

- **MaestroAgent** (`ai-copilot.service.ts` → `ai-orchestrator-service` `/spending-forecast/chat`): conversation lives only in an Angular signal. Refresh = gone. No history list, no way to resume or browse past chats.
- **Support Agent** (`ai-support.service.ts` → `ai-orchestrator-service` `/support`): the CURRENT conversation is stashed in `sessionStorage` (`support.ts`) so a refresh within the same tab resumes it — but it's a single slot, gone on tab close, and there's no concept of multiple distinct past conversations to list or reopen.

`ai-orchestrator-service` is deliberately stateless today (no `database.py`, no `MONGO_URL`) — documented in both agents' model files as an explicit choice from the original task spec ("poți păstra doar un context foarte scurt al conversației... NU memorie pe termen lung"). This spec is a deliberate, user-approved departure from that: MaestroAgent and Support Agent both get real, backend-persisted, multi-conversation history, listed and reopenable from the UI, scoped per user.

## Goals

- A user can see a list of their past conversations (per agent), reopen one, and keep chatting in it.
- Starting a new conversation is explicit ("Conversație nouă").
- Conversations can be deleted individually.
- Works across devices/browsers (backend-persisted, not `sessionStorage`/`localStorage`).
- Reopening an old MaestroAgent conversation shows the same rich cards (financial context, budgets) it showed live — not degraded to plain text.

## Non-goals

- No conversation renaming (title is auto-derived from the first message, truncated — no LLM call spent on a cosmetic title).
- No cross-agent search, export, or archival/retention policy — out of scope for this pass.
- No change to the agents' own reasoning/tool-calling logic, prompts, or the recent-turns truncation they already do internally (`_MAX_HISTORY_MESSAGES` in each agent module) — this is purely an added persistence + retrieval layer around unchanged agent code.

## Data model

New database for `ai-orchestrator-service` (its first — mirrors every other service owning its own Mongo database), one collection, shared by both agents (distinguished by an `agent` field, not two separate collections — same shape, no reason to split):

```
conversations_db.conversations
{
  _id: ObjectId,
  user_id: str,                                   # from JWT `sub`, never client-supplied
  agent: "spending_forecast" | "support",
  title: str,                                      # first user message, truncated (~50 chars) + "…"
  created_at: datetime,
  updated_at: datetime,                            # bumped on every appended turn; list is sorted by this, desc
  messages: [
    {
      role: "user" | "assistant",
      content: str,                                 # plain text — also what's replayed as `history` to the agent
      response: <dict> | null,                       # full structured response (SpendingForecastResponse / ChatResponse) for assistant turns, so a reopened conversation renders identically to how it looked live. null for user turns.
      created_at: datetime,
    },
    ...
  ],
}
```

Embedded messages array, not a separate collection — conversations are short (already capped at 40 turns by each agent's existing history limit), so there's no pagination/join need a subdocument can't handle.

Indexes (idempotent, created in `lifespan`, same pattern as every other service — e.g. `accounts-service`'s `backfill_missing_account_types`): compound `(user_id, agent, updated_at desc)` for the list query.

## Backend changes (`ai-orchestrator-service`)

`docker-compose.yml`: add `MONGO_URL=${MONGODB_URI_BASE}/ai_orchestrator_db` to `ai-orchestrator-service`'s environment, same pattern as every other stateful service.

New files, following the established per-service structure:
- `app/database.py` — Motor client (copy of any existing service's, e.g. `budgets-service/app/database.py`).
- `app/models/conversation.py` — `ConversationSummary` (id, title, updated_at), `ConversationDetail` (+ messages), request/response DTOs for the new endpoints.
- `app/services/conversation_service.py` — `list_conversations(user_id, agent)`, `get_conversation(user_id, agent, id)` (404 if missing or not owned), `create_conversation(user_id, agent, first_message)`, `append_turn(conversation_id, user_content, assistant_content, assistant_response)`, `delete_conversation(user_id, agent, id)`.

New routes, mirrored under both existing routers:
```
GET    /api/ai/spending-forecast/conversations
GET    /api/ai/spending-forecast/conversations/{id}
DELETE /api/ai/spending-forecast/conversations/{id}

GET    /api/ai/support/conversations
GET    /api/ai/support/conversations/{id}
DELETE /api/ai/support/conversations/{id}
```
No Gateway change needed — `proxy.py::_is_protected` already blanket-protects every path under `service="ai"` (`backend/gateway/app/routers/proxy.py:97`), so the new `/conversations` paths are covered automatically.

**Chat contract change** — `POST /spending-forecast/chat` and `POST /support` both change their request shape from `{message, history}` to `{message, conversation_id: str | None}`. Router flow (identical shape both agents):
```python
if payload.conversation_id:
    conversation = await conversation_service.get_conversation(user_id, AGENT, payload.conversation_id)
    history = to_history(conversation)          # same ChatHistoryMessage/ChatMessage shape as today
else:
    conversation = await conversation_service.create_conversation(user_id, AGENT, payload.message)
    history = []

response = await agent.handle_message(auth, payload.message, history=history)   # UNCHANGED call

await conversation_service.append_turn(conversation.id, payload.message, response.answer, response.model_dump())
response.conversation_id = conversation.id       # new field on both response models
return response
```
The agents' own `handle_message`/`handle_chat` internals — prompt building, tool calling, the existing history-truncation constants — are untouched. All existing agent-level tests stay valid; only the routers gain a persistence step before/after the same call.

**Support-specific note**: `support.py`'s auth dependency (`get_authorization`) deliberately returns only the raw header, not a decoded `user_id` — by design, so the agent's own tool-calling logic never makes authorization decisions off a client-derived value (Gateway + each downstream service already isolate per-user). Persisting conversations needs a `user_id` purely as a storage/ownership key, which is a different concern — so we add a small `CurrentUserId` dependency (decodes the same already-verified JWT, returns just `sub`) used ONLY by the new conversation endpoints and the chat router's persistence step, never passed into the agent/tools. This keeps the original security principle intact while giving persistence what it needs.

**Cleanup**: remove `support.ts`'s `sessionStorage` mechanism entirely (`SUPPORT_CHAT_STORAGE_KEY`, the save/restore logic) — fully superseded by backend persistence, and per this project's convention, dead code gets deleted, not left as a fallback.

## Frontend changes

Both `copilot.html`/`copilot.ts` and `support.html`/`support.ts` get the same treatment:

- A new **"Conversații" card**, added at the top of the existing right-side panel (`.copilot-side` / `.support-sidebar` — no new grid column). Shows: a "Conversație nouă" button, then the list (title + relative date), each row clickable to load, each with a small delete (×) action. The panel already has `max-height` + internal scroll (from a recent fix), so a growing list scrolls in place without affecting page layout.
- New methods on `ai-copilot.service.ts` / `ai-support.service.ts`: `listConversations()`, `getConversation(id)`, `deleteConversation(id)`.
- Component state: `conversations` signal (list), `activeConversationId` signal. `sendMessage()` passes `activeConversationId()` instead of a client-built `history` array; on the response, if `activeConversationId()` was null, set it from `response.conversation_id` and prepend the new conversation to the list (so it shows immediately without a re-fetch).
- Opening a conversation from the list: fetch its detail, replace `chatMessages` with its stored turns (mapping stored `response` back onto assistant messages so cards render exactly as before), set it active.
- "Conversație nouă": clear `chatMessages`, clear `activeConversationId` — next message creates a fresh conversation server-side (same lazy-creation as today's very first message, just explicit).

## Testing

- Backend: unit tests for `conversation_service` (create/list/append/delete/ownership-check-404), and router tests asserting the chat endpoint creates a conversation on first call, reuses it on `conversation_id`, and 404s on someone else's id.
- Frontend: not covered by the existing minimal `ng test` setup (per CLAUDE.md, coverage is minimal app-wide) — verified manually per this project's established practice this session (live curl/browser checks), not a new automated suite.
