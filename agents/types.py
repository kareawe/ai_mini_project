"""Shared types for the workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


class SearchDocument(TypedDict):
    title: str
    url: str
    date: str
    source_type: str
    query_group: str
    query_text: str
    technology: str
    company: str
    content: str


@dataclass
class VectorStoreBundle:
    index: Any
    documents: list[SearchDocument]
    dimension: int


class WorkflowState(TypedDict, total=False):
    user_query: str
    our_company: str
    target_technologies: list[str]
    next_action: Literal["company_discovery", "web_search", "report", "formatting", "end"]
    company_names: list[str]
    search_documents: list[SearchDocument]
    vector_store: VectorStoreBundle
    draft_report: str
    final_report: str
    output_path: str
    search_documents_path: str
    search_documents_input_path: str
    report_only: bool
    model: str
    report_model: str
    embedding_model: str
    max_companies: int
    tech_min_docs: int
    company_min_docs: int
    max_docs_per_query: int
    max_web_search_retries: int
    latest_doc_ratio_threshold: float
    web_search_retry_count: int
    latest_doc_ratio: float
    freshness_check_passed: bool
    company_discovery_done: bool
    web_search_done: bool
    report_done: bool
    formatting_done: bool
