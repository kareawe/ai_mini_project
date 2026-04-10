"""Web search agent."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from prompts.web_search import WEB_SEARCH_SYSTEM_PROMPT, build_search_prompt

from agents.search_store import (
    build_accuracy_summary,
    build_freshness_summary,
    format_accuracy_summary,
    format_freshness_summary,
    save_search_documents,
)
from agents.types import SearchDocument, WorkflowState
from agents.utils import fetch_page_date, get_client, infer_source_type
from agents.vector_store import build_vector_store


TECH_QUERY_GROUPS = [
    (
        "tech_overview",
        [
            "{technology} latest roadmap",
            "{technology} architecture standard latest",
        ],
    ),
    (
        "risk",
        [
            "{technology} yield thermal power cost issue",
        ],
    ),
    (
        "ecosystem",
        [
            "{technology} ecosystem partnership supply chain",
        ],
    ),
]

COMPANY_QUERY_GROUPS = [
    (
        "company_tech",
        [
            "{company} {technology} latest",
            "{company} {technology} roadmap",
        ],
    ),
    (
        "maturity",
        [
            "{company} {technology} sample qualification mass production",
            "{company} {technology} prototype demo validation shipment",
        ],
    ),
    (
        "risk",
        [
            "{company} {technology} challenge limitation issue",
        ],
    ),
    (
        "ecosystem",
        [
            "{company} {technology} partner customer collaboration",
        ],
    ),
]


class SearchHit(BaseModel):
    title: str
    url: str
    content: str


class SearchOutput(BaseModel):
    documents: list[SearchHit] = Field(default_factory=list)


def _parse_fallback_documents(text: str) -> list[SearchHit]:
    try:
        payload = json.loads(text)
        documents = payload.get("documents", [])
        return [SearchHit(**item) for item in documents if isinstance(item, dict)]
    except Exception:
        pass

    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    documents: list[SearchHit] = []
    for chunk in chunks:
        title = ""
        url = ""
        content = ""
        for line in chunk.splitlines():
            cleaned = line.strip()
            lowered = cleaned.lower()
            if lowered.startswith("title:"):
                title = cleaned.split(":", 1)[1].strip()
            elif lowered.startswith("url:"):
                url = cleaned.split(":", 1)[1].strip()
            elif lowered.startswith("content:"):
                content = cleaned.split(":", 1)[1].strip()
        if title and url and content:
            documents.append(SearchHit(title=title, url=url, content=content))
    return documents


def _dedupe_documents(documents: Iterable[SearchDocument]) -> list[SearchDocument]:
    seen_urls: set[str] = set()
    deduped: list[SearchDocument] = []
    for document in documents:
        url = document["url"]
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(document)
    return deduped


def _search_query(
    *,
    client,
    model: str,
    technology: str,
    company: str,
    query_group: str,
    query_text: str,
    max_results: int,
) -> list[SearchDocument]:
    prompt = build_search_prompt(
        technology=technology,
        company=company,
        query_group=query_group,
        query_text=query_text,
        max_results=max_results,
    )
    parsed = SearchOutput()
    try:
        response = client.responses.parse(
            model=model,
            instructions=WEB_SEARCH_SYSTEM_PROMPT,
            input=prompt,
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
            text_format=SearchOutput,
            temperature=0,
            max_output_tokens=1200,
        )
        parsed = response.output_parsed or SearchOutput()
    except Exception:
        fallback_response = client.responses.create(
            model=model,
            instructions=WEB_SEARCH_SYSTEM_PROMPT,
            input=prompt
            + "\n\nReturn plain text blocks in this exact format:\n"
            + "Title: ...\nURL: ...\nContent: ...\n",
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
            temperature=0,
            max_output_tokens=1200,
        )
        parsed = SearchOutput(documents=_parse_fallback_documents(fallback_response.output_text))

    documents: list[SearchDocument] = []
    for item in parsed.documents:
        url = item.url.strip()
        document: SearchDocument = {
            "title": item.title.strip(),
            "url": url,
            "date": fetch_page_date(url),
            "source_type": infer_source_type(url, company or technology),
            "query_group": query_group,
            "query_text": query_text,
            "technology": technology,
            "company": company,
            "content": item.content.strip(),
        }
        documents.append(document)
    return documents


def _apply_recency_retry_hint(query_text: str, retry_count: int) -> str:
    if retry_count <= 0:
        return query_text
    current_year = datetime.utcnow().year
    previous_year = current_year - 1
    return f"{query_text} {current_year} {previous_year} latest"


def _collect_documents(
    *,
    client,
    model: str,
    technology: str,
    company: str,
    query_groups: list[tuple[str, list[str]]],
    min_docs: int,
    max_docs_per_query: int,
    retry_count: int,
) -> list[SearchDocument]:
    collected: list[SearchDocument] = []
    scope = f"technology={technology}" if not company else f"technology={technology} company={company}"

    for query_group, templates in query_groups:
        if len(collected) >= min_docs:
            break

        for template in templates:
            query_text = _apply_recency_retry_hint(
                template.format(company=company, technology=technology),
                retry_count,
            )
            mode = "company" if company else "technology"
            print(
                f"[web_search] mode={mode} query_group={query_group} query={query_text}",
                flush=True,
            )
            documents = _search_query(
                client=client,
                model=model,
                technology=technology,
                company=company,
                query_group=query_group,
                query_text=query_text,
                max_results=max_docs_per_query,
            )
            collected.extend(documents)
            collected = _dedupe_documents(collected)
            print(
                f"[web_search] {scope} collected={len(collected)}/{min_docs}",
                flush=True,
            )
            if len(collected) >= min_docs:
                break

    return collected

def run_web_search(
    state: WorkflowState,
    *,
    model: str,
    embedding_model: str,
    tech_min_docs: int,
    company_min_docs: int,
    max_docs_per_query: int,
) -> dict:
    client = get_client()
    retry_count = state.get("web_search_retry_count", 0)
    print(f"[web_search] retry_count={retry_count}", flush=True)

    all_documents: list[SearchDocument] = []
    analysis_companies = [state["our_company"], *state.get("company_names", [])]

    for technology in state["target_technologies"]:
        print(f"[web_search] technology={technology}", flush=True)
        technology_documents = _collect_documents(
            client=client,
            model=model,
            technology=technology,
            company="",
            query_groups=TECH_QUERY_GROUPS,
            min_docs=tech_min_docs,
            max_docs_per_query=max_docs_per_query,
            retry_count=retry_count,
        )

        all_documents.extend(technology_documents)
        print(
            f"[web_search] technology={technology} final_count={len(technology_documents)}",
            flush=True,
        )

        for company in analysis_companies:
            print(f"[web_search] technology={technology} company={company}", flush=True)
            company_documents = _collect_documents(
                client=client,
                model=model,
                technology=technology,
                company=company,
                query_groups=COMPANY_QUERY_GROUPS,
                min_docs=company_min_docs,
                max_docs_per_query=max_docs_per_query,
                retry_count=retry_count,
            )

            all_documents.extend(company_documents)
            print(
                f"[web_search] technology={technology} company={company} "
                f"final_count={len(company_documents)}",
                flush=True,
            )

    deduped_documents = _dedupe_documents(all_documents)
    vector_store = build_vector_store(deduped_documents, embedding_model=embedding_model)
    # Freshness is checked after the full search pass so the supervisor can decide
    # whether another search round is worth paying for.
    freshness_summary = build_freshness_summary(deduped_documents)
    accuracy_summary = build_accuracy_summary(deduped_documents)
    latest_doc_ratio = freshness_summary["recent_365d_ratio"]
    freshness_check_passed = latest_doc_ratio >= state.get("latest_doc_ratio_threshold", 0.3)
    search_documents_path = state.get("search_documents_path", "outputs/search_documents.json")
    output_path = Path(search_documents_path)
    save_search_documents(output_path, deduped_documents)
    print(f"Saved search documents: {output_path} ({len(deduped_documents)} items)", flush=True)
    print(f"[web_search] {format_freshness_summary(freshness_summary)}", flush=True)
    print(f"[web_search] {format_accuracy_summary(accuracy_summary)}", flush=True)
    print(
        f"[web_search] freshness_check_passed={freshness_check_passed} "
        f"latest_doc_ratio={latest_doc_ratio:.2f}",
        flush=True,
    )

    return {
        "search_documents": deduped_documents,
        "search_documents_path": str(output_path),
        "vector_store": vector_store,
        "latest_doc_ratio": latest_doc_ratio,
        "freshness_summary": freshness_summary,
        "accuracy_summary": accuracy_summary,
        "freshness_check_passed": freshness_check_passed,
    }
