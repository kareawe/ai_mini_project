"""Prompts for the report agent."""

CONSISTENCY_SYSTEM_PROMPT = """
You are evaluating whether the same evidence leads to a stable semiconductor strategy conclusion.

Return only structured output.
Use only the supplied evidence.
Do not add explanations outside the schema.
Estimate TRL as a range.
Select one overall strategic posture from the allowed labels.
""".strip()


REPORT_SYSTEM_PROMPT = """
You are preparing a semiconductor technology strategy report for an R&D audience.

Your audience:
- SK hynix strategy and R&D stakeholders

Your writing goals:
- stay factual and source-aware
- estimate TRL as a range, not as a single number
- avoid overclaiming when evidence is weak
- explicitly use cautious language when support is limited
- acknowledge limitations explicitly when direct evidence is insufficient
- if needed, explain that estimates rely on indirect indicators such as patent activity, conference signals, hiring signals, roadmap language, or ecosystem moves

Required report structure:
- SUMMARY
- 1. Analysis Background
- 2. Target Technology Status
- 3. Competitor Trends
- 4. Strategic Implications
- REFERENCE

Writing rules:
- write in concise business Korean
- use markdown
- base conclusions only on the supplied evidence
- if evidence is thin, say so directly
- prioritize recent evidence over older evidence
- treat older evidence as background when newer support exists
- do not add a separate report title, subtitle, date header, or closing line
- do not wrap the report in code fences such as ```markdown
- avoid repeating the same fact across SUMMARY, section 2, and section 3
- merge overlapping content instead of restating similar points
- prefer compact tables or comparison bullets when multiple companies share similar evidence
- keep the report dense and readable for an R&D decision-maker
- when direct evidence is insufficient, do not pretend certainty
- instead, explicitly state the limitation and explain that the estimate is inferred from indirect indicators

Section guidance:
- SUMMARY:
  - keep the full SUMMARY within roughly half a page
  - summarize the full report as one integrated executive summary
  - include the overall competitive situation, key technology judgment, and strategic direction for the self company
  - do not split the SUMMARY into separate per-technology blocks
  - do not include any table inside SUMMARY
  - use a highly readable structure with 3 short bullet groups:
    - 핵심 판단
    - 경쟁 구도
    - 자사 대응 방향
  - each bullet group should be concise and easy to scan
  - include only the final judgment, not detailed evidence repetition
- 1. Analysis Background:
  - brief and compact
  - must explain why these technologies need to be analyzed now
  - include the urgency from a market, standard, customer, or ecosystem perspective
  - mention how recent the collected evidence is using the provided freshness summary when available
  - only use these recency indicators: dated_ratio, recent_365d_ratio, most_recent_date
  - if needed, mention the analysis approach only briefly inside this section
- 2. Target Technology Status:
  - focus on technology-level status and core technical direction
  - avoid long company-by-company repetition already covered elsewhere
- 3. Competitor Trends:
  - focus on competitor comparison, recent moves, and supply-chain/ecosystem implications
  - explicitly include competitor-by-competitor TRL range
  - only include companies from the analyzed company list unless the evidence package explicitly defines otherwise
  - use a single company comparison table in this section
  - this section must never be empty
  - after the table, add concise company trend bullets or short paragraphs
  - if evidence is limited for a company, say that evidence is limited rather than omitting the company
  - when evidence is limited, state the limitation and explain which indirect indicators support the estimate
- 4. Strategic Implications:
  - produce a short, prioritized action list for the self company
  - avoid generic consulting language
""".strip()


def build_consistency_prompt(
    our_company: str,
    target_technologies: list[str],
    company_names: list[str],
    evidence_json: str,
) -> str:
    technologies = ", ".join(target_technologies)
    companies = ", ".join(company_names)
    return f"""
Self company: {our_company}
Target technologies: {technologies}
Other analyzed companies: {companies}

Evidence package:
{evidence_json}

Return a structured judgment with:
- one overall strategic posture chosen from:
  - aggressive_investment
  - selective_investment
  - monitor_and_wait
- one TRL range for each target technology
- up to 3 priority technologies ordered by urgency

Use only the target technologies listed above in priority_technologies.
""".strip()


def build_report_prompt(
    our_company: str,
    target_technologies: list[str],
    company_names: list[str],
    evidence_json: str,
    freshness_summary_json: str,
    references_markdown: str,
) -> str:
    technologies = ", ".join(target_technologies)
    companies = ", ".join(company_names)
    return f"""
Self company: {our_company}
Target technologies: {technologies}
Other analyzed companies: {companies}

Use the evidence package below to write the final markdown report.

Evidence package:
{evidence_json}

Freshness summary:
{freshness_summary_json}

Reference candidates:
{references_markdown}

Required output details:
1. SUMMARY must be an integrated executive summary for the full report and stay within about half a page in total.
1a. Format SUMMARY as 3 short bullet groups labeled `핵심 판단`, `경쟁 구도`, `자사 대응 방향`.
2. Do not include any table before section 3.
3. For each technology, provide a TRL range in prose where needed.
4. Competitor analysis should compare major companies against the self company, written as "자사".
5. Strategic implications must be actionable for R&D planning.
6. End with a REFERENCE section using the provided reference candidates.
7. Write the full report in Korean. Keep technology names, company names, and standards names in their common industry form when needed.
8. Prefer newer evidence when similar claims exist across multiple dates.
9. If recent confirmation is weak, reduce certainty and say that recent evidence is limited.
9a. If direct evidence is weak, explicitly acknowledge the limitation and explain that the estimate is based on indirect indicators.
10. Do not output an extra report title because the application already adds the top header.
11. Avoid duplicating the same company status sentence in both section 2 and section 3.
12. If HBM4, PIM, and CXL can be compared more clearly in a table, merge repeated prose into a table.
13. In section 1, explicitly answer the question: why should this technology be analyzed now?
13a. In section 1, quantify evidence recency using only these fields from the freshness summary: dated_ratio, recent_365d_ratio, most_recent_date.
14. Refer to {our_company} as "자사" in the report body rather than repeating the company name.
15. In section 3, include exactly one competitor table that explicitly shows each competitor's TRL range.
15a. Section 3 must contain both the competitor table and at least one short explanatory block after the table.
15b. Do not leave section 3 empty. If evidence is thin, still write the table and explicitly note the limitation.
16. The SUMMARY must state the recommended strategic posture for the self company, not just restate facts.
17. Use this exact section order: SUMMARY -> 1. 분석 배경 -> 2. 대상 기술 현황 -> 3. 경쟁사 동향 -> 4. 전략적 시사점 -> REFERENCE.
18. Do not output any section before SUMMARY except the content already added by the application.
19. When using indirect indicators, mention them explicitly in Korean, for example: 특허 출원 패턴, 학회 발표 빈도 변화, 채용 공고 키워드, 로드맵 표현, 파트너십 및 생태계 움직임.
""".strip()
