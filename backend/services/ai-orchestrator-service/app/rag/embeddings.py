"""RAG "mic" (task-ul, secțiunea RAG): query -> embeddings -> top 2-3
chunk-uri relevante -> context pentru GPT. NU vector DB, NU reranking, NU
apel extern de embeddings — un TF-IDF + similaritate cosinus, în Python
pur (fără dependențe noi), suficient pentru câteva documente `.md` mici.
Determinist și ușor de testat (vezi tests/test_rag_retrieval.py).
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-zA-ZăâîșțĂÂÎȘȚ0-9]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class TfidfVectorizer:
    """TF-IDF minimal: fit() pe corpusul de chunk-uri (o singură dată, la
    pornirea serviciului), apoi transform() pentru orice text nou (chunk
    sau query) folosind IDF-ul deja învățat.
    """

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._document_count = 0

    def fit(self, documents: list[str]) -> None:
        self._document_count = len(documents)
        document_frequency: Counter[str] = Counter()
        for doc in documents:
            for term in set(tokenize(doc)):
                document_frequency[term] += 1
        # IDF cu netezire (+1 peste tot), ca termenii necunoscuți la query
        # să primească o pondere rezonabilă, nu 0/împărțire la 0.
        self._idf = {
            term: math.log((1 + self._document_count) / (1 + count)) + 1
            for term, count in document_frequency.items()
        }

    def _idf_for(self, term: str) -> float:
        return self._idf.get(term, math.log(1 + self._document_count) + 1)

    def transform(self, text: str) -> dict[str, float]:
        tokens = tokenize(text)
        if not tokens:
            return {}
        term_counts = Counter(tokens)
        total_tokens = len(tokens)
        return {term: (count / total_tokens) * self._idf_for(term) for term, count in term_counts.items()}


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common_terms = set(a) & set(b)
    if not common_terms:
        return 0.0
    numerator = sum(a[term] * b[term] for term in common_terms)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return numerator / (norm_a * norm_b)


def cosine_similarity_dense(a: list[float], b: list[float]) -> float:
    """Similaritate cosinus pentru vectori denși (embeddings reale, ex.
    text-embedding-3-small) — vezi app/rag/retriever.py. Diferă de
    `cosine_similarity` de mai sus doar prin faptul că vectorii sunt liste
    dense, nu dict-uri rare (TF-IDF).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    numerator = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return numerator / (norm_a * norm_b)
