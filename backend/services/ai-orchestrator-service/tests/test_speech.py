"""Teste pentru POST /speech (text-to-speech) — vezi app/tts.py,
app/routers/speech.py.

`app.tts.synthesize_speech` e mock-uit — nu facem apeluri REALE către
serviciul edge-tts în teste (extern, lent, ar polua CI-ul cu dependențe de
rețea) — vezi și restul serviciului (Azure OpenAI e la fel mock-uit în
test_agent.py/test_support_agent.py).
"""

import pytest

from app import tts

pytestmark = pytest.mark.asyncio


async def test_synthesize_returns_audio_mpeg(monkeypatch, client, auth_header: str):
    fake_audio = b"\xff\xfb\x90\x00fake-mp3-bytes"

    async def fake_synthesize(text: str) -> bytes:
        assert text == "Salut, ce mai faci?"
        return fake_audio

    monkeypatch.setattr(tts, "synthesize_speech", fake_synthesize)

    response = await client.post("/speech", json={"text": "Salut, ce mai faci?"}, headers={"Authorization": auth_header})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == fake_audio


async def test_synthesize_requires_auth(client):
    response = await client.post("/speech", json={"text": "Salut"})
    assert response.status_code == 401


async def test_synthesize_rejects_empty_text(client, auth_header: str):
    response = await client.post("/speech", json={"text": ""}, headers={"Authorization": auth_header})
    assert response.status_code == 422


async def test_synthesize_rejects_overly_long_text(client, auth_header: str):
    response = await client.post(
        "/speech", json={"text": "a" * (tts.MAX_TEXT_LENGTH + 1)}, headers={"Authorization": auth_header}
    )
    assert response.status_code == 422


async def test_synthesize_returns_502_on_tts_failure(monkeypatch, client, auth_header: str):
    async def failing_synthesize(text: str) -> bytes:
        raise RuntimeError("edge-tts indisponibil")

    monkeypatch.setattr(tts, "synthesize_speech", failing_synthesize)

    response = await client.post("/speech", json={"text": "Salut"}, headers={"Authorization": auth_header})
    assert response.status_code == 502
