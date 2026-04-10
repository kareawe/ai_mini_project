"""
반도체 기술 전략 분석 시스템 — LangGraph 메인 그래프 (LangSmith 추적 포함)

설계 원칙
- 실행 순서는 순차적이다.
  START -> Supervisor -> RAG -> Supervisor -> Web Search -> Supervisor
  -> Competitor -> Supervisor -> Report -> Supervisor -> Formatting -> Supervisor -> END
- 단, 각 단계 종료 후 Supervisor가 상태를 평가하여
  다음 단계로 갈지, 같은 단계를 재시도할지, 종료할지를 결정한다.
"""

import logging
import os
from typing import Any, Dict

from langgraph.graph import StateGraph, START, END

from agents.states import SupervisorState
from agents.supervisor import (
    initialize_state,
    route_next_action,
    evaluate_rag_results,
    evaluate_web_search_results,
    evaluate_competitor_results,
    evaluate_report,
    finalize,
)
from agents.rag_agent import run_rag_agent
from agents.web_search_agent import run_web_search_agent
from agents.competitor_agent import run_competitor_agent
from agents.report_agent import run_report_agent
from agents.formatting_node import run_formatting_node

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# LangSmith 추적 설정
# ─────────────────────────────────────────────

def setup_langsmith():
    """LangSmith 트레이싱 활성화"""
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    if not api_key:
        logger.warning("[LangSmith] LANGCHAIN_API_KEY 미설정 — 추적 비활성화")
        return False

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_PROJECT", "semiconductor-strategy-analysis")

    try:
        from langsmith import Client
        Client(api_key=api_key)
        logger.info(
            f"[LangSmith] 추적 활성화 — 프로젝트: {os.environ['LANGCHAIN_PROJECT']}"
        )
        return True
    except ImportError:
        logger.warning("[LangSmith] langsmith 패키지 미설치 — pip install langsmith")
        return False
    except Exception as e:
        logger.warning(f"[LangSmith] 연결 실패: {e}")
        return False


# ─────────────────────────────────────────────
# LangSmith 추적 데코레이터
# ─────────────────────────────────────────────

