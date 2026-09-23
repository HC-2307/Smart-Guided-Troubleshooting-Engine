"""Multi-stage action matcher for the trusted Settings catalog.

Matching order:
1. exact normalized message match
2. keyword/token scoring over message + descriptions
3. TF-IDF cosine similarity over catalog text

The matcher never invents a deeplink; it only returns an existing catalog entry.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "or", "for", "on", "in", "my",
    "your", "phone", "device", "settings", "setting", "page", "screen",
    "open", "opens", "view", "check", "go", "goes", "tap", "select",
}

ALIASES = {
    "backup": "back up",
    "back-up": "back up",
    "wi-fi": "wifi",
    "wireless fidelity": "wifi",
    "apps": "app",
    "applications": "app",
    "display": "screen",
    "power": "battery",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("_", " ").replace("-", " ")
    for old, new in ALIASES.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    return [t for t in normalize_text(text).split() if t and t not in STOPWORDS]


def _token_score(query: str, document: str) -> float:
    q = set(tokens(query))
    d = set(tokens(document))
    if not q or not d:
        return 0.0
    return len(q & d) / len(q)


def _sequence_score(query: str, document: str) -> float:
    return SequenceMatcher(None, normalize_text(query), normalize_text(document)).ratio()


@dataclass
class MatchResult:
    entry: dict[str, Any] | None
    strategy: str
    score: float
    candidates: list[dict[str, Any]]


class ActionMatcher:
    def __init__(self, catalog: list[dict[str, Any]], semantic_threshold: float = 0.34):
        self.catalog = catalog
        self.semantic_threshold = semantic_threshold
        self._idf: dict[str, float] = {}
        self._vectors: list[dict[str, float]] = []
        self._build_tfidf_index()

    @staticmethod
    def searchable_text(entry: dict[str, Any]) -> str:
        return " ".join(
            str(entry.get(k, "") or "")
            for k in ("message", "description", "qna_description", "originalType", "validation")
        )

    def _build_tfidf_index(self) -> None:
        docs = [tokens(self.searchable_text(e)) for e in self.catalog]
        n = max(len(docs), 1)
        df = Counter()
        for doc in docs:
            for term in set(doc):
                df[term] += 1

        self._idf = {
            term: math.log((1 + n) / (1 + freq)) + 1
            for term, freq in df.items()
        }

        self._vectors = [self._vector(doc) for doc in docs]

    def _vector(self, doc: list[str]) -> dict[str, float]:
        counts = Counter(doc)
        total = max(sum(counts.values()), 1)
        return {
            term: (count / total) * self._idf.get(term, 1.0)
            for term, count in counts.items()
        }

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(v * b.get(k, 0.0) for k, v in a.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    def match(self, action_name: str, context: str = "") -> MatchResult:
        query = " ".join(x for x in (action_name, context) if x).strip()
        normalized_name = normalize_text(action_name)

        # 1) Exact message. Duplicate messages are disambiguated with context.
        exact = [
            e for e in self.catalog
            if normalize_text(str(e.get("message", ""))) == normalized_name
        ]
        if exact:
            if len(exact) == 1 or not context:
                return MatchResult(exact[0], "exact", 1.0, exact[:5])

            ranked = sorted(
                exact,
                key=lambda e: (
                    _token_score(context, self.searchable_text(e)),
                    _sequence_score(context, self.searchable_text(e)),
                ),
                reverse=True,
            )
            score = _token_score(context, self.searchable_text(ranked[0]))
            return MatchResult(ranked[0], "exact+context", score, ranked[:5])

        # 2) Keyword/token scoring. Score all candidates and retain useful evidence.
        ranked_keyword = []
        for e in self.catalog:
            text = self.searchable_text(e)
            token_score = _token_score(query, text)
            seq = _sequence_score(action_name, str(e.get("message", "")))
            # Action name gets extra weight; context resolves ambiguous generic names.
            score = 0.72 * token_score + 0.28 * seq
            ranked_keyword.append((score, e))

        ranked_keyword.sort(key=lambda x: x[0], reverse=True)
        best_score, best_entry = ranked_keyword[0]
        if best_score >= 0.56:
            return MatchResult(
                best_entry, "keyword", best_score,
                [e for _, e in ranked_keyword[:5]],
            )

        # 3) TF-IDF cosine fallback.
        qvec = self._vector(tokens(query))
        ranked_semantic = [
            (self._cosine(qvec, vec), entry)
            for vec, entry in zip(self._vectors, self.catalog)
        ]
        ranked_semantic.sort(key=lambda x: x[0], reverse=True)
        sem_score, sem_entry = ranked_semantic[0]

        # Combine lexical and TF-IDF evidence so a single accidental overlap
        # does not create a trusted mapping.
        combined = 0.65 * sem_score + 0.35 * best_score
        if combined >= self.semantic_threshold:
            return MatchResult(
                sem_entry, "semantic", combined,
                [e for _, e in ranked_semantic[:5]],
            )

        return MatchResult(
            None, "unresolved", combined,
            [e for _, e in ranked_semantic[:5]],
        )
