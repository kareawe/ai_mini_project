import os
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Literal, Optional

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from agents.states import WebSearchAgentState, Document, Fact

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────

POSITIVE_SUFFIXES = [
    "advantage",
    "performance improvement",
    "mass production",
    "investment roadmap",
]

NEGATIVE_SUFFIXES = [
    "limitation",
    "challenge",
    "yield issue",
    "heat dissipation",
    "cost increase",
]

POSITIVE_KEYWORDS = {
    "advantage", "improvement", "breakthrough", "record", "launched",
    "investment", "roadmap", "production", "성능", "양산", "투자"
}
NEGATIVE_KEYWORDS = {
    "limitation", "challenge", "issue", "delay", "yield", "thermal",
    "cost", "problem", "failure", "recall", "수율", "발열", "지연", "문제"
}

SOURCE_TYPE_MAP = {
    "arxiv.org": "paper",
    "ieee.org": "paper",
    "sciencedirect.com": "paper",
    "patents.google.com": "patent",
    "samsung.com": "company_pr",
    "skhynix.com": "company_pr",
    "micron.com": "company_pr",
    "reuters.com": "news",
    "eetimes.com": "news",
    "anandtech.com": "news",
    "techinsights.com": "news",
}

RECENCY_WINDOW_DAYS = 180
MAX_PER_LABEL = 10

BiasLabel = Literal["positive", "negative", "neutral"]


# ─────────────────────────────────────────────
# 쿼리 생성
# ─────────────────────────────────────────────

def build_bias_controlled_queries(
    technologies: List[str],
    companies: List[str],
) -> Dict[str, Dict[str, List[str]]]:
    query_map: Dict[str, Dict[str, List[str]]] = {}

    for tech in technologies:
        pos = [f"{tech} {suf} 2024 2025" for suf in POSITIVE_SUFFIXES]
        neg = [f"{tech} {suf} 2024 2025" for suf in NEGATIVE_SUFFIXES]

        for company in companies:
            pos.append(f"{company} {tech} roadmap investment 2025")
            neg.append(f"{company} {tech} delay problem issue 2025")

        query_map[tech] = {
            "positive": pos,
            "negative": neg,
        }

    total_pos = sum(len(v["positive"]) for v in query_map.values())
    total_neg = sum(len(v["negative"]) for v in query_map.values())
    logger.info(f"[WebSearch] 긍정 쿼리 {total_pos}개 / 부정 쿼리 {total_neg}개 생성")

    return query_map


# ─────────────────────────────────────────────
# 검색 실행
# ─────────────────────────────────────────────

def execute_search(query: str) -> List[dict]:
    logger.debug(f"[WebSearch] 검색: '{query}'")
    try:
        from tavily import TavilyClient

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.error("[WebSearch] TAVILY_API_KEY 없음")
            return []

        client = TavilyClient(api_key=api_key)
        results = client.search(query, max_results=5)

        raw_items = results.get("results", [])
        logger.info(f"[WebSearch] RAW 결과 {len(raw_items)}개 - query='{query}'")

        parsed = []
        for r in raw_items:
            item = {
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "title": r.get("title", ""),
                "published_date": (
                    r.get("published_date")
                    or r.get("publishedDate")
                    or r.get("date")
                    or ""
                ),
            }
            parsed.append(item)

        if parsed:
            sample = parsed[0]
            logger.info(
                f"[WebSearch] 샘플 결과 - "
                f"url={sample['url']}, "
                f"date={sample['published_date']}, "
                f"content_len={len(sample['content'])}"
            )

        return parsed

    except ImportError:
        logger.error("[WebSearch] tavily-python 미설치 — pip install tavily-python")
        return []
    except Exception as e:
        logger.error(f"[WebSearch] 검색 실패 '{query}': {e}")
        return []


# ─────────────────────────────────────────────
# 출처 분류
# ─────────────────────────────────────────────

def classify_source_type(url: str) -> str:
    for domain, stype in SOURCE_TYPE_MAP.items():
        if domain in url:
            return stype

    if ".gov" in url or ".edu" in url:
        return "official"
    if "medium.com" in url or "substack.com" in url:
        return "blog"
    return "news"


# ─────────────────────────────────────────────
# 날짜 정규화
# ─────────────────────────────────────────────

