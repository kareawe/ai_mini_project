from __future__ import annotations

from pathlib import Path

from agents.config import AppConfig
from agents.llm_client import LLMClient
from agents.models import AgentRunResult, DraftResult, RunContext
from agents.utils import dump_json, write_text
from prompts.system_prompts import DRAFT_SYSTEM_PROMPT, DRAFT_REVIEW_SYSTEM_PROMPT


class DraftGenerationAgent:
    def __init__(self, config: AppConfig, context: RunContext) -> None:
        self.config = config
        self.context = context
        self.llm = LLMClient(config)

    def _validate_markdown(self, markdown_text: str) -> tuple[bool, list[str]]:
        warnings = []
        required_sections = [
            "SUMMARY",
            "1. 분석 배경 및 방법론",
            "2. 분석 대상 기술 현황",
            "3. 경쟁사 동향 분석",
            "4. 전략적 시사점",
            "REFERENCE",
        ]
        for section in required_sections:
            if section not in markdown_text:
                warnings.append(f"필수 섹션 누락: {section}")

        if "TRL 4~6" not in markdown_text and "TRL 4-6" not in markdown_text:
            warnings.append("TRL 4~6 추정 한계가 명시되지 않았습니다.")
        if "추정" not in markdown_text:
            warnings.append("보고서에서 추정 표현이 부족합니다.")
        return len(warnings) == 0, warnings

    def run(
        self,
        rag_result: AgentRunResult,
        web_result: AgentRunResult,
        competitor_result: AgentRunResult,
    ) -> DraftResult:
        markdown_report = ""
        warnings: list[str] = []

        for attempt in range(self.config.max_retry_draft + 1):
            prompt_input = {
                "user_query": self.context.user_query,
                "target_technologies": self.context.target_technologies,
                "our_company": self.context.our_company,
                "rag_facts": [fact.model_dump() for fact in rag_result.validated_facts],
                "web_facts": [fact.model_dump() for fact in web_result.validated_facts],
                "company_profiles": [profile.model_dump() for profile in competitor_result.company_profiles],
                "notes": {
                    "must_state_limits": True,
                    "must_treat_trl_4_6_as_estimate": True,
                    "must_separate_fact_and_inference": True,
                },
            }

            draft = self.llm.chat(
                system_prompt=DRAFT_SYSTEM_PROMPT,
                user_prompt=str(prompt_input),
                temperature=0.2,
            )

            review = self.llm.chat_json(
                system_prompt=DRAFT_REVIEW_SYSTEM_PROMPT,
                user_prompt=f"""
다음 markdown 초안을 검토하라.

반드시 JSON 형식으로만 응답하라.
다른 설명 문장, 코드블록, 머리말 없이 JSON 객체만 반환하라.

반환 형식:
{{
  "revised_markdown": "수정된 전체 마크다운 문자열"
}}

검토 기준:
1. 필수 섹션 존재 여부 점검
2. TRL 4~6은 추정임을 명시
3. 사실과 추정 구분
4. 경쟁사 비교와 전략적 시사점 연결
5. 참고 근거 언급 보완
6. markdown 형식 유지

검토할 초안:
{draft}
""",
            )

            markdown_report = review.get("revised_markdown", draft)
            passed, warnings = self._validate_markdown(markdown_report)

            if passed:
                output = DraftResult(
                    status="success",
                    retry_count=attempt,
                    validation_passed=True,
                    warnings=[],
                    markdown_report=markdown_report,
                )
                write_text(
                    Path(self.context.outputs_dir) / "drafts" / f"draft_report_{self.context.run_id}.md",
                    markdown_report,
                )
                dump_json(
                    Path(self.context.outputs_dir) / "drafts" / f"draft_meta_{self.context.run_id}.json",
                    output.model_dump(),
                )
                return output

        output = DraftResult(
            status="partial" if markdown_report else "failed",
            retry_count=self.config.max_retry_draft,
            validation_passed=False,
            warnings=warnings,
            markdown_report=markdown_report,
        )
        write_text(
            Path(self.context.outputs_dir) / "drafts" / f"draft_report_{self.context.run_id}.md",
            markdown_report,
        )
        dump_json(
            Path(self.context.outputs_dir) / "drafts" / f"draft_meta_{self.context.run_id}.json",
            output.model_dump(),
        )
        return output