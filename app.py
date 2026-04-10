from __future__ import annotations

import json
import os
from pathlib import Path

from agents.config import AppConfig
from agents.models import RunContext, SupervisorState
from agents.rag_agent import RAGAgent
from agents.web_search_agent import WebSearchAgent
from agents.competitor_agent import CompetitorListupAgent
from agents.draft_agent import DraftGenerationAgent
from agents.formatting_node import FormattingNode
from agents.utils import ensure_dirs, dump_json, now_kst_str


def main() -> None:
    config = AppConfig.from_env()

    root_dir = Path(__file__).resolve().parent
    data_dir = root_dir / "data"
    outputs_dir = root_dir / "outputs"

    ensure_dirs(
        outputs_dir / "raw",
        outputs_dir / "validated",
        outputs_dir / "drafts",
        outputs_dir / "final",
        outputs_dir / "logs",
    )

    user_query = (
        "HBM4, PIM, CXL 관련 최신 반도체 R&D 동향을 수집하고, "
        "삼성전자, SK하이닉스, 마이크론 중심으로 기술 성숙도(TRL)와 위협 수준을 분석한 뒤 "
        "R&D 담당자가 바로 참고할 수 있는 기술 전략 분석 보고서를 작성하라. "
        "협력사 후보와 관계 유형도 함께 정리하라."
    )

    target_technologies = ["HBM4", "PIM", "CXL"]

    context = RunContext(
        root_dir=str(root_dir),
        data_dir=str(data_dir),
        outputs_dir=str(outputs_dir),
        user_query=user_query,
        target_technologies=target_technologies,
        our_company="SK hynix", 
        run_id=now_kst_str().replace(":", "").replace("-", "").replace(" ", "_"),
    )

    supervisor_state = SupervisorState(
        user_query=user_query,
        target_technologies=target_technologies,
        status="running",
    )

    print("[1/5] RAG Agent 실행")
    rag_agent = RAGAgent(config=config, context=context)
    rag_result = rag_agent.run()
    supervisor_state.rag_result = rag_result

    print("[2/5] Web Search Agent 실행")
    web_agent = WebSearchAgent(config=config, context=context)
    web_result = web_agent.run()
    supervisor_state.web_result = web_result

    print("[3/5] Competitor List-up Agent 실행")
    competitor_agent = CompetitorListupAgent(config=config, context=context)
    competitor_result = competitor_agent.run(
        rag_result=rag_result,
        web_result=web_result,
    )
    supervisor_state.competitor_result = competitor_result

    print("[4/5] Draft Generation Agent 실행")
    draft_agent = DraftGenerationAgent(config=config, context=context)
    draft_result = draft_agent.run(
        rag_result=rag_result,
        web_result=web_result,
        competitor_result=competitor_result,
    )
    supervisor_state.draft_result = draft_result

    print("[5/5] Formatting Node 실행")
    formatting_node = FormattingNode(context=context)
    final_result = formatting_node.run(
        markdown_text=draft_result.markdown_report,
        run_id=context.run_id,
    )
    supervisor_state.final_result = final_result
    supervisor_state.status = "done"

    dump_json(
        outputs_dir / "final" / f"supervisor_state_{context.run_id}.json",
        supervisor_state.model_dump(),
    )

    print()
    print("실행 완료")
    print(f"- Markdown: {final_result.markdown_path}")
    print(f"- HTML: {final_result.html_path}")
    print(f"- PDF: {final_result.pdf_path}")


if __name__ == "__main__":
    main()