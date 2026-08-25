"""Teste pentru app/guardian/llm_client.py — clientul Azure OpenAI IZOLAT
al lui Guardian. `complete_json` NU are voie SĂ ARUNCE NICIODATĂ — orice
eșec (neconfigurat, timeout, eroare, JSON invalid) trebuie să întoarcă
None, ca apelantul (guardian/service.py) să cadă curat pe șablon."""

from types import SimpleNamespace

import pytest
from openai import OpenAIError

from app.guardian import llm_client

pytestmark = pytest.mark.asyncio


class _FakeCompletions:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.call_count = 0

    async def create(self, **kwargs):
        self.call_count += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        message = SimpleNamespace(content=item)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeClient:
    def __init__(self, responses: list):
        self.chat = SimpleNamespace(completions=_FakeCompletions(responses))


@pytest.fixture(autouse=True)
def reset_client_singleton():
    """`_get_chat_client` cache-uiește clientul modul-level — resetăm între
    teste ca mock-urile să nu se scurgă dintr-un test în altul."""
    llm_client._chat_client = None
    yield
    llm_client._chat_client = None


def _configure_azure(monkeypatch, endpoint: str = "https://fake.openai.azure.com", api_key: str = "fake-key"):
    monkeypatch.setattr("app.config.settings.azure_openai_endpoint", endpoint)
    monkeypatch.setattr("app.config.settings.azure_openai_api_key", api_key)


async def test_success_returns_parsed_dict(monkeypatch):
    _configure_azure(monkeypatch)
    fake = _FakeClient(['{"customer_phrase": "ok", "staff_explanation": "detaliat"}'])
    monkeypatch.setattr(llm_client, "_get_chat_client", lambda: fake)

    result = await llm_client.complete_json([{"role": "user", "content": "x"}])
    assert result == {"customer_phrase": "ok", "staff_explanation": "detaliat"}


async def test_malformed_json_returns_none_without_retry(monkeypatch):
    _configure_azure(monkeypatch)
    fake = _FakeClient(["not valid json {{{"])
    monkeypatch.setattr(llm_client, "_get_chat_client", lambda: fake)

    result = await llm_client.complete_json([{"role": "user", "content": "x"}])
    assert result is None
    assert fake.chat.completions.call_count == 1  # JSON invalid nu se reîncearcă


async def test_non_object_json_returns_none(monkeypatch):
    _configure_azure(monkeypatch)
    fake = _FakeClient(["[1, 2, 3]"])  # JSON valid, dar nu un obiect
    monkeypatch.setattr(llm_client, "_get_chat_client", lambda: fake)

    result = await llm_client.complete_json([{"role": "user", "content": "x"}])
    assert result is None


async def test_first_attempt_fails_retry_succeeds(monkeypatch):
    _configure_azure(monkeypatch)
    fake = _FakeClient([OpenAIError("eroare simulată"), '{"customer_phrase": "ok", "staff_explanation": "ok"}'])
    monkeypatch.setattr(llm_client, "_get_chat_client", lambda: fake)

    result = await llm_client.complete_json([{"role": "user", "content": "x"}])
    assert result == {"customer_phrase": "ok", "staff_explanation": "ok"}
    assert fake.chat.completions.call_count == 2


async def test_both_attempts_fail_returns_none(monkeypatch):
    _configure_azure(monkeypatch)
    fake = _FakeClient([OpenAIError("eroare 1"), OpenAIError("eroare 2")])
    monkeypatch.setattr(llm_client, "_get_chat_client", lambda: fake)

    result = await llm_client.complete_json([{"role": "user", "content": "x"}])
    assert result is None
    assert fake.chat.completions.call_count == 2


async def test_not_configured_returns_none_with_zero_network_attempts(monkeypatch):
    monkeypatch.setattr("app.config.settings.azure_openai_endpoint", "")
    monkeypatch.setattr("app.config.settings.azure_openai_api_key", "")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("_build_client NU trebuia apelat fără credențiale configurate")

    monkeypatch.setattr(llm_client, "_build_client", _fail_if_called)

    result = await llm_client.complete_json([{"role": "user", "content": "x"}])
    assert result is None
