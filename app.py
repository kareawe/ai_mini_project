"""LangGraph entrypoint for the semiconductor strategy report workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from langgraph.graph import END, StateGraph

from agents.company_discovery import run_company_discovery
from agents.pdf_render import render_report_pdf
from agents.retrieval_eval import evaluate_retrieval
from agents.report_formatting import build_final_report
from agents.report import run_report
from agents.search_store import format_accuracy_summary, format_freshness_summary, load_saved_search_context
from agents.supervisor import route_next_action, run_supervisor
from agents.types import WorkflowState
from agents.utils import get_api_key
from agents.web_search import run_web_search


DEFAULT_TECHNOLOGIES = ["HBM4", "PIM", "CXL"]
DEFAULT_OUR_COMPANY = "SK hynix"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CONSISTENCY_RUNS = 5
DEFAULT_RETRIEVAL_EVAL_CASES = "data/retrieval_eval_queries.json"


def _mark_completed(result: dict, step_key: str) -> dict:
    result[f"{step_key}_done"] = True
    return result


def company_discovery_node(state: WorkflowState) -> dict:
    if state.get("report_only"):
        print("Skipping node: company_discovery (report-only mode)", flush=True)
        return {"company_discovery_done": True}
    result = run_company_discovery(
        state,
        model=state.get("model", DEFAULT_MODEL),
        max_companies=state.get("max_companies", 5),
    )
    _mark_completed(result, "company_discovery")
    print(f"Completed node: company_discovery ({len(result.get('company_names', []))} companies)", flush=True)
    return result


def web_search_node(state: WorkflowState) -> dict:
    if state.get("report_only"):
        input_path = Path(state["search_documents_input_path"])
        result = load_saved_search_context(
            input_path=input_path,
            our_company=state["our_company"],
            max_companies=state.get("max_companies", 5),
            embedding_model=state.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
            latest_doc_ratio_threshold=state.get("latest_doc_ratio_threshold", 0.3),
        )
        print(
            f"Loaded search documents: {input_path} "
            f"({len(result.get('search_documents', []))} items)",
            flush=True,
        )
        print(f"Recovered companies from saved search data: {result.get('company_names', [])}", flush=True)
        if result.get("freshness_summary"):
            print(f"[web_search] {format_freshness_summary(result['freshness_summary'])}", flush=True)
        if result.get("accuracy_summary"):
            print(f"[web_search] {format_accuracy_summary(result['accuracy_summary'])}", flush=True)
        eval_cases_path = Path(state.get("retrieval_eval_cases_path", DEFAULT_RETRIEVAL_EVAL_CASES))
        if eval_cases_path.exists():
            retrieval_metrics = evaluate_retrieval(
                store=result.get("vector_store"),
                eval_cases_path=eval_cases_path,
                embedding_model=state.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
            )
            result["retrieval_metrics"] = retrieval_metrics
            print(
                "[web_search] retrieval_eval "
                f"Hit@1={retrieval_metrics['hit_rate_at_1']:.2f} "
                f"Hit@3={retrieval_metrics['hit_rate_at_3']:.2f} "
                f"Hit@5={retrieval_metrics['hit_rate_at_5']:.2f} "
                f"MRR={retrieval_metrics['mrr']:.2f}",
                flush=True,
            )
        return _mark_completed(result, "web_search")
    result = run_web_search(
        state,
        model=state.get("model", DEFAULT_MODEL),
        embedding_model=state.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
        tech_min_docs=state.get("tech_min_docs", 5),
        company_min_docs=state.get("company_min_docs", 3),
        max_docs_per_query=state.get("max_docs_per_query", 2),
    )
    eval_cases_path = Path(state.get("retrieval_eval_cases_path", DEFAULT_RETRIEVAL_EVAL_CASES))
    if eval_cases_path.exists():
        retrieval_metrics = evaluate_retrieval(
            store=result.get("vector_store"),
            eval_cases_path=eval_cases_path,
            embedding_model=state.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
        )
        result["retrieval_metrics"] = retrieval_metrics
        print(
            "[web_search] retrieval_eval "
            f"Hit@1={retrieval_metrics['hit_rate_at_1']:.2f} "
            f"Hit@3={retrieval_metrics['hit_rate_at_3']:.2f} "
            f"Hit@5={retrieval_metrics['hit_rate_at_5']:.2f} "
            f"MRR={retrieval_metrics['mrr']:.2f}",
            flush=True,
        )
    _mark_completed(result, "web_search")
    print(
        "Completed node: web_search "
        f"({len(result.get('search_documents', []))} documents, "
        f"latest ratio={result.get('latest_doc_ratio', 0.0):.2f})",
        flush=True,
    )
    return result


def report_node(state: WorkflowState) -> dict:
    result = run_report(
        state,
        model=state.get("report_model", state.get("model", DEFAULT_MODEL)),
        embedding_model=state.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
    )
    _mark_completed(result, "report")
    print("Completed node: report", flush=True)
    return result


def _write_final_report(output_path: Path, report_text: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding="utf-8")


def formatting_node(state: WorkflowState) -> dict:
    final_report = build_final_report(
        state.get("draft_report", ""),
        freshness_summary=state.get("freshness_summary"),
        accuracy_summary=state.get("accuracy_summary"),
        consistency_summary=state.get("consistency_summary"),
    )

    markdown_output_path = Path(state["output_path"])
    _write_final_report(markdown_output_path, final_report)

    pdf_output_path = Path(
        state.get("pdf_output_path")
        or markdown_output_path.with_suffix(".pdf")
    )
    rendered_pdf_path = render_report_pdf(final_report, pdf_output_path)

    print(
        f"Completed node: formatting ({markdown_output_path}, {rendered_pdf_path})",
        flush=True,
    )
    return {
        "final_report": final_report,
        "pdf_output_path": rendered_pdf_path,
        "formatting_done": True,
    }


def build_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("supervisor", run_supervisor)
    graph.add_node("company_discovery", company_discovery_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("report", report_node)
    graph.add_node("formatting", formatting_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_next_action,
        {
            "company_discovery": "company_discovery",
            "web_search": "web_search",
            "report": "report",
            "formatting": "formatting",
            "end": END,
        },
    )
    graph.add_edge("company_discovery", "supervisor")
    graph.add_edge("web_search", "supervisor")
    graph.add_edge("report", "supervisor")
    graph.add_edge("formatting", "supervisor")

    return graph.compile()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a semiconductor strategy report.")
    parser.add_argument(
        "--query",
        default="Collect the latest HBM4, PIM, and CXL R&D updates, analyze competitor maturity and threat, and generate a strategy report.",
        help="High-level user request stored in the workflow state.",
    )
    parser.add_argument(
        "--technologies",
        nargs="+",
        default=DEFAULT_TECHNOLOGIES,
        help="Target technologies to analyze.",
    )
    parser.add_argument(
        "--output",
        default="outputs/strategy_report.md",
        help="Output markdown path.",
    )
    parser.add_argument(
        "--pdf-output",
        default="",
        help="Optional PDF path rendered after markdown formatting. Defaults to the markdown output path with .pdf suffix.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip discovery and live web search, and regenerate the report from saved search documents.",
    )
    parser.add_argument(
        "--search-documents-output",
        default="outputs/search_documents.json",
        help="Output JSON path for collected search documents.",
    )
    parser.add_argument(
        "--search-documents-input",
        default="outputs/search_documents.json",
        help="Input JSON path used in report-only mode.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model used for discovery and search.",
    )
    parser.add_argument(
        "--report-model",
        default=DEFAULT_MODEL,
        help="Model used for final report generation.",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Embedding model used for FAISS indexing and retrieval.",
    )
    parser.add_argument(
        "--max-companies",
        type=int,
        default=5,
        help="Maximum discovered companies to keep.",
    )
    parser.add_argument(
        "--tech-min-docs",
        type=int,
        default=5,
        help="Minimum document count per technology.",
    )
    parser.add_argument(
        "--company-min-docs",
        type=int,
        default=3,
        help="Minimum document count per company x technology.",
    )
    parser.add_argument(
        "--max-docs-per-query",
        type=int,
        default=2,
        help="Maximum structured search hits to request per query.",
    )
    parser.add_argument(
        "--max-web-search-retries",
        type=int,
        default=1,
        help="Maximum supervisor retries when search freshness is below threshold.",
    )
    parser.add_argument(
        "--latest-doc-ratio-threshold",
        type=float,
        default=0.3,
        help="Minimum ratio of recent documents required before report generation.",
    )
    parser.add_argument(
        "--consistency-runs",
        type=int,
        default=DEFAULT_CONSISTENCY_RUNS,
        help="Number of repeated report-judgment runs used for consistency evaluation.",
    )
    parser.add_argument(
        "--retrieval-eval-cases",
        default=DEFAULT_RETRIEVAL_EVAL_CASES,
        help="Retrieval evaluation dataset JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    get_api_key()

    print("Workflow: Supervisor -> Company Discovery -> Web Search -> Report -> Formatting", flush=True)
    print(
        "Run config: "
        f"technologies={', '.join(args.technologies)} | "
        f"max_companies={args.max_companies} | "
        f"tech_min_docs={args.tech_min_docs} | "
        f"company_min_docs={args.company_min_docs} | "
        f"max_docs_per_query={args.max_docs_per_query} | "
        f"report_only={args.report_only}",
        flush=True,
    )

    initial_state: WorkflowState = {
        "user_query": args.query,
        "our_company": DEFAULT_OUR_COMPANY,
        "target_technologies": args.technologies,
        "output_path": args.output,
        "pdf_output_path": args.pdf_output,
        "search_documents_path": args.search_documents_output,
        "search_documents_input_path": args.search_documents_input,
        "report_only": args.report_only,
        "model": args.model,
        "report_model": args.report_model,
        "embedding_model": args.embedding_model,
        "max_companies": args.max_companies,
        "tech_min_docs": args.tech_min_docs,
        "company_min_docs": args.company_min_docs,
        "max_docs_per_query": args.max_docs_per_query,
        "max_web_search_retries": args.max_web_search_retries,
        "latest_doc_ratio_threshold": args.latest_doc_ratio_threshold,
        "consistency_runs": args.consistency_runs,
        "retrieval_eval_cases_path": args.retrieval_eval_cases,
        "web_search_retry_count": 0,
        "latest_doc_ratio": 0.0,
        "freshness_check_passed": False,
        "company_discovery_done": False,
        "web_search_done": False,
        "report_done": False,
        "formatting_done": False,
    }

    app = build_graph()
    print("Invoking graph", flush=True)
    final_state = app.invoke(initial_state)
    print("Graph invocation completed", flush=True)

    print(f"Report written to {args.output}")
    print(f"PDF written to {final_state.get('pdf_output_path', args.pdf_output)}")
    print(f"Discovered companies: {', '.join(final_state.get('company_names', []))}")


if __name__ == "__main__":
    main()
