"""Helpers for persisted search documents and report-only reloads."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from core.types import AccuracySummary, FreshnessSummary, SearchDocument
from core.utils import is_recent_date, normalize_company_name, parse_date_value
from core.vector_store import build_vector_store


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


def build_freshness_summary(documents: list[SearchDocument]) -> FreshnessSummary:
    total_documents = len(documents)
    parsed_dates = [
        parse_date_value(document.get("date", ""))
        for document in documents
    ]
    valid_dates = [parsed_date for parsed_date in parsed_dates if parsed_date is not None]
    dated_documents = len(valid_dates)

    sorted_dates = sorted(valid_dates)
    most_recent_date = sorted_dates[-1].isoformat() if sorted_dates else ""
    recent_365d_ratio = (
        sum(1 for document in documents if is_recent_date(document.get("date", ""), days=365)) / total_documents
        if total_documents
        else 0.0
    )

    return {
        "dated_ratio": (dated_documents / total_documents) if total_documents else 0.0,
        "recent_365d_ratio": recent_365d_ratio,
        "most_recent_date": most_recent_date,
    }


def format_freshness_summary(summary: FreshnessSummary) -> str:
    dated_ratio = summary.get("dated_ratio", 0.0)
    recent_365d_ratio = summary.get("recent_365d_ratio", 0.0)
    most_recent_date = summary.get("most_recent_date", "") or "unknown"
    return (
        "freshness: "
        f"dated_ratio={dated_ratio:.0%} | "
        f"recent_365d_ratio={recent_365d_ratio:.0%} | "
        f"most_recent_date={most_recent_date}"
    )


def build_accuracy_summary(documents: list[SearchDocument]) -> AccuracySummary:
    total_documents = len(documents)
    if total_documents == 0:
        return {
            "high_trust_source_ratio": 0.0,
        }

    high_trust_types = {"official", "standard", "paper", "patent"}
    high_trust_count = sum(
        1 for document in documents if document.get("source_type", "") in high_trust_types
    )

    return {
        "high_trust_source_ratio": high_trust_count / total_documents,
    }


def format_accuracy_summary(summary: AccuracySummary) -> str:
    high_trust_source_ratio = summary.get("high_trust_source_ratio", 0.0)
    return f"accuracy: high_trust_source_ratio={high_trust_source_ratio:.0%}"


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
    freshness_summary = build_freshness_summary(documents)
    accuracy_summary = build_accuracy_summary(documents)
    latest_doc_ratio = freshness_summary["recent_365d_ratio"]
    vector_store = build_vector_store(documents, embedding_model=embedding_model)

    return {
        "company_names": company_names,
        "search_documents": documents,
        "search_documents_path": str(input_path),
        "vector_store": vector_store,
        "latest_doc_ratio": latest_doc_ratio,
        "freshness_summary": freshness_summary,
        "accuracy_summary": accuracy_summary,
        "freshness_check_passed": latest_doc_ratio >= latest_doc_ratio_threshold,
    }
