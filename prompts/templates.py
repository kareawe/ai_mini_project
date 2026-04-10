"""
프롬프트 템플릿 모음
- 각 Agent의 LLM 호출 시 사용하는 시스템/유저 프롬프트
- 편향 통제 및 교차 검증 요구사항 명시
"""

from typing import List, Dict, Any


# ─────────────────────────────────────────────
# Supervisor 프롬프트
# ─────────────────────────────────────────────

SUPERVISOR_SYSTEM = """당신은 반도체 기술 전략 분석 시스템의 Supervisor입니다.
다음 원칙을 항상 준수하세요:
1. 분석 대상 기술(HBM4, PIM, CXL)에 대해 객관적이고 균형 잡힌 판단을 내립니다.
2. 단일 출처나 기업 홍보 자료만으로는 결론을 내리지 않습니다.
3. 불확실한 정보는 "조건부 판단" 또는 "가능성 범위"로 표현합니다.
4. 각 에이전트의 결과물이 품질 기준을 충족하는지 엄격히 검토합니다.
"""

SUPERVISOR_ROUTE_PROMPT = """현재 워크플로우 상태를 분석하고 다음 액션을 결정하세요.

현재 상태:
- 수집된 문서 수: {doc_count}
- 검증된 팩트 수: {fact_count}
- 경쟁사 프로파일 수: {profile_count}
- 보고서 초안 존재: {has_draft}
- 보고서 평가 결과: {eval_result}
- 현재 재시도 횟수: {retry_count}

다음 중 하나를 반환하세요: rag / web_search / competitor / report / formatting / end
"""


# ─────────────────────────────────────────────
# RAG Agent 프롬프트
# ─────────────────────────────────────────────

RAG_QUERY_TEMPLATE = """다음 기술에 대한 핵심 정보를 내부 문서에서 검색합니다.

검색 기술: {technology}
사용자 질의: {user_query}

검색 초점:
- 기술 정의 및 핵심 아키텍처 원리
- 성능 지표 및 벤치마크 데이터
- 기술적 제약사항 (수율, 발열, 전력)
- 최신 연구 동향 및 개발 방향

출처 유형 우선순위: 논문 > 특허 > 기술 보고서 > 뉴스
"""

RAG_QUALITY_CHECK_PROMPT = """검색된 문서들이 다음 기준을 충족하는지 평가하세요.

문서 목록:
{document_summaries}

평가 기준:
1. 분석 대상 기술({technologies})과 직접적 관련성
2. 수치/성능 데이터 포함 여부
3. 출처의 신뢰성 (논문/특허 여부)
4. 정보의 구체성

JSON 형식으로 반환: {{"quality_score": 0.0~1.0, "issues": ["..."], "recommendation": "..."}}
"""


# ─────────────────────────────────────────────
# Web Search Agent 프롬프트
# ─────────────────────────────────────────────

WEB_SEARCH_POSITIVE_TEMPLATE = """{technology} {company} {suffix} 2024 2025"""
WEB_SEARCH_NEGATIVE_TEMPLATE = """{technology} {company} {suffix} 2024 2025"""

BIAS_CONTROL_INSTRUCTION = """
편향 통제 지시사항:
- 긍정 신호(성능 향상, 양산 계획, 투자 확대)와 부정 신호(기술 한계, 수율, 발열, 비용)를 동시 수집
- 기업 홍보 자료 단독으로는 유효 근거 불채택
- 동일 주장에 대해 최소 2개 이상 이종 출처(논문/특허/뉴스/기업발표) 확인
- 상충 정보는 단정하지 말고 "가능성 범위" 또는 "조건부 판단"으로 기술
"""

WEB_SEARCH_FACT_EXTRACTION_PROMPT = """다음 웹 검색 결과에서 팩트를 추출하세요.

검색 결과:
{search_results}

대상 기술: {technology}
대상 기업: {company}

추출 규칙:
1. 수치가 포함된 구체적 사실만 추출
2. 출처 URL과 게시일을 반드시 기록
3. 상충되는 정보가 있으면 별도 항목으로 기록
4. 기업 홍보 자료 단독 주장은 confidence를 0.5 이하로 설정

{bias_control_instruction}

JSON 형식으로 반환:
{{
  "facts": [
    {{
      "claim": "...",
      "source": "URL",
      "source_type": "paper|patent|news|company_pr",
      "published_date": "YYYY-MM-DD",
      "confidence": 0.0~1.0,
      "is_positive_signal": true/false,
      "contradictions": ["..."]
    }}
  ]
}}
"""


# ─────────────────────────────────────────────
# Competitor Agent 프롬프트
# ─────────────────────────────────────────────

COMPETITOR_TRL_ESTIMATION_PROMPT = """다음 정보를 바탕으로 {company}의 {technology} 기술 성숙도(TRL)를 추정하세요.

수집된 정보:
{evidence}

TRL 기준:
- TRL 9: 실제 양산 (Mass Production)
- TRL 8: 고객 샘플 검증 완료
- TRL 7: 시스템 프로토타입 검증
- TRL 6: 관련 환경에서 시스템 실증
- TRL 5: 관련 환경에서 기술 검증
- TRL 4: 실험실 기술 실증
- TRL 3: 개념 증명

판단 시 주의사항:
- 양산 수율(Yield) 정보가 없으면 TRL을 과대평가하지 않음
- 발열/전력 문제가 보고된 경우 TRL을 보수적으로 추정
- 기업 발표만 있고 외부 검증 없으면 TRL을 1단계 낮춰서 판단

JSON 반환: {{"trl": 1~9, "confidence": 0.0~1.0, "rationale": "...", "limiting_factors": ["..."]}}
"""

