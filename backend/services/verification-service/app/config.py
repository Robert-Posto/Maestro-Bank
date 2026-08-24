"""Configurație citită din variabile de mediu. Nimic hardcodat aici."""

import os


class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker — folosită pentru a marca identitatea userului
    # ca verificată, după un match facial reușit (vezi service.py).
    auth_service_url: str = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")

    # Model DeepFace — inițial VGG-Face, dar testat manual cu poze reale a
    # confirmat fals-pozitive clare (buletinul unui utilizator + selfie-ul
    # ALTEI persoane, gen diferit, a trecut ca "verified"). VGG-Face are
    # embeddinguri mai vechi/mai puțin discriminative; ArcFace (loss cu
    # margine angulară, antrenat explicit să separe identități diferite)
    # are un rată de fals-acceptare mult mai mică la threshold-ul lui
    # implicit — schimbare de config, nu de cod, ca să rămână ușor de
    # ajustat dacă threshold-ul tot pare prea permisiv. Threshold-ul de
    # similaritate vine din DeepFace însuși (per model), nu îl recalculăm noi.
    #
    # Detector: "opencv" (Haar cascade) e cel mai rapid, dar eșuează des pe
    # poze reale de buletin (glare/hologramă/unghi) — am trecut pe
    # "retinaface" (deep learning, mult mai robust), acceptând un răspuns
    # ceva mai lent (secunde, nu milisecunde) în schimbul unei detecții
    # care chiar funcționează pe poze reale de act.
    deepface_model_name: str = os.getenv("DEEPFACE_MODEL_NAME", "ArcFace")
    deepface_detector_backend: str = os.getenv("DEEPFACE_DETECTOR_BACKEND", "retinaface")

    # Dimensiune maximă acceptată per imagine (bytes) — protecție simplă
    # împotriva upload-urilor abuzive; buletin/selfie n-au nevoie de mai
    # mult de câțiva MB.
    max_image_size_bytes: int = int(os.getenv("MAX_IMAGE_SIZE_BYTES", str(8 * 1024 * 1024)))


settings = Settings()
