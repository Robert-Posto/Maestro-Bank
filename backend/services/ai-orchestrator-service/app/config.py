"""Configurație citită din variabile de mediu. Nimic hardcodat aici — vezi
task-ul Spending + Forecast Agent, secțiunea 6: "NU hardcoda API key,
endpoint, deployment name, secrets."
"""

import os


class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-development")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Adresă INTERNĂ Docker a API Gateway-ului — agentul NU accesează
    # MongoDB sau microserviciile direct, doar prin Gateway (vezi
    # app/tools/*), exact ca un client extern (Angular) ar face.
    gateway_url: str = os.getenv("GATEWAY_URL", "http://gateway:8000")

    # --- Azure OpenAI (GPT-5-mini) --------------------------------------
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
    azure_openai_api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    # Timeout per apel către Azure (chat SAU embeddings) — vezi
    # app/llm/azure_openai.py::_build_client pentru context complet.
    azure_openai_request_timeout_seconds: float = float(os.getenv("AZURE_OPENAI_REQUEST_TIMEOUT_SECONDS", "45.0"))

    # --- Azure OpenAI embeddings (RAG — vezi app/rag/) -------------------
    # Opțional: dacă lipsesc, RAG-ul cade automat pe TF-IDF local (vezi
    # app/rag/retriever.py) — nu deja nimic nu se strică fără ele. Implicit
    # ENDPOINT/API_KEY cad pe aceleași valori ca la chat (de obicei aceeași
    # resursă Azure), dar pot fi suprascrise separat dacă e nevoie.
    azure_openai_embedding_endpoint: str = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT") or os.getenv(
        "AZURE_OPENAI_ENDPOINT", ""
    )
    azure_openai_embedding_api_key: str = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY") or os.getenv(
        "AZURE_OPENAI_API_KEY", ""
    )
    azure_openai_embedding_deployment: str = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

    # Timeout pentru apelurile HTTP către Gateway (tools) — vezi secțiunea
    # 20: "setează timeout-uri, dacă un microserviciu nu răspunde întoarce
    # o eroare controlată."
    gateway_timeout_seconds: float = float(os.getenv("GATEWAY_TIMEOUT_SECONDS", "8.0"))

    # Limită de siguranță pentru bucla tool-calling (vezi app/agents) —
    # evită o buclă infinită dacă modelul tot cere tool-uri.
    max_tool_call_rounds: int = int(os.getenv("AI_MAX_TOOL_CALL_ROUNDS", "4"))

    @property
    def azure_openai_configured(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    @property
    def azure_embeddings_configured(self) -> bool:
        return bool(self.azure_openai_embedding_endpoint and self.azure_openai_embedding_api_key)


settings = Settings()
