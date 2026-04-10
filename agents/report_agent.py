"""
Report Generation & Evaluation Agent
- 검증된 팩트 + 경쟁사 프로파일 기반 보고서 초안 생성 (GPT-4o-mini 실제 작성)
- 품질 자체 평가 (정확성 / 최신성 / 일관성 / 편향 통제 / 교차 검증)
- 기준 미달 시 Supervisor에게 재생성 요청 신호 반환
"""

import logging
from datetime import datetime
from typing import List
from openai import OpenAI
from agents.states import ReportAgentState, Fact, CompanyProfile, EvaluationResult

logger = logging.getLogger(__name__)

client = OpenAI()

# ─────────────────────────────────────────────
# 보고서 목차
# ─────────────────────────────────────────────

REPORT_OUTLINE = [
    "SUMMARY: 에이전트 종합 판정",
    "  - 기술 성숙도(TRL) 및 위협 수준 요약 차트",
    "1. 분석 배경 및 방법론",
    "  1.1 분석의 시급성: 차세대 반도체 표준 선점의 중요성",
    "  1.2 최신 데이터 확보: RAG 및 실시간 웹 검색 기반 데이터 추출 방식",
    "  1.3 기술 성숙도(TRL) 추정의 한계 및 접근 방식",
    "2. 분석 대상 기술 현황",
    "  2.1 HBM4: 적층 공정(Hybrid Bonding) 및 커스텀 메모리 아키텍처 현황",
    "  2.2 PIM/CXL: 지연 시간(Latency) 개선 및 메모리 풀링(Pooling) 기술 수준",
    "  2.3 기술적 난제: 열 관리(Heat Dissipation) 및 전력 효율성(PPW) 분석",
    "3. 경쟁사 동향 분석",
    "  3.1 경쟁사별 TRL 매핑: 삼성전자, SK하이닉스, 마이크론",
    "  3.2 전략 변화 추론: 최근 실적 발표 및 특허 출원 기반 기술 방향성 분석",
    "  3.3 파트너십 및 공급망 분석",
    "4. 전략적 시사점",
    "  4.1 R&D 우선순위 제언: 즉시 투입이 필요한 핵심 IP 및 공정 기술",
    "  4.2 위협 수준별 대응 시나리오: 경쟁사 양산 시점에 따른 시장 방어 전략",
    "  4.3 협력 생태계 구축: Design House 및 EDA 툴 업체와의 협업 방향",
    "REFERENCE: 보고서 작성 시 활용한 자료 목록",
]


# ─────────────────────────────────────────────
# 헬퍼: 입력 컨텍스트 직렬화
# ─────────────────────────────────────────────

def _serialize_facts(facts: List[Fact]) -> str:
    if not facts:
        return "수집된 팩트 없음"
    lines = []
    for i, f in enumerate(facts, 1):
        lines.append(
            f"[팩트 {i}] 기술={f.technology} | 신뢰도={f.confidence:.2f}\n"
            f"  내용: {f.claim}\n"
            f"  출처: {', '.join(f.sources)}\n"
            f"  출처유형: {', '.join(f.source_types)}"
        )
    return "\n\n".join(lines)


def _serialize_profiles(profiles: List[CompanyProfile]) -> str:
    if not profiles:
        return "수집된 경쟁사 프로파일 없음"
    lines = []
    for p in profiles:
        signals = "\n    ".join(p.key_signals) if p.key_signals else "없음"
        partnerships = ", ".join(p.partnerships) if p.partnerships else "없음"
        lines.append(
            f"[{p.name}] 역할={p.role} | TRL={p.trl_scores} | 위협수준={p.threat_level}\n"
            f"  핵심신호:\n    {signals}\n"
            f"  파트너십: {partnerships}"
        )
    return "\n\n".join(lines)


