"""Retrieval evaluation helpers based on the current in-app retrieval path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from core.types import RetrievalMetrics, VectorStoreBundle
from core.vector_store import retrieve_documents


class RetrievalEvalCase(TypedDict):
    query: str
    relevant_urls: list[str]


def load_eval_cases(path: Path) -> list[RetrievalEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return payload


def reciprocal_rank(retrieved_urls: list[str], relevant_urls: set[str]) -> float:
    for rank, url in enumerate(retrieved_urls, start=1):
        if url in relevant_urls:
            return 1.0 / rank
    return 0.0


def hit_at_k(retrieved_urls: list[str], relevant_urls: set[str], k: int) -> float:
    return 1.0 if any(url in relevant_urls for url in retrieved_urls[:k]) else 0.0


def evaluate_retrieval(
    *,
    store: VectorStoreBundle | None,
    eval_cases_path: Path,
    embedding_model: str,
) -> RetrievalMetrics:
    cases = load_eval_cases(eval_cases_path)
    if not store or not store.documents or not cases:
        return {
            "hit_rate_at_1": 0.0,
            "hit_rate_at_3": 0.0,
            "hit_rate_at_5": 0.0,
            "mrr": 0.0,
            "query_count": len(cases),
        }

    hit_scores_at_1: list[float] = []
    hit_scores_at_3: list[float] = []
    hit_scores_at_5: list[float] = []
    reciprocal_ranks: list[float] = []

    for case in cases:
        retrieved_documents = retrieve_documents(
            store,
            query=case["query"],
            embedding_model=embedding_model,
            top_k=5,
        )
        retrieved_urls = [document["url"] for document in retrieved_documents]
        relevant_urls = set(case["relevant_urls"])

        hit_scores_at_1.append(hit_at_k(retrieved_urls, relevant_urls, 1))
        hit_scores_at_3.append(hit_at_k(retrieved_urls, relevant_urls, 3))
        hit_scores_at_5.append(hit_at_k(retrieved_urls, relevant_urls, 5))
        reciprocal_ranks.append(reciprocal_rank(retrieved_urls, relevant_urls))

    query_count = len(cases)
    return {
        "hit_rate_at_1": sum(hit_scores_at_1) / query_count,
        "hit_rate_at_3": sum(hit_scores_at_3) / query_count,
        "hit_rate_at_5": sum(hit_scores_at_5) / query_count,
        "mrr": sum(reciprocal_ranks) / query_count,
        "query_count": query_count,
    }
