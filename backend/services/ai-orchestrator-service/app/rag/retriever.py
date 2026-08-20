"""Încarcă documentele `.md` din app/rag/knowledge/ (knowledge CONTEXTUAL —
NU date live ale userului, vezi task-ul), le împarte în chunk-uri pe
secțiuni ("## Titlu") și expune `retrieve(query)` -> top 2-3 chunk-uri
relevante, cu scor.

Două moduri, alese automat:
  - embeddings REALE (Azure OpenAI, ex. text-embedding-3-small) — dacă
    AZURE_OPENAI_EMBEDDING_ENDPOINT/API_KEY sunt configurate. Înțeleg
    sinonime/parafrazări, nu doar suprapunere de cuvinte.
  - fallback TF-IDF local (app/rag/embeddings.py) — dacă embeddings NU
    sunt configurate, sau dacă apelul către Azure eșuează la runtime.
    Serviciul funcționează oricum, doar mai puțin "inteligent" semantic.

Embeddings-urile chunk-urilor se calculează O SINGURĂ DATĂ (cache la
nivel de proces, lazy la primul `retrieve()`) — documentele sunt statice.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.llm.azure_openai import create_embeddings
from app.rag.embeddings import TfidfVectorizer, cosine_similarity, cosine_similarity_dense

logger = logging.getLogger("ai-orchestrator-service.rag")

_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
_SECTION_SPLIT_RE = re.compile(r"\n(?=## )")

# Similaritatea embeddings reale trăiește într-un interval diferit de cea
# TF-IDF (rareori aproape de 0, chiar și pentru text nerelevant) — praguri
# separate, calibrate empiric pentru fiecare mod.
_MIN_SCORE_EMBEDDING = 0.2
_MIN_SCORE_TFIDF = 0.05


@dataclass(frozen=True)
class Chunk:
    source: str
    text: str


def _load_chunks(knowledge_dir: Path = _KNOWLEDGE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        for section in _SECTION_SPLIT_RE.split(content):
            section = section.strip()
            if section:
                chunks.append(Chunk(source=path.name, text=section))
    return chunks


class KnowledgeRetriever:
    def __init__(self, knowledge_dir: Path = _KNOWLEDGE_DIR) -> None:
        self._chunks = _load_chunks(knowledge_dir)

        # Fallback TF-IDF — construit mereu, e ieftin și local (fără rețea).
        self._tfidf_vectorizer = TfidfVectorizer()
        self._tfidf_vectorizer.fit([chunk.text for chunk in self._chunks])
        self._tfidf_vectors = [self._tfidf_vectorizer.transform(chunk.text) for chunk in self._chunks]

        # Embeddings reale — populate lazy, la primul retrieve() (necesită
        # un apel de rețea). `None` = încă nu s-a încercat; listă goală
        # goală imposibilă cu chunk-uri existente, deci fără ambiguitate.
        self._embedding_vectors: list[list[float]] | None = None
        self._embeddings_unavailable = not self._chunks

    async def _ensure_embeddings(self) -> None:
        if self._embedding_vectors is not None or self._embeddings_unavailable:
            return
        if not settings.azure_embeddings_configured:
            self._embeddings_unavailable = True
            return
        try:
            self._embedding_vectors = await create_embeddings([chunk.text for chunk in self._chunks])
            logger.info("RAG: embeddings reale calculate pentru %s chunk-uri (%s)", len(self._chunks), settings.azure_openai_embedding_deployment)
        except Exception as exc:  # noqa: BLE001 — orice eroare de la Azure -> fallback, nu blocăm chat-ul
            logger.warning("RAG: embeddings reale indisponibile, folosesc fallback TF-IDF (%s)", exc)
            self._embeddings_unavailable = True

    async def retrieve(self, query: str, top_k: int = 3, min_score: float | None = None) -> list[tuple[Chunk, float]]:
        if not self._chunks:
            return []

        await self._ensure_embeddings()

        if self._embedding_vectors is not None:
            try:
                query_vector = (await create_embeddings([query]))[0]
                scored = [
                    (chunk, cosine_similarity_dense(query_vector, vector))
                    for chunk, vector in zip(self._chunks, self._embedding_vectors)
                ]
                threshold = min_score if min_score is not None else _MIN_SCORE_EMBEDDING
                return self._top(scored, top_k, threshold)
            except Exception as exc:  # noqa: BLE001 — eroare la query -> fallback TF-IDF pentru ACEST request
                logger.warning("RAG: embeddings pentru query eșuate, cad pe TF-IDF (%s)", exc)

        query_vector = self._tfidf_vectorizer.transform(query)
        scored = [
            (chunk, cosine_similarity(query_vector, vector)) for chunk, vector in zip(self._chunks, self._tfidf_vectors)
        ]
        threshold = min_score if min_score is not None else _MIN_SCORE_TFIDF
        return self._top(scored, top_k, threshold)

    @staticmethod
    def _top(scored: list[tuple[Chunk, float]], top_k: int, min_score: float) -> list[tuple[Chunk, float]]:
        scored.sort(key=lambda item: item[1], reverse=True)
        return [(chunk, score) for chunk, score in scored[:top_k] if score >= min_score]


_retriever: KnowledgeRetriever | None = None


def get_retriever() -> KnowledgeRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KnowledgeRetriever()
    return _retriever
