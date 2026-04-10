"""
Supervisor Agent
- 전체 워크플로우 조율
- 각 Agent 호출 순서 결정 및 품질 기준 미달 시 재시도 제어
- Control Strategy 구현
"""

import json
import logging
from typing import Any, Dict

from agents.states import (
    SupervisorState, EvaluationResult,
    Document, Fact, CompanyProfile
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 품질 임계값 (Control Strategy 기준)
# ─────────────────────────────────────────────
THRESHOLDS = {
    "accuracy":    0.60,
    "recency":     0.75,
    "consistency": 0.80,
}
DEFAULT_MAX_RETRY = 1


# ─────────────────────────────────────────────
# Supervisor Node 함수들 (LangGraph 호환)
# ─────────────────────────────────────────────

def initialize_state(state: SupervisorState) -> SupervisorState:
    """사용자 쿼리를 분석하여 초기 상태 설정"""
    logger.info("[Supervisor] 초기화 — 분석 대상 기술 파싱")
    state.setdefault("target_technologies", ["HBM4", "PIM", "CXL"])
    state.setdefault("scope", {
        "period": "최근 12개월",
        "regions": ["global"],
        "company_tiers": ["tier1_memory", "tier1_logic", "partner"],
    })
    state.setdefault("retry_count", {
        "rag": 0, "web_search": 0, "competitor": 0, "report": 0
    })
    state["max_retry"] = DEFAULT_MAX_RETRY
    state["status"] = "running"
    state["next_action"] = "rag"
    return state


def route_next_action(state: SupervisorState) -> str:
    """
    현재 상태를 보고 다음 노드를 결정하는 라우터.
    LangGraph conditional_edges 에서 사용.
    """
    action = state.get("next_action", "end")
    status = state.get("status", "running")

    if status == "failed":
        logger.warning("[Supervisor] 상태 failed → END")
        return "end"

    logger.info(f"[Supervisor] 다음 액션: {action}")
    return action


def evaluate_rag_results(state: SupervisorState) -> SupervisorState:
    """RAG 결과 품질 평가 및 재시도 여부 결정"""
    docs: list = state.get("retrieved_documents", [])
    retry = state.get("retry_count", {})
    max_retry = state.get("max_retry", DEFAULT_MAX_RETRY)

    quality_ok = len(docs) >= 3  # 간단 기준: 최소 3개 문서

    if not quality_ok and retry.get("rag", 0) < max_retry:
        logger.info("[Supervisor] RAG 품질 미달 → 재시도")
        retry["rag"] = retry.get("rag", 0) + 1
        state["retry_count"] = retry
        state["status"] = "retry"
        state["next_action"] = "rag"
    else:
        logger.info("[Supervisor] RAG 완료 → 웹 검색")
        state["status"] = "running"
        state["next_action"] = "web_search"

    return state


def evaluate_web_search_results(state: SupervisorState) -> SupervisorState:
    """웹 검색 결과 최신성 평가 및 재시도 여부 결정"""
    facts: list = state.get("validated_facts", [])
    retry = state.get("retry_count", {})
    max_retry = state.get("max_retry", DEFAULT_MAX_RETRY)

    recency_ok = len(facts) >= 5

    if not recency_ok and retry.get("web_search", 0) < max_retry:
        logger.info("[Supervisor] 웹 검색 최신성 미달 → 재시도")
        retry["web_search"] = retry.get("web_search", 0) + 1
        state["retry_count"] = retry
        state["status"] = "retry"
        state["next_action"] = "web_search"
    else:
        logger.info("[Supervisor] 웹 검색 완료 → 경쟁사 분석")
        state["status"] = "running"
        state["next_action"] = "competitor"
    return state


def evaluate_competitor_results(state: SupervisorState) -> SupervisorState:
    """경쟁사 프로파일 완성도 평가"""
    profiles: list = state.get("company_profiles", [])
    retry = state.get("retry_count", {})
    max_retry = state.get("max_retry", DEFAULT_MAX_RETRY)

    ok = len(profiles) >= 2

    if not ok and retry.get("competitor", 0) < max_retry:
        logger.info("[Supervisor] 경쟁사 프로파일 부족 → 재시도")
        retry["competitor"] = retry.get("competitor", 0) + 1
        state["retry_count"] = retry
        state["status"] = "retry"
        state["next_action"] = "competitor"
    else:
        logger.info("[Supervisor] 경쟁사 분석 완료 → 보고서 작성")
        state["status"] = "running"
        state["next_action"] = "report"
    return state


def evaluate_report(state: SupervisorState) -> SupervisorState:
    """
    보고서 품질 평가 (Control Strategy 핵심).
    기준 미달 시 동일 근거로 LLM 재호출 지시.
    """
    ev: EvaluationResult = state.get("evaluation_result")
    retry = state.get("retry_count", {})
    max_retry = state.get("max_retry", DEFAULT_MAX_RETRY)

    if ev is None:
        logger.warning("[Supervisor] 평가 결과 없음 → 보고서 재생성")
        state["next_action"] = "report"
        return state

    passed = (
        ev.accuracy_score    >= THRESHOLDS["accuracy"]    and
        ev.recency_score     >= THRESHOLDS["recency"]     and
        ev.consistency_score >= THRESHOLDS["consistency"] and
        ev.bias_check_passed and
        ev.cross_validation_passed
    )

    if not passed and retry.get("report", 0) < max_retry:
        logger.info(f"[Supervisor] 보고서 품질 미달 → 재생성 (피드백: {ev.feedback})")
        retry["report"] = retry.get("report", 0) + 1
        state["retry_count"] = retry
        state["status"] = "retry"
        state["next_action"] = "report"
    elif not passed:
        logger.error("[Supervisor] 최대 재시도 초과 → 실패 처리")
        state["status"] = "failed"
        state["next_action"] = "end"
    else:
        logger.info("[Supervisor] 보고서 품질 OK → 포맷팅")
        state["status"] = "running"
        state["next_action"] = "formatting"

    return state


def finalize(state: SupervisorState) -> SupervisorState:
    """포맷팅 완료 후 최종 확인"""
    logger.info("[Supervisor] 최종 보고서 생성 완료 → END")
    state["status"] = "done"
    state["next_action"] = "end"
    return state