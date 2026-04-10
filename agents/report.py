"""Report generation agent."""

from __future__ import annotations

from prompts.report import REPORT_SYSTEM_PROMPT, build_report_prompt

from agents.types import SearchDocument, WorkflowState
from agents.utils import get_client, json_dumps
from agents.vector_store import retrieve_documents


def _trl_range_from_documents(documents: list[SearchDocument]) -> str:
    text = " ".join(document["content"].lower() for document in documents)
    if any(keyword in text for keyword in ("mass production", "commercial shipment", "in production")):
        return "TRL 8-9"
    if any(keyword in text for keyword in ("qualification", "sample", "validation", "customer")):
        return "TRL 6-8"
    if any(keyword in text for keyword in ("prototype", "demo", "proof-of-concept")):
        return "TRL 4-6"
    if any(keyword in text for keyword in ("paper", "research", "patent")):
        return "TRL 2-4"
    return "TRL 3-5"


def _evidence_rows(documents: list[SearchDocument]) -> list[dict]:
    rows: list[dict] = []
    for document in documents:
        rows.append(
            {
                "title": document["title"],
                "company": document["company"] or "General",
                "date": document["date"] or "unknown",
                "source_type": document["source_type"],
                "query_group": document["query_group"],
                "url": document["url"],
                "content": document["content"],
            }
        )
    return rows


def _retrieve_evidence_group(
    state: WorkflowState,
    *,
    query: str,
    embedding_model: str,
    top_k: int,
) -> list[SearchDocument]:
    return retrieve_documents(
        state.get("vector_store"),
        query=query,
        embedding_model=embedding_model,
        top_k=top_k,
    )


def _build_evidence_package(state: WorkflowState, embedding_model: str) -> dict:
    our_company = state["our_company"]
    analysis_companies = [our_company, *state.get("company_names", [])]
    package: dict = {
        "self_company": our_company,
        "technologies": [],
    }

    for technology in state["target_technologies"]:
        # Each section is grounded with a small, purpose-specific evidence slice
        # so the report agent is less likely to repeat the same raw snippets.
        overview_docs = _retrieve_evidence_group(
            state,
            query=f"{technology} roadmap architecture standard latest",
            embedding_model=embedding_model,
            top_k=5,
        )
        risk_docs = _retrieve_evidence_group(
            state,
            query=f"{technology} yield thermal power cost issue challenge",
            embedding_model=embedding_model,
            top_k=4,
        )
        ecosystem_docs = _retrieve_evidence_group(
            state,
            query=f"{technology} ecosystem partnership supply chain customer collaboration",
            embedding_model=embedding_model,
            top_k=4,
        )

        company_blocks: list[dict] = []
        combined_company_docs: list[SearchDocument] = []
        for company in analysis_companies:
            company_docs = _retrieve_evidence_group(
                state,
                query=f"{company} {technology} roadmap qualification sample validation latest",
                embedding_model=embedding_model,
                top_k=3,
            )
            combined_company_docs.extend(company_docs)
            company_blocks.append(
                {
                    "company": company,
                    "role": "self" if company == our_company else "competitor",
                    "trl_range": _trl_range_from_documents(company_docs or overview_docs),
                    "documents": _evidence_rows(company_docs),
                }
            )

        package["technologies"].append(
            {
                "technology": technology,
                "trl_range": _trl_range_from_documents(combined_company_docs or overview_docs),
                "overview_documents": _evidence_rows(overview_docs),
                "risk_documents": _evidence_rows(risk_docs),
                "ecosystem_documents": _evidence_rows(ecosystem_docs),
                "company_documents": company_blocks,
            }
        )

    return package


def _build_references(documents: list[SearchDocument]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for document in sorted(documents, key=lambda item: (item["date"] or "", item["title"]), reverse=True):
        if document["url"] in seen:
            continue
        seen.add(document["url"])
        date = document["date"] or "unknown"
        source_type = document["source_type"]
        lines.append(f"- {document['title']} | {date} | {source_type} | {document['url']}")
    return "\n".join(lines)


def run_report(
    state: WorkflowState,
    *,
    model: str,
    embedding_model: str,
) -> dict:
    client = get_client()
    evidence_package = _build_evidence_package(state, embedding_model=embedding_model)
    references = _build_references(state.get("search_documents", []))
    print(
        f"[report] technologies={len(state.get('target_technologies', []))} "
        f"companies={len(state.get('company_names', [])) + 1} "
        f"references={len(references.splitlines()) if references else 0}",
        flush=True,
    )

    response = client.responses.create(
        model=model,
        instructions=REPORT_SYSTEM_PROMPT,
        input=build_report_prompt(
            our_company=state["our_company"],
            target_technologies=state["target_technologies"],
            company_names=state.get("company_names", []),
            evidence_json=json_dumps(evidence_package),
            references_markdown=references,
        ),
        temperature=0.2,
        max_output_tokens=5000,
    )

    return {"draft_report": response.output_text}