def traced(name: str, run_type: str = "chain"):
    """LangSmith 추적 데코레이터 — 미설치 시 그냥 실행"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                from langsmith import traceable
                return traceable(name=name, run_type=run_type)(func)(*args, **kwargs)
            except ImportError:
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ─────────────────────────────────────────────
# Supervisor Node
# ─────────────────────────────────────────────

@traced("Supervisor", run_type="chain")
def supervisor_node(state: SupervisorState) -> SupervisorState:
    logger.info(f"[Supervisor DEBUG] incoming state keys = {list(state.keys())}")
    logger.info(
        f"[Supervisor DEBUG] incoming next_action = {state.get('next_action')}, "
        f"status = {state.get('status')}, "
        f"retry_count = {state.get('retry_count')}"
    )

    # 최초 진입일 때만 초기화
    if state.get("next_action") is None:
        logger.info("[Supervisor] 초기 진입 — 상태 초기화")
        state = initialize_state(state)
    else:
        logger.info(
            f"[Supervisor] 복귀 — status={state.get('status')}, "
            f"next_action={state.get('next_action')}, "
            f"retry_count={state.get('retry_count')}"
        )

    return state

# ─────────────────────────────────────────────
# Agent 실행 + 평가 결합 노드
# ─────────────────────────────────────────────

@traced("RAG Agent", run_type="retriever")
def rag_node(state: SupervisorState) -> SupervisorState:
    logger.info("─── Step 1: RAG Agent ───")

    sub_state: Dict[str, Any] = {
        "user_query": state.get("user_query", ""),
        "target_technologies": state.get("target_technologies", []),
        "retrieved_documents": state.get("retrieved_documents", []),
        "retry_count": state.get("retry_count", {}),
    }

    result = run_rag_agent(sub_state)
    state["retrieved_documents"] = result.get("retrieved_documents", [])

    # Supervisor 평가 로직 활용
    state = evaluate_rag_results(state)
    return state


@traced("Web Search Agent", run_type="tool")
def web_search_node(state: SupervisorState) -> SupervisorState:
    logger.info("─── Step 2: Web Search Agent ───")

    sub_state: Dict[str, Any] = {
        "user_query": state.get("user_query", ""),
        "target_technologies": state.get("target_technologies", []),
        "scope": state.get("scope", {}),
        "company_candidates": state.get("company_candidates", []),
        "retrieved_documents": state.get("retrieved_documents", []),
        "retry_count": state.get("retry_count", {}),
    }

    result = run_web_search_agent(sub_state)
    state["retrieved_documents"] = result.get("retrieved_documents", [])
    state["validated_facts"] = result.get("validated_facts", [])

    state = evaluate_web_search_results(state)
    return state


@traced("Competitor Agent", run_type="chain")
def competitor_node(state: SupervisorState) -> SupervisorState:
    logger.info("─── Step 3: Competitor Agent ───")

    sub_state: Dict[str, Any] = {
        "target_technologies": state.get("target_technologies", []),
        "retrieved_documents": state.get("retrieved_documents", []),
        "validated_facts": state.get("validated_facts", []),
        "company_candidates": state.get("company_candidates", []),
        "retry_count": state.get("retry_count", {}),
    }

    result = run_competitor_agent(sub_state)
    state["company_candidates"] = result.get("company_candidates", [])
    state["company_profiles"] = result.get("company_profiles", [])

    state = evaluate_competitor_results(state)
    return state


@traced("Report Agent", run_type="llm")
def report_node(state: SupervisorState) -> SupervisorState:
    logger.info("─── Step 4: Report Agent ───")

    sub_state: Dict[str, Any] = {
        "target_technologies": state.get("target_technologies", []),
        "validated_facts": state.get("validated_facts", []),
        "company_profiles": state.get("company_profiles", []),
        "retry_count": state.get("retry_count", {}),
    }

    result = run_report_agent(sub_state)
    state["draft_report"] = result.get("draft_report", "")
    state["evaluation_result"] = result.get("evaluation_result")

    state = evaluate_report(state)
    return state


@traced("Formatting Node", run_type="chain")
def formatting_node(state: SupervisorState) -> SupervisorState:
    logger.info("─── Step 5: Formatting Node ───")

    sub_state: Dict[str, Any] = {
        "draft_report": state.get("draft_report", ""),
    }

    result = run_formatting_node(sub_state)
    state["output_path"] = result.get("output_path", "")

    state = finalize(state)
    return state


# ─────────────────────────────────────────────
# LangGraph 그래프 빌드
# ─────────────────────────────────────────────

def build_graph():
    """
    순차 실행 + Supervisor 라우팅 구조
    """
    setup_langsmith()
    logger.info("[Graph] LangGraph 그래프 구성 중...")

    graph = StateGraph(SupervisorState)

    # Nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("rag", rag_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("competitor", competitor_node)
    graph.add_node("report", report_node)
    graph.add_node("formatting", formatting_node)

    # 시작점
    graph.add_edge(START, "supervisor")

    # Supervisor가 next_action을 기준으로 다음 순차 단계를 라우팅
    graph.add_conditional_edges(
        "supervisor",
        route_next_action,
        {
            "rag": "rag",
            "web_search": "web_search",
            "competitor": "competitor",
            "report": "report",
            "formatting": "formatting",
            "end": END,
        },
    )

    # 각 단계 종료 후 반드시 Supervisor로 복귀
    graph.add_edge("rag", "supervisor")
    graph.add_edge("web_search", "supervisor")
    graph.add_edge("competitor", "supervisor")
    graph.add_edge("report", "supervisor")
    graph.add_edge("formatting", "supervisor")

    compiled = graph.compile()
    logger.info("[Graph] LangGraph 그래프 구성 완료")
    return compiled


# ─────────────────────────────────────────────
# 실행 예시용 헬퍼
# ─────────────────────────────────────────────

def run_workflow(initial_state: Dict[str, Any]) -> SupervisorState:
    """
    외부에서 쉽게 호출할 수 있는 실행 헬퍼
    """
    graph = build_graph()
    logger.info("[Workflow] 실행 시작")
    result = graph.invoke(initial_state)
    logger.info(
        f"[Workflow] 실행 완료 — status={result.get('status')}, "
        f"next_action={result.get('next_action')}, "
        f"output_path={result.get('output_path')}"
    )
    return result