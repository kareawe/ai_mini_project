"""
Competitor List-up & Profiling Agent
- 수집된 문서/팩트 기반으로 경쟁사/협력사 식별
- 기술별 TRL(기술 성숙도) 추정
- 위협 수준 평가 (high / medium / low)
- 긍정·부정 신호 균형 반영
"""

import logging
from typing import List, Dict
from agents.states import CompetitorAgentState, CompanyProfile, Document, Fact

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 사전 정의 기업 분류
# ─────────────────────────────────────────────

KNOWN_COMPANIES = {
    "competitor": ["Samsung Electronics", "SK Hynix", "Micron Technology"],
    "partner":    ["TSMC", "NVIDIA", "AMD", "Intel", "Broadcom"],
    "customer":   ["Apple", "Google", "Microsoft", "Meta"],
}

# TRL 기준 힌트 키워드
TRL_KEYWORDS = {
    9: ["mass production", "양산", "high volume", "shipped"],
    8: ["qualification", "customer sample", "validation"],
    7: ["prototype", "demo", "pilot"],
    6: ["system prototype", "system demo"],
    5: ["technology validated", "lab validation"],
    4: ["technology demonstrated"],
    3: ["proof of concept", "experimental"],
}


# ─────────────────────────────────────────────
# 기업 식별
# ─────────────────────────────────────────────

def identify_companies(
    documents: List[Document],
    facts: List[Fact],
) -> List[str]:
    """문서에서 언급된 기업 식별 및 전체 후보 리스트 반환"""
    mentioned = set()
    all_texts = [d.content for d in documents] + [f.claim for f in facts]

    for text in all_texts:
        for role_group in KNOWN_COMPANIES.values():
            for company in role_group:
                if company.lower() in text.lower():
                    mentioned.add(company)

    # 최소한 tier1 메모리 3사는 포함
    for c in KNOWN_COMPANIES["competitor"]:
        mentioned.add(c)

    logger.info(f"[Competitor] 식별된 기업: {sorted(mentioned)}")
    return sorted(mentioned)


# ─────────────────────────────────────────────
# TRL 추정
# ─────────────────────────────────────────────

def estimate_trl(company: str, technology: str, documents: List[Document]) -> int:
    """
    키워드 기반 TRL 추정.
    실제 환경: LLM에게 문서 청크를 넘겨 TRL 점수 추론 요청.
    """
    relevant_texts = [
        d.content for d in documents
        if (d.company == company or company.lower() in d.content.lower())
        and (d.technology == technology or technology.lower() in d.content.lower())
    ]

    combined = " ".join(relevant_texts).lower()
    for trl, keywords in TRL_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return trl

    return 5  # 정보 불충분 시 기본값


# ─────────────────────────────────────────────
# 위협 수준 평가
# ─────────────────────────────────────────────

def assess_threat_level(trl_scores: Dict[str, int], role: str) -> str:
    """평균 TRL + 역할 기반 위협 수준 결정"""
    if role != "competitor":
        return "low"

    avg_trl = sum(trl_scores.values()) / max(len(trl_scores), 1)
    if avg_trl >= 8:
        return "high"
    elif avg_trl >= 6:
        return "medium"
    return "low"


# ─────────────────────────────────────────────
# 신호 추출 (긍정·부정 균형)
# ─────────────────────────────────────────────

def extract_signals(
    company: str,
    documents: List[Document],
    facts: List[Fact],
) -> List[str]:
    """
    설계 문서 편향 통제:
    긍정 신호(성능 향상, 양산 계획, 투자 확대)와
    부정 신호(기술적 한계, 수율, 발열, 비용)를 동시 수집.
    """
    signals = []
    relevant_docs = [
        d for d in documents
        if company.lower() in d.content.lower()
    ]

    positive_keywords = ["performance", "launched", "investment", "roadmap", "record"]
    negative_keywords = ["delay", "yield", "thermal", "cost", "challenge", "issue", "recall"]

    for doc in relevant_docs[:10]:
        content_lower = doc.content.lower()
        for kw in positive_keywords:
            if kw in content_lower:
                signals.append(f"[+] {kw} 관련 신호 — {doc.source}")
                break
        for kw in negative_keywords:
            if kw in content_lower:
                signals.append(f"[-] {kw} 관련 신호 — {doc.source}")
                break

    # 팩트의 상충 정보도 반영
    for fact in facts:
        if fact.company == company and fact.contradictions:
            for c in fact.contradictions:
                signals.append(f"[!] 상충: {c}")

    return signals[:10]  # 최대 10개


# ─────────────────────────────────────────────
# 파트너십 추출
# ─────────────────────────────────────────────

def extract_partnerships(company: str, documents: List[Document]) -> List[str]:
    partners = []
    for doc in documents:
        if company.lower() in doc.content.lower():
            for partner_list in KNOWN_COMPANIES.values():
                for p in partner_list:
                    if p != company and p.lower() in doc.content.lower():
                        partners.append(p)
    return list(set(partners))


# ─────────────────────────────────────────────
# Competitor Agent 메인 노드 함수
# ─────────────────────────────────────────────

def run_competitor_agent(state: CompetitorAgentState) -> CompetitorAgentState:
    """Competitor Agent 실행 엔트리포인트"""
    technologies = state.get("target_technologies", ["HBM4", "PIM", "CXL"])
    documents = state.get("retrieved_documents", [])
    facts = state.get("validated_facts", [])

    logger.info(f"[Competitor Agent] 시작 — 기술: {technologies}")

    # 1. 기업 식별
    companies = identify_companies(documents, facts)
    state["company_candidates"] = companies

    # 2. 프로파일 생성
    profiles: List[CompanyProfile] = []
    for company in companies:
        role = "competitor"
        for r, group in KNOWN_COMPANIES.items():
            if company in group:
                role = r
                break

        trl_scores = {
            tech: estimate_trl(company, tech, documents)
            for tech in technologies
        }
        threat_level = assess_threat_level(trl_scores, role)
        key_signals = extract_signals(company, documents, facts)
        partnerships = extract_partnerships(company, documents)

        profiles.append(CompanyProfile(
            name=company,
            role=role,
            technologies=technologies,
            trl_scores=trl_scores,
            threat_level=threat_level,
            key_signals=key_signals,
            recent_moves=[],       # 실제 환경: LLM 추론
            partnerships=partnerships,
        ))
        logger.info(
            f"[Competitor Agent] {company}: TRL={trl_scores}, "
            f"위협={threat_level}, 신호={len(key_signals)}개"
        )

    state["company_profiles"] = profiles
    logger.info(f"[Competitor Agent] 완료 — {len(profiles)}개 프로파일 생성")
    return state