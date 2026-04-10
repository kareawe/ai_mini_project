"""FAISS-backed retrieval helpers."""

from __future__ import annotations

from typing import Sequence

import faiss
import numpy as np

from agents.types import SearchDocument, VectorStoreBundle
from agents.utils import is_recent_date


def _batched(items: Sequence[str], batch_size: int) -> list[list[str]]:
    return [list(items[index : index + batch_size]) for index in range(0, len(items), batch_size)]


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


_EMBEDDING_MODELS: dict[str, object] = {}


def _get_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    model = _EMBEDDING_MODELS.get(model_name)
    if model is None:
        # Reuse the locally cached model first so evaluation and report-only runs
        # can work without network access.
        try:
            model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            model = SentenceTransformer(model_name)
        _EMBEDDING_MODELS[model_name] = model
    return model


def build_vector_store(
    documents: list[SearchDocument],
    embedding_model: str,
) -> VectorStoreBundle | None:
    if not documents:
        return None

    texts = [document["content"] for document in documents]
    model = _get_embedding_model(embedding_model)
    matrix = np.array(model.encode(texts, batch_size=32, show_progress_bar=False), dtype="float32")
    matrix = _normalize_rows(matrix)

    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    return VectorStoreBundle(index=index, documents=documents, dimension=matrix.shape[1])


def retrieve_documents(
    store: VectorStoreBundle | None,
    query: str,
    embedding_model: str,
    top_k: int = 4,
) -> list[SearchDocument]:
    if not store or not store.documents:
        return []

    model = _get_embedding_model(embedding_model)
    query_vector = np.array(model.encode([query], show_progress_bar=False), dtype="float32")
    query_vector = _normalize_rows(query_vector)

    limit = min(max(top_k * 3, top_k), len(store.documents))
    scores, indices = store.index.search(query_vector, limit)

    candidates: list[tuple[float, int]] = []
    for score, index in zip(scores[0], indices[0]):
        if index < 0:
            continue
        candidates.append((float(score), int(index)))

    ranked = sorted(
        candidates,
        key=lambda item: item[0] + (0.15 if is_recent_date(store.documents[item[1]].get("date", "")) else 0.0),
        reverse=True,
    )

    matches: list[SearchDocument] = []
    for _score, index in ranked[:top_k]:
        matches.append(store.documents[index])
    return matches
