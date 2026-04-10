"""
반도체 기술 전략 분석 시스템 - Agent State 정의
설계 문서 기반: SupervisorState, RAGAgentState, WebSearchAgentState,
CompetitorAgentState, ReportAgentState, FormattingState
"""

from typing import TypedDict, List, Dict, Any, Literal, Optional
from dataclasses import dataclass, field


# ─────────────────────────────────────────────
# 공통 데이터 모델
# ─────────────────────────────────────────────

@dataclass
class Document:
    """수집된 문서/정보 단위"""
    content: str
    source: str                         # URL, 파일명, 논문명 등
    source_type: str                    # "paper" | "company_pr" | "news" | "patent"
    published_date: Optional[str] = None
    technology: Optional[str] = None    # "HBM4" | "PIM" | "CXL"
    company: Optional[str] = None
    relevance_score: float = 0.0


@dataclass
class Fact:
    """검증된 사실 단위"""
    claim: str
    sources: List[str]                  # 교차 검증된 출처 목록 (최소 2개 권장)
    source_types: List[str]             # 출처 유형 다양성 확인용
    technology: str
    company: Optional[str] = None
    confidence: float = 0.0             # 0.0 ~ 1.0
    contradictions: List[str] = field(default_factory=list)  # 상충 정보


@dataclass
class CompanyProfile:
    """경쟁사/협력사 프로파일"""
    name: str
    role: str                           # "competitor" | "partner" | "customer"
    technologies: List[str]
    trl_scores: Dict[str, int]          # {"HBM4": 7, "PIM": 5, "CXL": 6}
    threat_level: str                   # "high" | "medium" | "low"
    key_signals: List[str]              # 긍정/부정 신호 혼합
    recent_moves: List[str]             # 최신 동향
    partnerships: List[str]


@dataclass
class EvaluationResult:
    """보고서 품질 평가 결과"""
    accuracy_score: float               # 0.0 ~ 1.0 (팩트 오류 없음 기준)
    recency_score: float                # 0.0 ~ 1.0 (최신 정보 반영 기준)
    consistency_score: float            # 0.0 ~ 1.0 (동일 근거 → 일관된 결론)
    bias_check_passed: bool             # 긍정/부정 신호 균형 여부
    cross_validation_passed: bool       # 2개 이상 이종 출처 교차검증 여부
    overall_passed: bool
    feedback: str                       # 미달 시 구체적 피드백


# ─────────────────────────────────────────────
# Agent States
# ─────────────────────────────────────────────

class SupervisorState(TypedDict, total=False):
    """전체 워크플로우를 조율하는 Supervisor 상태"""
    user_query: str
    target_technologies: List[str]      # ["HBM4", "PIM", "CXL"]
    scope: Dict[str, Any]               # 분석 범위 (기간, 지역, 기업군 등)

    retrieved_documents: List[Document]
    validated_facts: List[Fact]

    company_candidates: List[str]
    company_profiles: List[CompanyProfile]

    draft_report: str
    evaluation_result: EvaluationResult

    next_action: Literal[
        "rag",
        "web_search",
        "competitor",
        "report",
        "formatting",
        "end"
    ]
    retry_count: Dict[str, int]         # {"rag": 0, "web_search": 1, ...}
    max_retry: int                      # 기본값:1, 상황에 따라 조정
    status: Literal["running", "retry", "done", "failed"]


class RAGAgentState(TypedDict, total=False):
    """내부 문서 RAG 검색 Agent 상태"""
    user_query: str
    target_technologies: List[str]
    retrieved_documents: List[Document]
    retrieval_quality_score: float
    retry_count: Dict[str, int]


class WebSearchAgentState(TypedDict, total=False):
    """실시간 웹 검색 Agent 상태 (편향 통제 포함)"""
    user_query: str
    target_technologies: List[str]
    scope: Dict[str, Any]

    company_candidates: List[str]

    # 편향 통제: 긍정/부정 쿼리 병렬 수집
    positive_queries: List[str]         # "advantage / performance / investment"
    negative_queries: List[str]         # "limitation / challenge / issue / yield"

    retrieved_documents: List[Document]
    validated_facts: List[Fact]

    recency_check_passed: bool          # 최신성 기준 통과 여부
    retry_count: Dict[str, int]


class CompetitorAgentState(TypedDict, total=False):
    """경쟁사/협력사 리스트업 및 프로파일링 Agent 상태"""
    target_technologies: List[str]

    retrieved_documents: List[Document]
    validated_facts: List[Fact]

    company_candidates: List[str]
    company_profiles: List[CompanyProfile]

    retry_count: Dict[str, int]


class ReportAgentState(TypedDict, total=False):
    """보고서 초안 생성 및 자체 평가 Agent 상태"""
    target_technologies: List[str]
    validated_facts: List[Fact]
    company_profiles: List[CompanyProfile]

    report_outline: List[str]
    draft_report: str
    evaluation_result: EvaluationResult

    retry_count: Dict[str, int]


class FormattingState(TypedDict, total=False):
    """최종 보고서 포맷팅 (PDF 생성) Node 상태"""
    draft_report: str
    final_report: str
    output_path: str
    status: Literal["running", "done"]