def _format_trl_table(profiles: List[CompanyProfile]) -> str:
    lines = [
        "| 기업 | HBM4 TRL | PIM TRL | CXL TRL | 위협 수준 |",
        "|------|----------|---------|---------|-----------|",
    ]
    for p in profiles:
        if p.role == "competitor":
            hbm = p.trl_scores.get("HBM4", "-")
            pim = p.trl_scores.get("PIM", "-")
            cxl = p.trl_scores.get("CXL", "-")
            lines.append(f"| {p.name} | {hbm} | {pim} | {cxl} | {p.threat_level.upper()} |")
    return "\n".join(lines)


def _format_references(facts: List[Fact]) -> str:
    refs = []
    seen = set()
    for fact in facts:
        for src in fact.sources:
            if src not in seen:
                src_type = fact.source_types[0] if fact.source_types else "unknown"
                refs.append(f"- [{src_type}] {src}")
                seen.add(src)
    return "\n".join(refs) if refs else "- 참고 자료 없음"


# ─────────────────────────────────────────────
# LLM 호출: 섹션별 실제 내용 생성
# ─────────────────────────────────────────────

def _llm_write_section(section_title: str, instructions: str, context: str) -> str:
    """GPT-4o-mini로 보고서 섹션 하나를 실제 작성"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 반도체 기술 전략 분석 전문가입니다. "
                        "주어진 팩트와 경쟁사 프로파일 데이터를 기반으로 "
                        "보고서 섹션을 한국어로 작성하세요. "
                        "마크다운 형식을 사용하고, 데이터에 근거한 구체적인 분석을 제공하세요. "
                        "추측은 '추정' 또는 '간접 지표 기반'임을 명시하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"## 작성할 섹션: {section_title}\n\n"
                        f"## 작성 지침:\n{instructions}\n\n"
                        f"## 활용할 데이터:\n{context}\n\n"
                        f"위 데이터를 반드시 활용하여 섹션 내용을 작성하세요."
                    ),
                },
            ],
            max_tokens=1500,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[Report Agent] LLM 섹션 생성 실패 ({section_title}): {e}")
        return f"_{section_title} 내용 생성 실패: {e}_"


# ─────────────────────────────────────────────
# 보고서 초안 생성 (LLM 기반)
# ─────────────────────────────────────────────

def generate_draft_report(
    technologies: List[str],
    facts: List[Fact],
    profiles: List[CompanyProfile],
) -> str:
    now = datetime.now().strftime("%Y년 %m월 %d일")
    facts_ctx = _serialize_facts(facts)
    profiles_ctx = _serialize_profiles(profiles)
    trl_table = _format_trl_table(profiles)
    ref_text = _format_references(facts)
    tech_str = ", ".join(technologies)

    logger.info("[Report Agent] LLM 섹션별 보고서 작성 시작")

    # ── SUMMARY ──────────────────────────────────────────────────
    summary = _llm_write_section(
        "SUMMARY: 에이전트 종합 판정",
        (
            "보고서 전체 핵심 내용을 1/2 페이지 이내로 요약하세요.\n"
            "- 분석 대상 기술의 현재 경쟁 구도를 한 문단으로 요약\n"
            "- 가장 위협적인 경쟁사와 그 근거를 명시\n"
            "- 즉각적인 R&D 대응이 필요한 핵심 포인트 2~3개 제시"
        ),
        f"분석 기술: {tech_str}\n\n{profiles_ctx}",
    )

    # ── 1. 분석 배경 ─────────────────────────────────────────────
    section1 = _llm_write_section(
        "1. 분석 배경 및 방법론",
        (
            "아래 3개 소섹션을 모두 작성하세요.\n"
            "### 1.1 분석의 시급성\n"
            "- 왜 지금 이 기술을 분석해야 하는지 시장/산업 맥락으로 설명\n"
            "### 1.2 데이터 확보 방식\n"
            "- RAG, 실시간 웹 검색, 편향 통제, 교차 검증 방법 설명\n"
            "### 1.3 TRL 추정의 한계\n"
            "- TRL 4~6 구간은 영업 비밀 영역임을 명시\n"
            "- 간접 지표(특허, 학회 발표, 채용 공고) 기반 추정임을 명시"
        ),
        f"분석 기술: {tech_str}\n\n팩트 데이터:\n{facts_ctx}",
    )

    # ── 2. 기술 현황 ─────────────────────────────────────────────
    section2 = _llm_write_section(
        "2. 분석 대상 기술 현황",
        (
            "아래 3개 소섹션을 모두 작성하세요.\n"
            "### 2.1 HBM4\n"
            "- 수집된 팩트 데이터를 직접 인용하여 현재 기술 수준 서술\n"
            "### 2.2 PIM/CXL\n"
            "- 수집된 팩트 데이터를 직접 인용하여 현재 기술 수준 서술\n"
            "### 2.3 기술적 난제\n"
            "- 열 관리, 전력 효율, 제조 비용, 수율 관점에서 마크다운 표로 정리"
        ),
        f"팩트 데이터:\n{facts_ctx}",
    )

    # ── 3. 경쟁사 동향 ───────────────────────────────────────────
    section3 = _llm_write_section(
        "3. 경쟁사 동향 분석",
        (
            "아래 3개 소섹션을 모두 작성하세요.\n"
            "### 3.1 경쟁사별 TRL 매핑\n"
            "- 각 경쟁사의 TRL 수치와 위협 수준을 근거와 함께 서술\n"
            "- TRL 4~6 구간 추정 시 간접 지표 명시\n"
            "### 3.2 전략 변화 추론\n"
            "- 핵심 신호(key_signals) 데이터를 근거로 각 경쟁사의 전략 방향 분석\n"
            "- 상충 정보가 있으면 조건부 판단으로 서술\n"
            "### 3.3 파트너십 및 공급망\n"
            "- 각 경쟁사의 파트너십 현황과 공급망 전략 분석"
        ),
        f"경쟁사 프로파일:\n{profiles_ctx}",
    )

    # ── 4. 전략적 시사점 ─────────────────────────────────────────
    section4 = _llm_write_section(
        "4. 전략적 시사점",
        (
            "아래 3개 소섹션을 모두 작성하세요.\n"
            "### 4.1 R&D 우선순위 제언\n"
            "- 경쟁사 분석 결과를 바탕으로 즉시 투자해야 할 기술 영역 3~5개 제시\n"
            "- 각 항목에 근거(어떤 경쟁사의 어떤 움직임 때문인지) 명시\n"
            "### 4.2 위협 수준별 대응 시나리오\n"
            "- 고/중/저 위협 시나리오별 구체적 대응 전략을 마크다운 표로 작성\n"
            "### 4.3 협력 생태계 구축\n"
            "- EDA 툴, Design House, 고객사 관점에서 협력 방향 제시"
        ),
        f"경쟁사 프로파일:\n{profiles_ctx}\n\n팩트 데이터:\n{facts_ctx}",
    )

    logger.info("[Report Agent] 모든 섹션 생성 완료 — 보고서 조립 중")

    # ── 전체 보고서 조립 ─────────────────────────────────────────
    report = f"""# 반도체 핵심 기술 경쟁사 기술 전략 분석 보고서
