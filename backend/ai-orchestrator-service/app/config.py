"""Configurație citită din variabile de mediu. Nimic hardcodat aici."""

import os


class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Support Agent vorbește cu restul sistemului EXCLUSIV prin Gateway,
    # exact ca orice alt client (Angular inclusiv) — nu are bază de date
    # proprie și nu importă module din alte microservicii. Adresă INTERNĂ
    # Docker — browserul nu o accesează niciodată direct.
    gateway_url: str = os.getenv("GATEWAY_URL", "http://gateway:8000")

    # --- Azure OpenAI (GPT-5-mini) ---------------------------------------
    # Necompletate implicit — serviciul pornește și răspunde la /health
    # chiar și fără ele; doar POST /support eșuează explicit dacă lipsesc
    # (vezi app/llm/azure_openai.py). NU hardcoda vreo cheie aici.
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini").strip()
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()

    # Plafon de siguranță pentru bucla de tool-calling (vezi app/agents/support.py)
    # — evită o buclă infinită dacă modelul nu ajunge niciodată la respond_to_user.
    agent_max_tool_iterations: int = int(os.getenv("SUPPORT_AGENT_MAX_TOOL_ITERATIONS", "6"))


settings = Settings()
