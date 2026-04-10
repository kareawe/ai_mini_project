"""Report generation agent."""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Literal

from pydantic import BaseModel, Field

from prompts.report import (
    CONSISTENCY_SYSTEM_PROMPT,
    REPORT_SYSTEM_PROMPT,
    build_consistency_prompt,
    build_report_prompt,
)

from core.types import ConsistencySummary, SearchDocument, WorkflowState
from core.utils import get_client, json_dumps
from core.vector_store import retrieve_documents


class ConsistencyTechnologyAssessment(BaseModel):
    technology: str
    trl_range: str


class ConsistencyJudgment(BaseModel):
    overall_posture: Literal["aggressive_investment", "selective_investment", "monitor_and_wait"] = "selective_investment"
    priority_technologies: list[str] = Field(default_factory=list)
    technology_assessments: list[ConsistencyTechnologyAssessment] = Field(default_factory=list)


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
        "freshness_summary": state.get("freshness_summary", {}),
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


def _dominant_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    counter = Counter(values)
    return counter.most_common(1)[0][1] / len(values)


def _normalize_priorities(values: list[str], allowed_technologies: list[str]) -> tuple[str, ...]:
    allowed = {technology.lower(): technology for technology in allowed_technologies}
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        canonical = allowed.get(key)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return tuple(normalized[:3])


def _build_consistency_summary(
    state: WorkflowState,
    *,
    client,
    model: str,
    evidence_json: str,
    run_count: int,
) -> ConsistencySummary:
    judgments: list[ConsistencyJudgment] = []

    # The repeated structured pass measures decision stability from the same evidence,
    # without comparing long free-form reports line by line.
    for _ in range(run_count):
        response = client.responses.parse(
            model=model,
            instructions=CONSISTENCY_SYSTEM_PROMPT,
            input=build_consistency_prompt(
                our_company=state["our_company"],
                target_technologies=state["target_technologies"],
                company_names=state.get("company_names", []),
                evidence_json=evidence_json,
            ),
            text_format=ConsistencyJudgment,
            temperature=0.5,
            max_output_tokens=800,
        )
        judgments.append(response.output_parsed or ConsistencyJudgment())

    posture_ratio = _dominant_ratio([judgment.overall_posture for judgment in judgments])
    priority_ratio = _dominant_ratio(
        [
            "|".join(_normalize_priorities(judgment.priority_technologies, state["target_technologies"]))
            for judgment in judgments
        ]
    )

    technology_ratios: list[float] = []
    for technology in state["target_technologies"]:
        trl_values: list[str] = []
        for judgment in judgments:
            for assessment in judgment.technology_assessments:
                if assessment.technology.strip().lower() == technology.lower():
                    trl_values.append(assessment.trl_range.strip())
                    break
        technology_ratios.append(_dominant_ratio(trl_values))

    overall_consistency_ratio = mean(
        [posture_ratio, priority_ratio, *technology_ratios]
    ) if technology_ratios else mean([posture_ratio, priority_ratio])

    return {
        "run_count": run_count,
        "overall_consistency_ratio": overall_consistency_ratio,
        "warning_required": overall_consistency_ratio < 0.7,
    }


def run_report(
    state: WorkflowState,
    *,
    model: str,
    embedding_model: str,
) -> dict:
    client = get_client()
    evidence_package = _build_evidence_package(state, embedding_model=embedding_model)
    evidence_json = json_dumps(evidence_package)
    consistency_summary = _build_consistency_summary(
        state,
        client=client,
        model=model,
        evidence_json=evidence_json,
        run_count=state.get("consistency_runs", 5),
    )
    references = _build_references(state.get("search_documents", []))
    print(
        f"[report] technologies={len(state.get('target_technologies', []))} "
        f"companies={len(state.get('company_names', [])) + 1} "
        f"references={len(references.splitlines()) if references else 0} "
        f"consistency={consistency_summary['overall_consistency_ratio']:.0%}",
        flush=True,
    )

    response = client.responses.create(
        model=model,
        instructions=REPORT_SYSTEM_PROMPT,
        input=build_report_prompt(
            our_company=state["our_company"],
            target_technologies=state["target_technologies"],
            company_names=state.get("company_names", []),
            evidence_json=evidence_json,
            freshness_summary_json=json_dumps(state.get("freshness_summary", {})),
            references_markdown=references,
        ),
        temperature=0.2,
        max_output_tokens=5000,
    )

    return {
        "draft_report": response.output_text,
        "consistency_summary": consistency_summary,
    }