def try_parse_relative_date(text: str, now: datetime) -> Optional[datetime]:
    if not text:
        return None

    s = text.strip().lower()

    if s == "today":
        return now
    if s == "yesterday":
        return now - timedelta(days=1)
    if s == "last week":
        return now - timedelta(days=7)
    if s == "last month":
        return now - relativedelta(months=1)

    m = re.search(r"(\d+)\s+(day|days|week|weeks|month|months|year|years)\s+ago", s)
    if not m:
        return None

    value = int(m.group(1))
    unit = m.group(2)

    if "day" in unit:
        return now - timedelta(days=value)
    if "week" in unit:
        return now - timedelta(weeks=value)
    if "month" in unit:
        return now - relativedelta(months=value)
    if "year" in unit:
        return now - relativedelta(years=value)

    return None


def llm_normalize_date(date_str: str, fallback_text: str = "") -> Optional[str]:
    if not date_str and not fallback_text:
        return None

    try:
        from openai import OpenAI
        client = OpenAI()

        prompt = f"""
You are a date normalization system.

Convert the following into YYYY-MM-DD.

Rules:
- If "April 2025" -> 2025-04-01
- If "3 days ago" -> calculate from today
- If unclear -> return NONE

Current date: {datetime.now().strftime("%Y-%m-%d")}

date_str: {date_str}
context: {fallback_text[:300]}

Output:
YYYY-MM-DD or NONE
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        result = response.choices[0].message.content.strip()

        if result == "NONE":
            return None

        return result

    except Exception as e:
        logger.error(f"[DateLLM] 실패: {e}")
        return None


def normalize_date_to_datetime(
    date_str: str,
    fallback_text: str = "",
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    now = now or datetime.now()

    candidates = []
    if date_str:
        candidates.append(date_str)
    if fallback_text:
        candidates.append(fallback_text)

    for c in candidates:
        try:
            dt = date_parser.parse(c, fuzzy=True)
            return dt
        except Exception:
            pass

    for c in candidates:
        dt = try_parse_relative_date(c, now)
        if dt:
            return dt

    if fallback_text:
        patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{4}/\d{2}/\d{2}\b",
            r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
            r"\b[A-Za-z]+\s+\d{4}\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, fallback_text)
            if m:
                try:
                    return date_parser.parse(m.group(0), fuzzy=True)
                except Exception:
                    pass

    normalized = llm_normalize_date(date_str, fallback_text)
    if normalized:
        try:
            return datetime.strptime(normalized, "%Y-%m-%d")
        except Exception:
            pass

    return None


def is_recent(
    date_str: str,
    fallback_text: str = "",
    recency_window_days: int = RECENCY_WINDOW_DAYS,
) -> bool:
    dt = normalize_date_to_datetime(date_str, fallback_text)
    if not dt:
        logger.debug(f"[WebSearch] 날짜 파싱 실패 - date='{date_str}'")
        return False

    is_ok = (datetime.now() - dt) <= timedelta(days=recency_window_days)
    logger.debug(
        f"[WebSearch] 날짜 판정 - raw='{date_str}', parsed='{dt.date()}', recent={is_ok}"
    )
    return is_ok


# ─────────────────────────────────────────────
# 라벨링
# ─────────────────────────────────────────────

def label_chunk(text: str) -> BiasLabel:
    text_lower = text.lower()
    pos_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
    neg_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

    if pos_hits == 0 and neg_hits == 0:
        return "neutral"
    if pos_hits >= neg_hits:
        return "positive"
    return "negative"


def parse_results_to_documents(
    raw_results: List[dict],
    technology: str,
) -> List[Document]:
    docs = []

    for r in raw_results:
        url = r.get("url", "")
        title = r.get("title", "")
        content = r.get("content", "")
        pub_date = r.get("published_date", "")
        source_type = classify_source_type(url)

        if not content.strip():
            logger.debug(f"[WebSearch] 빈 content 제외: {url}")
            continue

        combined_text = f"{title}\n{content}".strip()

        if not is_recent(pub_date, combined_text):
            logger.debug(f"[WebSearch] 최신성 미달 제외: {url}, date={pub_date}")
            continue

        label = label_chunk(combined_text)

        docs.append(Document(
            content=f"[{label.upper()}] {combined_text}",
            source=url,
            source_type=source_type,
            published_date=pub_date,
            technology=technology,
            relevance_score=0.8,
        ))

    logger.info(f"[WebSearch] 문서 변환 완료 - tech={technology}, docs={len(docs)}")
    return docs


# ─────────────────────────────────────────────
# 균형 컨텍스트
# ─────────────────────────────────────────────

def build_balanced_context(documents: List[Document]) -> List[Document]:
    buckets: Dict[str, List[Document]] = {"positive": [], "negative": [], "neutral": []}

    for doc in documents:
        if doc.content.startswith("[POSITIVE]"):
            buckets["positive"].append(doc)
        elif doc.content.startswith("[NEGATIVE]"):
            buckets["negative"].append(doc)
        else:
            buckets["neutral"].append(doc)

    balanced = (
        buckets["positive"][:MAX_PER_LABEL]
        + buckets["negative"][:MAX_PER_LABEL]
        + buckets["neutral"][: MAX_PER_LABEL // 2]
    )

    logger.info(
        f"[WebSearch] 균형 컨텍스트 구성 — "
        f"긍정 {len(buckets['positive'][:MAX_PER_LABEL])}개 / "
        f"부정 {len(buckets['negative'][:MAX_PER_LABEL])}개 / "
        f"중립 {len(buckets['neutral'][:MAX_PER_LABEL // 2])}개"
    )
    return balanced


# ─────────────────────────────────────────────
# 교차 검증
# ─────────────────────────────────────────────

def cross_validate_facts(documents: List[Document]) -> List[Fact]:
    tech_groups: Dict[str, List[Document]] = {}
    for doc in documents:
        tech_groups.setdefault(doc.technology or "unknown", []).append(doc)

    facts = []
    for tech, docs in tech_groups.items():
        if not docs:
            continue

        source_types = list({d.source_type for d in docs})
        sources = list({d.source for d in docs})

        if source_types == ["company_pr"]:
            confidence = 0.55
            logger.info(f"[WebSearch] {tech}: 기업 발표 단독 → 저신뢰 팩트로 유지")
        elif len(source_types) >= 2:
            confidence = 0.85
            logger.info(f"[WebSearch] {tech}: 이종 출처 {len(source_types)}개 → 고신뢰 팩트")
        else:
            confidence = 0.65
            logger.info(f"[WebSearch] {tech}: 이종 출처 부족 → 저신뢰 팩트로 유지")

        labels = {d.content.split("]")[0].lstrip("[") for d in docs}
        contradictions = []
        if "POSITIVE" in labels and "NEGATIVE" in labels:
            contradictions.append("긍정·부정 신호 상충 — 조건부 판단 필요")

        facts.append(Fact(
            claim=f"{tech} 관련 수집 정보",
            sources=sources,
            source_types=source_types,
            technology=tech,
            confidence=confidence,
            contradictions=contradictions,
        ))

    logger.info(f"[WebSearch] 교차 검증 완료 — {len(facts)}개 팩트 채택")
    return facts


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def run_web_search_agent(state: WebSearchAgentState) -> WebSearchAgentState:
    technologies = state.get("target_technologies", ["HBM4", "PIM", "CXL"])
    companies = state.get("company_candidates") or ["Samsung", "SK Hynix", "Micron"]

    logger.info(f"[Web Search Agent] 시작 — 기술: {technologies}, 기업: {companies}")

    query_map = build_bias_controlled_queries(technologies, companies)

    state["positive_queries"] = [
        q for tech in technologies for q in query_map[tech]["positive"]
    ]
    state["negative_queries"] = [
        q for tech in technologies for q in query_map[tech]["negative"]
    ]

    all_documents: List[Document] = []

    for tech in technologies:
        tech_queries = query_map[tech]["positive"][:4] + query_map[tech]["negative"][:4]

        logger.info(f"[WebSearch] 기술 '{tech}' 검색 시작 - 쿼리 {len(tech_queries)}개")

        for q in tech_queries:
            raw = execute_search(q)
            docs = parse_results_to_documents(raw, tech)
            all_documents.extend(docs)

    balanced_documents = build_balanced_context(all_documents)
    validated_facts = cross_validate_facts(all_documents)

    recency_ok = len(all_documents) >= 5

    state["retrieved_documents"] = balanced_documents
    state["validated_facts"] = validated_facts
    state["recency_check_passed"] = recency_ok

    logger.info(
        f"[Web Search Agent] 완료 — "
        f"전체 {len(all_documents)}개 → 균형 컨텍스트 {len(balanced_documents)}개, "
        f"팩트 {len(validated_facts)}개, 최신성 {'OK' if recency_ok else '미달'}"
    )

    return state