"""Logica de verificare a identității — compară fața din poza buletinului
cu un selfie live, folosind DeepFace.

Imaginile NU sunt persistate: sunt scrise temporar pe disc (DeepFace cere
căi de fișier), comparate, apoi șterse imediat, indiferent de rezultat —
nu există un motiv real, într-un demo, să păstrăm poze de buletin. Doar
REZULTATUL (verified: bool) ajunge să fie salvat, ca flag pe user-ul din
auth_db (identity_verified) — vezi _mark_identity_verified mai jos.
"""

import asyncio
import logging
import os
import tempfile

import httpx
from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.i18n import translate

logger = logging.getLogger("verification-service")


async def _read_and_validate_image(file: UploadFile, label_key: str) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=translate("imageMissing", label=translate(label_key)))
    if len(content) > settings.max_image_size_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=translate("imageTooLarge", label=translate(label_key)))
    return content


def _run_deepface_verify(id_document_path: str, selfie_path: str) -> dict:
    from deepface import DeepFace

    return DeepFace.verify(
        img1_path=id_document_path,
        img2_path=selfie_path,
        model_name=settings.deepface_model_name,
        detector_backend=settings.deepface_detector_backend,
    )


def _build_models() -> None:
    from deepface import DeepFace

    DeepFace.build_model(task="facial_recognition", model_name=settings.deepface_model_name)
    DeepFace.build_model(task="face_detector", model_name=settings.deepface_detector_backend)


async def warm_up_model() -> None:
    """Încarcă modelul de recunoaștere ȘI detectorul de fețe în memorie
    ÎNAINTE ca serviciul să înceapă să accepte cereri (lifespan din
    main.py) — altfel prima cerere REALĂ a unui user plătește costul de
    încărcare (poate depăși cu ușurință timeout-ul de 10s al Gateway-ului,
    care ar întoarce 504 la primul verify-identity din viața containerului)."""
    logger.info(
        "verification-service: încarc modelul %s + detectorul %s...",
        settings.deepface_model_name,
        settings.deepface_detector_backend,
    )
    await asyncio.to_thread(_build_models)
    logger.info("verification-service: modele încărcate, gata de cereri.")


async def _mark_identity_verified(user_id: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{settings.auth_service_url}/internal/auth/mark-identity-verified",
            json={"user_id": user_id},
        )
        response.raise_for_status()


def _similarity_percent(distance: float) -> float:
    """Similaritate cosine, ca procent — DeepFace (cu metrica implicită,
    cosine) întoarce doar distanța; similaritatea = 1 - distanța. NU e o
    probabilitate calibrată statistic, doar o citire mai intuitivă decât
    distanța brută (0% = complet diferite, 100% = identice)."""
    return round(max(0.0, min(1.0, 1 - distance)) * 100, 1)


async def verify_identity(user_id: str, id_document: UploadFile, selfie: UploadFile) -> dict:
    id_bytes = await _read_and_validate_image(id_document, "labelIdDocument")
    selfie_bytes = await _read_and_validate_image(selfie, "labelSelfie")

    with tempfile.TemporaryDirectory() as tmp_dir:
        id_path = os.path.join(tmp_dir, "id_document.jpg")
        selfie_path = os.path.join(tmp_dir, "selfie.jpg")
        with open(id_path, "wb") as f:
            f.write(id_bytes)
        with open(selfie_path, "wb") as f:
            f.write(selfie_bytes)

        try:
            # DeepFace.verify e sincron și greu de calcul (CPU) — rulat
            # într-un thread separat, ca să nu blocheze event loop-ul.
            result = await asyncio.to_thread(_run_deepface_verify, id_path, selfie_path)
        except ValueError as exc:
            # DeepFace ridică ValueError când nu detectează nicio față
            # într-una din imagini — mesaj prietenos, nu 500.
            logger.info("verification-service: nicio față detectată pentru user_id=%s (%s)", user_id, exc)
            return {
                "verified": False,
                "message": "Nu am putut detecta o față clară în una dintre imagini. Încearcă din nou, cu lumină mai bună.",
                "similarity_percent": None,
            }

    verified = bool(result.get("verified"))
    distance = result.get("distance", 1.0)
    similarity_percent = _similarity_percent(distance)
    logger.info(
        "verification-service: rezultat comparare pentru user_id=%s: verified=%s distance=%.4f similarity=%.1f%%",
        user_id,
        verified,
        distance,
        similarity_percent,
    )

    if not verified:
        return {
            "verified": False,
            "message": f"Fața din selfie nu se potrivește cu cea din buletin (similaritate {similarity_percent}%). Încearcă din nou.",
            "similarity_percent": similarity_percent,
        }

    try:
        await _mark_identity_verified(user_id)
    except httpx.HTTPError:
        logger.exception("verification-service: match reușit dar marcarea în auth-service a eșuat (user_id=%s)", user_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=translate("identityUpdateFailedAfterVerification"),
        )

    return {
        "verified": True,
        "message": f"Identitate confirmată (similaritate {similarity_percent}%).",
        "similarity_percent": similarity_percent,
    }
