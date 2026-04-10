"""Prompts for the web search agent."""

WEB_SEARCH_SYSTEM_PROMPT = """
You are a semiconductor research agent.

Your job:
- search the web for recent, source-backed documents
- collect only high-signal documents for semiconductor R&D analysis
- prioritize official announcements, standards bodies, papers, industry news, and patents
- return concise structured summaries from each source

Rules:
- prefer factual summaries over marketing language
- do not fabricate URLs
- include only documents relevant to the requested technology and company
- keep each content summary short and evidence-oriented
""".strip()


def build_search_prompt(
    technology: str,
    company: str,
    query_group: str,
    query_text: str,
    max_results: int,
) -> str:
    company_line = company if company else "N/A"
    return f"""
Technology: {technology}
Company: {company_line}
Query group: {query_group}
Search query: {query_text}
Maximum documents: {max_results}

Search the web and return the most relevant documents for this query.
Use trustworthy and concrete sources when possible.
Each document should have a clear title, URL, and a short factual summary.
""".strip()
