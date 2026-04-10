"""Formatting helpers for final report rendering."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from agents.types import AccuracySummary, ConsistencySummary, FreshnessSummary


def strip_wrapping_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text.strip()


def remove_summary_tables(text: str) -> str:
    lines = text.splitlines()
    background_heading = re.compile(r"^\s*(##\s*)?1\.\s*분석 배경")
    table_separator = re.compile(r"^\s*\|?[\s:-]+(\|[\s:-]+)+\|?\s*$")

    split_index = len(lines)
    for index, line in enumerate(lines):
        if background_heading.match(line):
            split_index = index
            break

    summary_lines = lines[:split_index]
    remaining_lines = lines[split_index:]

    cleaned_summary: list[str] = []
    index = 0
    while index < len(summary_lines):
        current = summary_lines[index]
        next_line = summary_lines[index + 1] if index + 1 < len(summary_lines) else ""

        # Summary tables are removed post-generation because the model still
        # occasionally inserts markdown tables despite explicit prompt rules.
        is_table_header = "|" in current and table_separator.match(next_line)
        is_table_separator = table_separator.match(current) is not None

        if is_table_header or is_table_separator:
            index += 1
            while index < len(summary_lines):
                table_line = summary_lines[index]
                if "|" in table_line or table_separator.match(table_line):
                    index += 1
                    continue
                if not table_line.strip():
                    index += 1
                break
            continue

        cleaned_summary.append(current)
        index += 1

    return "\n".join(cleaned_summary + remaining_lines).strip()


def ensure_summary_heading(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("# 요약"):
        return text.strip()
    if stripped.startswith("SUMMARY"):
        remainder = stripped[len("SUMMARY") :].lstrip()
        return f"# 요약\n\n{remainder}".strip()
    return f"# 요약\n\n{text.strip()}"


def _build_metrics_block(
    freshness_summary: FreshnessSummary | None,
    accuracy_summary: AccuracySummary | None,
    consistency_summary: ConsistencySummary | None,
) -> list[str]:
    if not freshness_summary and not accuracy_summary and not consistency_summary:
        return []

    lines = ["## 메트릭", ""]

    if freshness_summary:
        dated_ratio = freshness_summary.get("dated_ratio", 0.0)
        recent_365d_ratio = freshness_summary.get("recent_365d_ratio", 0.0)
        most_recent_date = freshness_summary.get("most_recent_date", "") or "unknown"
        lines.extend(
            [
                f"- 날짜 확인 가능 문서 비율: {dated_ratio:.0%}",
                f"- 최근 1년 문서 비율: {recent_365d_ratio:.0%}",
                f"- 최신 문서 일자: {most_recent_date}",
            ]
        )

    if accuracy_summary:
        high_trust_source_ratio = accuracy_summary.get("high_trust_source_ratio", 0.0)
        lines.append(f"- 고신뢰 출처 비율: {high_trust_source_ratio:.0%}")

    if consistency_summary:
        run_count = consistency_summary.get("run_count", 0)
        consistency_ratio = consistency_summary.get("overall_consistency_ratio", 0.0)
        lines.extend(
            [
                f"- 결론 일관성: {consistency_ratio:.0%} ({run_count}회 반복 평가)",
            ]
        )
        if consistency_summary.get("warning_required", False):
            lines.append(
                "- 주의: 동일 근거 기반 반복 평가에서 일관성이 낮아 최종 판단은 신중한 해석이 필요함."
            )

    lines.append("")
    return lines


def build_final_report(
    draft_report: str,
    freshness_summary: FreshnessSummary | None = None,
    accuracy_summary: AccuracySummary | None = None,
    consistency_summary: ConsistencySummary | None = None,
) -> str:
    korea_time = datetime.now(timezone(timedelta(hours=9)))
    generated_at = korea_time.strftime("%Y-%m-%d %H:%M KST")
    report_body = strip_wrapping_code_fence(draft_report)
    report_body = remove_summary_tables(report_body)
    report_body = ensure_summary_heading(report_body)
    metrics_block = _build_metrics_block(
        freshness_summary,
        accuracy_summary,
        consistency_summary,
    )

    return "\n".join(
        [
            "# 반도체 기술 전략 분석 보고서",
            "",
            f"- 생성 시각: {generated_at}",
            "",
            *metrics_block,
            report_body,
            "",
        ]
    ).strip() + "\n"
