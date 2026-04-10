"""Helpers for persisted search documents and report-only reloads."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from agents.types import SearchDocument
from agents.utils import is_recent_date, normalize_company_name
from agents.vector_store import build_vector_store


def load_search_documents(path: Path) -> list[SearchDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return payload


def save_search_documents(path: Path, documents: list[SearchDocument]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(documents, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def infer_companies_from_documents(
    documents: list[SearchDocument],
    our_company: str,
    max_companies: int,
) -> list[str]:
    counter: Counter[str] = Counter()
    for document in documents:
        company = normalize_company_name(document.get("company", ""))
        if not company or company == our_company:
            continue
        counter[company] += 1
    return [company for company, _count in counter.most_common(max_companies)]


def calculate_latest_doc_ratio(documents: list[SearchDocument]) -> float:
    if not documents:
        return 0.0
    recent_count = sum(1 for document in documents if is_recent_date(document.get("date", "")))
    return recent_count / len(documents)


def load_saved_search_context(
    *,
    input_path: Path,
    our_company: str,
    max_companies: int,
    embedding_model: str,
    latest_doc_ratio_threshold: float,
) -> dict:
    documents = load_search_documents(input_path)
    company_names = infer_companies_from_documents(
        documents,
        our_company=our_company,
        max_companies=max_companies,
    )
    latest_doc_ratio = calculate_latest_doc_ratio(documents)
    vector_store = build_vector_store(documents, embedding_model=embedding_model)

    return {
        "company_names": company_names,
        "search_documents": documents,
        "search_documents_path": str(input_path),
        "vector_store": vector_store,
        "latest_doc_ratio": latest_doc_ratio,
        "freshness_check_passed": latest_doc_ratio >= latest_doc_ratio_threshold,
    }