COMPETITOR_THREAT_ASSESSMENT_PROMPT = """다음 경쟁사 프로파일을 바탕으로 위협 수준을 평가하세요.

기업: {company}
TRL 점수: {trl_scores}
주요 신호: {signals}
파트너십: {partnerships}

위협 수준 기준:
- HIGH: TRL 8+ AND 주요 고객사 공급 계약 확인 AND 투자 확대 신호
- MEDIUM: TRL 6~7 OR 기술 검증 완료 OR 파트너십 강화 신호
- LOW: TRL 5 이하 OR 개발 지연 또는 기술적 한계 보고

JSON 반환: {{"threat_level": "high|medium|low", "rationale": "...", "key_risks": ["..."]}}
"""


# ─────────────────────────────────────────────
# Report Agent 프롬프트
# ─────────────────────────────────────────────

REPORT_GENERATION_SYSTEM = """당신은 반도체 R&D 전략 분석 전문가입니다.
다음 원칙으로 보고서를 작성하세요:

1. **팩트 기반**: 모든 주장에 출처를 명시합니다.
2. **균형 잡힌 관점**: 기술의 강점과 한계를 동시에 기술합니다.
3. **조건부 판단**: 불확실한 정보는 "~로 추정됨", "~가능성이 있음"으로 표현합니다.
4. **R&D 실용성**: R&D 담당자가 즉시 활용할 수 있는 인사이트 중심으로 작성합니다.
5. **TRL 보수적 추정**: 공개 정보만으로는 과대평가 위험이 있으므로 보수적으로 판단합니다.
"""

REPORT_SECTION_PROMPT = """다음 섹션을 작성하세요: {section_title}

사용 가능한 팩트:
{relevant_facts}

관련 경쟁사 정보:
{relevant_profiles}

작성 지침:
- 분량: {target_length}자 이내
- 수치 데이터는 반드시 출처와 함께 기술
- 상충 정보가 있으면 양쪽 모두 기술 후 조건부 판단 제시
- 전문 용어는 괄호 안에 영문 병기
"""

REPORT_EVALUATION_PROMPT = """다음 보고서 초안의 품질을 평가하세요.

보고서:
{draft_report}

검증에 사용된 팩트 수: {fact_count}
교차 검증된 팩트 비율: {cross_validated_ratio}

평가 기준:
1. 정확성 (0.0~1.0): 출처 기반 사실 오류 없음
2. 최신성 (0.0~1.0): 최근 12개월 내 정보 반영
3. 일관성 (0.0~1.0): 논리적 흐름의 일관성
4. 편향 통제: 긍정/부정 신호 균형 여부 (true/false)
5. 교차 검증: 이종 출처 2개 이상 확인 여부 (true/false)

JSON 반환:
{{
  "accuracy_score": 0.0~1.0,
  "recency_score": 0.0~1.0,
  "consistency_score": 0.0~1.0,
  "bias_check_passed": true/false,
  "cross_validation_passed": true/false,
  "overall_passed": true/false,
  "feedback": "구체적인 개선 사항"
}}
"""


# ─────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────

def build_web_search_queries(
    technologies: List[str],
    companies: List[str],
    positive_suffixes: List[str] = None,
    negative_suffixes: List[str] = None,
) -> Dict[str, List[str]]:
    """긍정/부정 편향 통제 쿼리 딕셔너리 반환"""
    if positive_suffixes is None:
        positive_suffixes = ["advantage", "performance", "roadmap", "investment 2025"]
    if negative_suffixes is None:
        negative_suffixes = ["limitation", "yield issue", "thermal problem", "delay 2025"]

    queries = {"positive": [], "negative": []}
    for tech in technologies:
        for suf in positive_suffixes:
            queries["positive"].append(f"{tech} {suf}")
        for suf in negative_suffixes:
            queries["negative"].append(f"{tech} {suf}")
        for company in companies:
            queries["positive"].append(f"{company} {tech} roadmap 2025")
            queries["negative"].append(f"{company} {tech} challenge issue 2025")

    return queries


def format_facts_for_prompt(facts: List[Any]) -> str:
    """팩트 목록을 프롬프트용 텍스트로 변환"""
    if not facts:
        return "수집된 팩트 없음"
    lines = []
    for i, f in enumerate(facts, 1):
        lines.append(
            f"{i}. [{f.technology}] {f.claim}\n"
            f"   출처: {', '.join(f.sources[:2])}\n"
            f"   신뢰도: {f.confidence:.2f} | 출처유형: {', '.join(set(f.source_types))}"
        )
    return "\n\n".join(lines)


def format_profiles_for_prompt(profiles: List[Any]) -> str:
    """경쟁사 프로파일을 프롬프트용 텍스트로 변환"""
    if not profiles:
        return "경쟁사 프로파일 없음"
    lines = []
    for p in profiles:
        if p.role == "competitor":
            lines.append(
                f"■ {p.name}\n"
                f"  TRL: {p.trl_scores}\n"
                f"  위협: {p.threat_level.upper()}\n"
                f"  신호: {' / '.join(p.key_signals[:3])}"
            )
    return "\n\n".join(lines)