"""Supervisor agent for workflow routing."""

from __future__ import annotations

from core.types import WorkflowState


def run_supervisor(state: WorkflowState) -> dict:
    if not state.get("company_discovery_done"):
        return {"next_action": "company_discovery"}
    if not state.get("web_search_done"):
        return {"next_action": "web_search"}
    if not state.get("freshness_check_passed", True):
        retry_count = state.get("web_search_retry_count", 0)
        max_retries = state.get("max_web_search_retries", 1)
        # Freshness retry is handled here so worker agents remain simple and only
        # perform their own task instead of deciding whether to rerun themselves.
        if retry_count < max_retries:
            return {
                "next_action": "web_search",
                "web_search_done": False,
                "web_search_retry_count": retry_count + 1,
            }
    if not state.get("report_done"):
        return {"next_action": "report"}
    if not state.get("formatting_done"):
        return {"next_action": "formatting"}
    return {"next_action": "end"}


def route_next_action(state: WorkflowState) -> str:
    return state.get("next_action", "end")
