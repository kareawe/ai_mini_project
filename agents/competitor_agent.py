from __future__ import annotations

from pathlib import Path
from typing import List

from agents.config import AppConfig
from agents.llm_client import LLMClient
from agents.models import AgentRunResult, CompanyProfile, RunContext
from agents.utils import dump_json
from prompts.system_prompts import COMPETITOR_EXTRACTION_SYSTEM_PROMPT


class CompetitorListupAgent:
    def __init__(self, config: AppConfig, context: RunContext) -> None:
        self.config = config
        self.context = context
        self.llm = LLMClient(config)

    def _validate(self, profiles: List[CompanyProfile]) -> tuple[bool, list[str]]:
        warnings = []
        if len(profiles) < 5:
            warnings.append("경쟁사/협력사 프로필 수가 부족합니다.")
        competitor_names = {p.company_name for p in profiles if p.role == "competitor"}
        must_have = {"Samsung Electronics", "SK hynix", "Micron"}
        if not must_have.intersection(competitor_names):
            warnings.append("핵심 경쟁사 커버리지가 부족합니다.")
        return len(warnings) == 0, warnings

    def run(self, rag_result: AgentRunResult, web_result: AgentRunResult) -> AgentRunResult:
        warnings: list[str] = []
        profiles: List[CompanyProfile] = []

        for attempt in range(self.config.max_retry_competitor + 1):
            prompt_input = {
                "user_query": self.context.user_query,
                "target_technologies": self.context.target_technologies,
                "allowed_relationship_labels": [
                    "research_collab",
                    "business_partnership",
                    "supply_chain",
                    "candidate_only",
                ],
                "seed_competitors": ["Samsung Electronics", "SK hynix", "Micron"],
                "rag_facts": [fact.model_dump() for fact in rag_result.validated_facts],
                "web_facts": [fact.model_dump() for fact in web_result.validated_facts],
                "web_evidences": [item.model_dump() for item in web_result.raw_items[:40]],
            }

            result_json = self.llm.chat_json(
                system_prompt=COMPETITOR_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=str(prompt_input),
            )

            profiles = [
                CompanyProfile(
                    company_name=row.get("company_name", ""),
                    role=row.get("role", "unknown"),
                    technologies=row.get("technologies", []),
                    relationship_type=row.get("relationship_type", "candidate_only"),
                    summary=row.get("summary", ""),
                    supporting_evidence=row.get("supporting_evidence", []),
                    confidence=float(row.get("confidence", 0.5)),
                    notes=row.get("notes", ""),
                )
                for row in result_json.get("profiles", [])
            ]

            passed, warnings = self._validate(profiles)
            if passed:
                output = AgentRunResult(
                    agent_name="CompetitorListupAgent",
                    status="success",
                    retry_count=attempt,
                    validation_passed=True,
                    warnings=[],
                    company_profiles=profiles,
                )
                dump_json(
                    Path(self.context.outputs_dir) / "validated" / f"competitor_result_{self.context.run_id}.json",
                    output.model_dump(),
                )
                return output

        status = "partial" if profiles else "failed"
        output = AgentRunResult(
            agent_name="CompetitorListupAgent",
            status=status,
            retry_count=self.config.max_retry_competitor,
            validation_passed=False,
            warnings=warnings,
            company_profiles=profiles,
        )
        dump_json(
            Path(self.context.outputs_dir) / "validated" / f"competitor_result_{self.context.run_id}.json",
            output.model_dump(),
        )
        return output