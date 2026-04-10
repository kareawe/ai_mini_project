"""Company discovery agent."""

from __future__ import annotations

from collections import Counter
import re

from pydantic import BaseModel, Field

from prompts.company_discovery import DISCOVERY_SYSTEM_PROMPT, build_discovery_prompt

from agents.types import WorkflowState
from agents.utils import dedupe_keep_order, get_client, normalize_company_name


DISCOVERY_QUERIES = [
    "{technology} major companies",
    "{technology} key players partners",
]


class CompanyDiscoveryOutput(BaseModel):
    companies: list[str] = Field(default_factory=list)


def _parse_company_lines(text: str, our_company: str, max_companies: int) -> list[str]:
    companies: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        line = line.split("|")[0].strip()
        line = line.split(" - ")[0].strip()
        if not line or line.lower() == our_company.lower():
            continue
        companies.append(line)
        if len(companies) >= max_companies:
            break
    return companies


def run_company_discovery(
    state: WorkflowState,
    model: str,
    max_companies: int,
) -> dict:
    client = get_client()
    our_company = state["our_company"]

    counter: Counter[str] = Counter()
    for technology in state["target_technologies"]:
        print(f"[company_discovery] technology={technology}", flush=True)
        for template in DISCOVERY_QUERIES:
            query_text = template.format(technology=technology)
            print(f"[company_discovery] query={query_text}", flush=True)
            prompt = build_discovery_prompt(
                technology=technology,
                query_text=query_text,
                our_company=our_company,
                max_companies=max_companies,
            )
            companies: list[str] = []
            try:
                response = client.responses.parse(
                    model=model,
                    instructions=DISCOVERY_SYSTEM_PROMPT,
                    input=prompt,
                    tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
                    text_format=CompanyDiscoveryOutput,
                    temperature=0,
                    max_output_tokens=600,
                )
                parsed = response.output_parsed or CompanyDiscoveryOutput()
                companies = parsed.companies
            except Exception:
                fallback_response = client.responses.create(
                    model=model,
                    instructions=DISCOVERY_SYSTEM_PROMPT,
                    input=prompt
                    + "\n\nReturn plain text only, one company per line, with no explanation.",
                    tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
                    temperature=0,
                    max_output_tokens=400,
                )
                companies = _parse_company_lines(
                    fallback_response.output_text,
                    our_company=our_company,
                    max_companies=max_companies,
                )

            print(
                f"[company_discovery] query_result_count={len(companies)} "
                f"sample={companies[:3]}",
                flush=True,
            )

            for company in companies:
                normalized = normalize_company_name(company)
                if normalized.lower() == our_company.lower():
                    continue
                counter[normalized] += 1

    ordered = [company for company, _count in counter.most_common(max_companies)]
    company_names = dedupe_keep_order(ordered)
    print(f"[company_discovery] selected_companies={company_names}", flush=True)
    return {"company_names": company_names}
