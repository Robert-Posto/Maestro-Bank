"""Teste pentru RAG (embeddings + retrieval) — vezi task-ul:
query -> embeddings -> top 2-3 chunk-uri relevante.

Testăm explicit AMBELE moduri:
  - fallback TF-IDF local (embeddings Azure NEconfigurate) — determinist,
    fără rețea;
  - embeddings reale — cu `create_embeddings` mock-uit (NU consumăm API
    Azure real în teste, vezi task-ul, secțiunea 24), plus un test de
    degradare grațioasă dacă apelul către Azure eșuează la runtime.
"""

import pytest

from app.rag.embeddings import TfidfVectorizer, cosine_similarity, cosine_similarity_dense
from app.rag.retriever import KnowledgeRetriever, get_retriever

# NOTĂ: fără `pytestmark = pytest.mark.asyncio` — pytest.ini are deja
# `asyncio_mode = auto`, deci testele async de mai jos rulează corect
# oricum; un mark explicit la nivel de modul ar afecta greșit și testele
# sincrone de similaritate de mai sus (avertisment inutil de la pytest-asyncio).


def _write_doc(directory, name: str, content: str) -> None:
    (directory / name).write_text(content, encoding="utf-8")


def _force_tfidf_fallback(monkeypatch) -> None:
    """Dezactivează embeddings-urile reale pentru acest test, indiferent
    ce e setat în mediul containerului (AZURE_OPENAI_ENDPOINT etc.)."""
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_endpoint", "")
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_api_key", "")


# --- funcții pure de similaritate -----------------------------------------


def test_cosine_similarity_identical_vectors_is_one():
    vectorizer = TfidfVectorizer()
    vectorizer.fit(["buffer de siguranță pentru cheltuieli", "forecast de sold la finalul lunii"])
    vector = vectorizer.transform("buffer de siguranță pentru cheltuieli")
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_similarity_unrelated_texts_is_low():
    vectorizer = TfidfVectorizer()
    vectorizer.fit(["buffer de siguranță pentru cheltuieli", "rețetă de prăjitură cu mere"])
    a = vectorizer.transform("buffer de siguranță pentru cheltuieli")
    b = vectorizer.transform("rețetă de prăjitură cu mere")
    assert cosine_similarity(a, b) < 0.2


