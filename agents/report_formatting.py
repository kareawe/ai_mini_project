"""Formatting helpers for final report rendering."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


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


def build_final_report(draft_report: str) -> str:
    korea_time = datetime.now(timezone(timedelta(hours=9)))
    generated_at = korea_time.strftime("%Y-%m-%d %H:%M KST")
    report_body = strip_wrapping_code_fence(draft_report)
    report_body = remove_summary_tables(report_body)

    return "\n".join(
        [
            "# 반도체 기술 전략 분석 보고서",
            "",
            f"- 생성 시각: {generated_at}",
            "",
            report_body,
            "",
        ]
    ).strip() + "\n"
