from __future__ import annotations

from pathlib import Path
from typing import Any, List

import requests

from agents.config import AppConfig
from agents.llm_client import LLMClient
from agents.models import AgentRunResult, EvidenceItem, RunContext, ValidatedFact
from agents.utils import dedupe_preserve_order, dump_json, log_step
from prompts.system_prompts import WEB_FACT_EXTRACTION_SYSTEM_PROMPT


class WebSearchAgent:
    def __init__(self, config: AppConfig, context: RunContext) -> None:
        self.config = config
        self.context = context
        self.llm = LLMClient(config)

    def _tavily_search(self, query: str) -> dict[str, Any]:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.config.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": True,
            "max_results": 8,
            "topic": "news",
        }
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _openalex_search(self, query: str) -> list[dict[str, Any]]:
        url = "https://api.openalex.org/works"
        params = {
            "search": query,
            "per-page": 5,
            "sort": "relevance_score:desc",
        }
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def _build_queries(self, attempt: int) -> list[str]:
        techs = self.context.target_technologies

        base_patterns = [
            "{tech} technology overview",
            "{tech} limitation challenge issue",
        ]

        if attempt > 0:
            base_patterns.extend(
                [
                    "{tech} bottleneck problem",
                    "{tech} thermal power issue",
                    "{tech} industry adoption challenge",
                ]
            )

        queries: list[str] = []
        for tech in techs:
            for pattern in base_patterns:
                queries.append(pattern.format(tech=tech))

        return queries

    def _convert_web_results(self, tavily_data: dict[str, Any]) -> List[EvidenceItem]:
        items: List[EvidenceItem] = []
        for row in tavily_data.get("results", []):
            items.append(
                EvidenceItem(
                    title=row.get("title", ""),
                    url=row.get("url", ""),
                    source_type="news",
                    published_date=row.get("published_date"),
                    snippet=row.get("content", "")[:400],
                    content=(row.get("raw_content") or row.get("content") or "")[:5000],
                    metadata={"score": row.get("score", 0)},
                )
            )
        return items

    def _convert_openalex_results(self, rows: list[dict[str, Any]]) -> List[EvidenceItem]:
        items: List[EvidenceItem] = []
        for row in rows:
            abstract = ""
            if row.get("abstract_inverted_index"):
                abstract = " ".join(row["abstract_inverted_index"].keys())

            authorships = row.get("authorships", [])
            institutions = []
            for auth in authorships:
                for inst in auth.get("institutions", []):
                    name = inst.get("display_name")
                    if name:
                        institutions.append(name)

            items.append(
                EvidenceItem(
                    title=row.get("display_name", ""),
                    url=row.get("primary_location", {}).get("landing_page_url") or "",
                    source_type="paper",
                    published_date=str(row.get("publication_year", "")),
                    snippet=abstract[:400],
                    content=abstract[:3000],
                    metadata={"institutions": dedupe_preserve_order(institutions)},
                )
            )
        return items

    def _validate(self, facts: List[ValidatedFact]) -> tuple[bool, list[str]]:
        warnings: list[str] = []

        if len(facts) < 4:
            warnings.append("웹 근거 fact 수가 부족합니다.")

        source_types = set()
        positive_count = 0
        negative_count = 0

        for fact in facts:
            for src in fact.source_types:
                source_types.add(src)
            if fact.threat_signal and "high" in fact.threat_signal.lower():
                negative_count += 1
            else:
                positive_count += 1

        if len(source_types) < 2:
            warnings.append("출처 유형 다양성이 부족합니다.")
        if positive_count == 0 or negative_count == 0:
            warnings.append("긍정/부정 신호 균형이 부족합니다.")

        return len(warnings) == 0, warnings

    def run(self) -> AgentRunResult:
        log_step("WebSearchAgent", "Web Search Agent 시작")

        all_raw_items: List[EvidenceItem] = []
        validated_facts: List[ValidatedFact] = []
        warnings: List[str] = []

        for attempt in range(self.config.max_retry_web + 1):
            log_step("WebSearchAgent", f"시도 {attempt + 1}/{self.config.max_retry_web + 1}")

            queries = self._build_queries(attempt)
            log_step("WebSearchAgent", f"생성된 query 수: {len(queries)}")

            raw_items: List[EvidenceItem] = []

            for idx, query in enumerate(queries, start=1):
                log_step("WebSearchAgent", f"[{idx}/{len(queries)}] Tavily 검색 시작 | {query}")
                tavily_data = self._tavily_search(query)
                tavily_items = self._convert_web_results(tavily_data)
                log_step("WebSearchAgent", f"[{idx}/{len(queries)}] Tavily 결과 수: {len(tavily_items)}")
                raw_items.extend(tavily_items)

                log_step("WebSearchAgent", f"[{idx}/{len(queries)}] OpenAlex 검색 시작 | {query}")
                openalex_rows = self._openalex_search(query)
                openalex_items = self._convert_openalex_results(openalex_rows)
                log_step("WebSearchAgent", f"[{idx}/{len(queries)}] OpenAlex 결과 수: {len(openalex_items)}")
                raw_items.extend(openalex_items)

            log_step("WebSearchAgent", f"중복 제거 전 raw item 수: {len(raw_items)}")

            deduped = {}
            for item in raw_items:
                key = f"{item.title}|{item.url}|{item.source_type}"
                if key not in deduped:
                    deduped[key] = item

            all_raw_items = list(deduped.values())
            log_step("WebSearchAgent", f"중복 제거 후 raw item 수: {len(all_raw_items)}")

            prompt_input = {
                "user_query": self.context.user_query,
                "target_technologies": self.context.target_technologies,
                "relationship_labels": [
                    "research_collab",
                    "business_partnership",
                    "supply_chain",
                    "candidate_only",
                ],
                "evidences": [
                    {
                        "evidence_id": f"web_{idx}",
                        "title": item.title,
                        "url": item.url,
                        "source_type": item.source_type,
                        "published_date": item.published_date,
                        "content": item.content[:2500],
                    }
                    for idx, item in enumerate(all_raw_items, start=1)
                ],
            }

            log_step("WebSearchAgent", "LLM fact 추출 요청 시작")
            result_json = self.llm.chat_json(
                system_prompt=WEB_FACT_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=str(prompt_input),
            )
            log_step("WebSearchAgent", "LLM fact 추출 완료")

            validated_facts = []
            for fact in result_json.get("facts", []):
                validated_facts.append(
                    ValidatedFact(
                        claim=fact.get("claim", ""),
                        technology=fact.get("technology", "UNKNOWN"),
                        company=fact.get("company"),
                        trl_signal=fact.get("trl_signal"),
                        threat_signal=fact.get("threat_signal"),
                        confidence=float(fact.get("confidence", 0.5)),
                        evidence_ids=fact.get("evidence_ids", []),
                        evidence_summary=fact.get("evidence_summary", ""),
                        source_types=fact.get("source_types", []),
                        caveat=fact.get("caveat", ""),
                    )
                )

            log_step("WebSearchAgent", f"검증 대상 fact 수: {len(validated_facts)}")
            passed, warnings = self._validate(validated_facts)

            if passed:
                log_step("WebSearchAgent", "검증 통과")
                output = AgentRunResult(
                    agent_name="WebSearchAgent",
                    status="success",
                    retry_count=attempt,
                    validation_passed=True,
                    warnings=[],
                    raw_items=all_raw_items,
                    validated_facts=validated_facts,
                    extra={"queries": queries},
                )
                dump_json(
                    Path(self.context.outputs_dir) / "validated" / f"web_result_{self.context.run_id}.json",
                    output.model_dump(),
                )
                log_step(
                    "WebSearchAgent",
                    f"종료 | status={output.status} | retry={output.retry_count} | facts={len(output.validated_facts)}",
                )
                return output

            log_step("WebSearchAgent", f"검증 실패, warnings={warnings}")

        status = "partial" if validated_facts else "failed"
        output = AgentRunResult(
            agent_name="WebSearchAgent",
            status=status,
            retry_count=self.config.max_retry_web,
            validation_passed=False,
            warnings=warnings,
            raw_items=all_raw_items,
            validated_facts=validated_facts,
        )
        dump_json(
            Path(self.context.outputs_dir) / "validated" / f"web_result_{self.context.run_id}.json",
            output.model_dump(),
        )
        log_step(
            "WebSearchAgent",
            f"최종 종료 | status={output.status} | retry={output.retry_count} | facts={len(output.validated_facts)}",
        )
        return output