def test_cosine_similarity_dense_identical_is_one():
    assert cosine_similarity_dense([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_dense_orthogonal_is_zero():
    assert cosine_similarity_dense([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_dense_mismatched_length_is_zero():
    assert cosine_similarity_dense([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


# --- fallback TF-IDF (embeddings neconfigurate) ---------------------------


async def test_retriever_finds_relevant_chunk(tmp_path, monkeypatch):
    _force_tfidf_fallback(monkeypatch)
    _write_doc(
        tmp_path,
        "buffer.md",
        "# Buffer\n\n## Ce este bufferul de siguranță\nBufferul de siguranță e o rezervă pentru cheltuieli neprevăzute.\n",
    )
    _write_doc(
        tmp_path,
        "categories.md",
        "# Categorii\n\n## Categorii de cheltuieli\nAlimentație, shopping, transport, facturi, restaurante.\n",
    )
    retriever = KnowledgeRetriever(knowledge_dir=tmp_path)

    hits = await retriever.retrieve("ce este bufferul de siguranță", top_k=3)

    assert hits, "ar trebui să găsească cel puțin un chunk relevant"
    top_chunk, top_score = hits[0]
    assert top_chunk.source == "buffer.md"
    assert top_score > 0


async def test_retriever_respects_top_k(tmp_path, monkeypatch):
    _force_tfidf_fallback(monkeypatch)
    for i in range(5):
        _write_doc(tmp_path, f"doc{i}.md", f"# Doc {i}\n\n## Secțiune\nText despre cheltuieli și buffer {i}.\n")
    retriever = KnowledgeRetriever(knowledge_dir=tmp_path)

    hits = await retriever.retrieve("cheltuieli și buffer", top_k=2)

    assert len(hits) <= 2


async def test_retriever_returns_empty_for_irrelevant_query(tmp_path, monkeypatch):
    _force_tfidf_fallback(monkeypatch)
    _write_doc(tmp_path, "buffer.md", "# Buffer\n\n## Buffer\nBufferul de siguranță pentru cheltuieli.\n")
    retriever = KnowledgeRetriever(knowledge_dir=tmp_path)

    hits = await retriever.retrieve("rețetă de prăjitură cu mere și scorțișoară", top_k=3, min_score=0.3)

    assert hits == []


async def test_retriever_empty_knowledge_dir_returns_empty(tmp_path, monkeypatch):
    _force_tfidf_fallback(monkeypatch)
    retriever = KnowledgeRetriever(knowledge_dir=tmp_path)
    assert await retriever.retrieve("orice întrebare") == []


async def test_real_knowledge_base_answers_buffer_question(monkeypatch):
    """Verificare end-to-end pe documentele reale din app/rag/knowledge/."""
    _force_tfidf_fallback(monkeypatch)
    retriever = get_retriever()
    hits = await retriever.retrieve("ce este bufferul de siguranță recomandat", top_k=3)
    assert hits
    assert any(chunk.source == "safety_buffer.md" for chunk, _score in hits)


# --- embeddings reale (mock-uite) -----------------------------------------

# Vectori-jucărie 2D, aleși ca query-ul să fie clar mai aproape de chunk-ul
# despre buffer decât de cel despre categorii (nu contează valorile reale
# ale unui embedding adevărat, doar geometria relativă).
_BUFFER_VECTOR = [1.0, 0.0]
_CATEGORIES_VECTOR = [0.0, 1.0]
_QUERY_VECTOR = [0.9, 0.1]


async def test_retriever_uses_real_embeddings_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_endpoint", "https://fake.openai.azure.com")
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_api_key", "fake-key")

    _write_doc(tmp_path, "buffer.md", "# Buffer\n\n## Buffer\nBufferul de siguranță pentru cheltuieli.\n")
    _write_doc(tmp_path, "categories.md", "# Categorii\n\n## Categorii\nCategorii de cheltuieli.\n")
    retriever = KnowledgeRetriever(knowledge_dir=tmp_path)

    calls: list[list[str]] = []

    async def fake_create_embeddings(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        if len(texts) == 1:  # apelul pentru query
            return [_QUERY_VECTOR]
        return [_BUFFER_VECTOR, _CATEGORIES_VECTOR]  # apelul pentru chunk-uri, în ordinea încărcării (alfabetică)

    monkeypatch.setattr("app.rag.retriever.create_embeddings", fake_create_embeddings)

    hits = await retriever.retrieve("ce e bufferul?", top_k=1, min_score=0.5)

    assert len(calls) == 2, "un apel pentru chunk-uri (o singură dată) + unul pentru query"
    assert hits[0][0].source == "buffer.md"


async def test_retriever_falls_back_to_tfidf_when_embeddings_call_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_endpoint", "https://fake.openai.azure.com")
    monkeypatch.setattr("app.rag.retriever.settings.azure_openai_embedding_api_key", "fake-key")

    _write_doc(tmp_path, "buffer.md", "# Buffer\n\n## Ce este bufferul\nBufferul de siguranță pentru cheltuieli neprevăzute.\n")
    retriever = KnowledgeRetriever(knowledge_dir=tmp_path)

    async def failing_create_embeddings(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Azure indisponibil (simulat)")

    monkeypatch.setattr("app.rag.retriever.create_embeddings", failing_create_embeddings)

    # NU trebuie să arunce excepție — degradare grațioasă pe TF-IDF.
    hits = await retriever.retrieve("ce este bufferul de siguranță")

    assert hits
    assert hits[0][0].source == "buffer.md"
