"""
Teste pentru verification-service.

Nu rulăm DeepFace efectiv aici (model greu, cere imagini reale cu fețe) —
testăm doar wiring-ul HTTP/JWT al rutei, cu app.service.verify_identity
mock-uit. Verificarea reală a algoritmului de matching se face manual,
prin /docs, cu poze adevărate.

Rulare (cu stack-ul pornit prin `docker compose up`):

    docker compose exec verification-service pip install pytest==8.3.3 pytest-asyncio==0.24.0 -q
    docker compose exec verification-service python -m pytest -q
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import jwt
import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio

USER_ID = str(ObjectId())


def _make_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "email": "test@example.com", "iat": now, "exp": now + timedelta(minutes=5)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


AUTH_HEADER = {"Authorization": f"Bearer {_make_token(USER_ID)}"}


async def test_verify_identity_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"id_document": ("id.jpg", b"fake", "image/jpeg"), "selfie": ("selfie.jpg", b"fake", "image/jpeg")}
        response = await client.post("/verify-identity", files=files)
    assert response.status_code == 401


async def test_verify_identity_success(monkeypatch):
    mock_verify = AsyncMock(return_value={"verified": True, "message": "Identitate confirmată."})
    monkeypatch.setattr("app.routers.verification.service.verify_identity", mock_verify)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        files = {"id_document": ("id.jpg", b"fake", "image/jpeg"), "selfie": ("selfie.jpg", b"fake", "image/jpeg")}
        response = await client.post("/verify-identity", files=files, headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json() == {"verified": True, "message": "Identitate confirmată."}
    mock_verify.assert_awaited_once()
    assert mock_verify.await_args.args[0] == USER_ID