**생성일**: {now}
**분석 대상 기술**: {tech_str}
**데이터 신뢰 수준**: RAG + 실시간 웹 검색 교차 검증 기반

---


{summary}

### 기술 성숙도(TRL) 및 위협 수준 요약

{trl_table}

> TRL 추정은 공개 정보 기반이며, 실제 내부 개발 수준과 차이가 있을 수 있습니다.

---


{section1}

---


{section2}

---


{section3}

---


{section4}

---

## REFERENCE

{ref_text}

---
*본 보고서는 AI 에이전트 시스템(RAG + 웹 검색 + GPT-4o-mini)에 의해 자동 생성되었습니다.*
*모든 수치/판단은 공개 정보 기반이며, 투자 또는 사업 결정 전 추가 검증이 필요합니다.*
"""
    return report.strip()


# ─────────────────────────────────────────────
# 보고서 품질 평가
# ─────────────────────────────────────────────

def evaluate_report_quality(
    draft: str,
    facts: List[Fact],
    profiles: List[CompanyProfile],
) -> EvaluationResult:

    # ── 정확성: confidence 가중 평균 + 출처 다양성·신호 품질 보정 ──
    if facts:
        base_accuracy = sum(f.confidence for f in facts) / len(facts)
        sourced = sum(1 for f in facts if len(set(f.source_types)) >= 2)
        diversity_bonus = (sourced / len(facts)) * 0.2
        avg_signals = sum(len(p.key_signals) for p in profiles) / max(len(profiles), 1)
        signal_bonus = min(avg_signals / 10, 0.1)
        accuracy = min(base_accuracy + diversity_bonus + signal_bonus, 1.0)
    else:
        accuracy = 0.5

    # ── 최신성: 목차 섹션 완성도 ─────────────────────────────────
    sections_present = sum(1 for item in REPORT_OUTLINE if any(
        keyword in draft for keyword in item.split(":")[-1].split()[:3]
    ))
    recency = min(sections_present / max(len(REPORT_OUTLINE), 1), 1.0)

    # ── 일관성: 보고서 길이/구조 안정성 ──────────────────────────
    consistency = 0.85 if len(draft) > 1000 else 0.6

    # ── 편향 통제: 긍정/부정 신호 균형 ──────────────────────────
    has_positive = any("[+]" in s for p in profiles for s in p.key_signals)
    has_negative = any("[-]" in s for p in profiles for s in p.key_signals)
    bias_check = has_positive and has_negative

    # ── 교차 검증: 이종 출처 2개 이상 팩트 존재 ─────────────────
    cross_val = any(len(set(f.source_types)) >= 2 for f in facts) if facts else False

    # ── 최종 통과 기준 ────────────────────────────────────────────
    overall = (
        accuracy >= 0.60 and
        recency >= 0.75 and
        consistency >= 0.80 and
        bias_check and
        cross_val
    )

    feedback_parts = []
    if accuracy < 0.60:
        feedback_parts.append(f"정확성 미달 ({accuracy:.2f} < 0.60): 팩트 출처 보완 필요")
    if recency < 0.75:
        feedback_parts.append(f"최신성 미달 ({recency:.2f} < 0.75): 최신 데이터 재수집 필요")
    if consistency < 0.80:
        feedback_parts.append("일관성 미달: 보고서 길이/구조 불안정")
    if not bias_check:
        feedback_parts.append("편향 통제 미달: 긍정 또는 부정 신호 누락")
    if not cross_val:
        feedback_parts.append("교차 검증 미달: 이종 출처 2개 이상 필요")

    result = EvaluationResult(
        accuracy_score=accuracy,
        recency_score=recency,
        consistency_score=consistency,
        bias_check_passed=bias_check,
        cross_validation_passed=cross_val,
        overall_passed=overall,
        feedback=" | ".join(feedback_parts) if feedback_parts else "모든 기준 통과",
    )

    logger.info(
        f"[Report Agent] 평가 결과: "
        f"정확성={accuracy:.2f}, 최신성={recency:.2f}, "
        f"일관성={consistency:.2f}, 편향통제={bias_check}, "
        f"교차검증={cross_val}, 통과={overall}"
    )
    return result


# ─────────────────────────────────────────────
# Report Agent 메인 노드 함수
# ─────────────────────────────────────────────

def run_report_agent(state: ReportAgentState) -> ReportAgentState:
    """Report Agent 실행 엔트리포인트"""
    technologies = state.get("target_technologies", ["HBM4", "PIM", "CXL"])
    facts = state.get("validated_facts", [])
    profiles = state.get("company_profiles", [])

    logger.info(f"[Report Agent] 보고서 초안 생성 시작 — 팩트 {len(facts)}개, 프로파일 {len(profiles)}개")

    state["report_outline"] = REPORT_OUTLINE

    draft = generate_draft_report(technologies, facts, profiles)
    state["draft_report"] = draft

    evaluation = evaluate_report_quality(draft, facts, profiles)
    state["evaluation_result"] = evaluation

    logger.info(f"[Report Agent] 완료 — 통과: {evaluation.overall_passed}")
    return state