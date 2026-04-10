"""PDF rendering node for the final markdown report."""

from __future__ import annotations

from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


KOREAN_FONT_NAME = "AppleGothic"
KOREAN_FONT_PATH = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"


def _register_font() -> str:
    if KOREAN_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(KOREAN_FONT_NAME, KOREAN_FONT_PATH))
    return KOREAN_FONT_NAME


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    base_styles = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "KoreanHeading1",
            parent=base_styles["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            spaceAfter=10,
            alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "KoreanHeading2",
            parent=base_styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            spaceBefore=8,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "h3": ParagraphStyle(
            "KoreanHeading3",
            parent=base_styles["Heading3"],
            fontName=font_name,
            fontSize=12,
            leading=16,
            spaceBefore=6,
            spaceAfter=5,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "KoreanBody",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=15,
            spaceAfter=5,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "KoreanBullet",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=15,
            leftIndent=10,
            bulletIndent=0,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "table": ParagraphStyle(
            "KoreanTable",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=12,
            alignment=TA_LEFT,
        ),
    }


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_inline_markup(text: str) -> str:
    escaped = _escape_html(text)
    escaped = escaped.replace("  ", " ")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(re.fullmatch(r"\|?[\s:-]+(\|[\s:-]+)+\|?", stripped))


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _build_table(table_lines: list[str], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [_split_markdown_row(line) for line in table_lines if line.strip()]
    header = rows[0]
    body = rows[2:] if len(table_lines) > 1 and _is_table_separator(table_lines[1]) else rows[1:]
    normalized_rows = [header, *body]

    max_cols = max(len(row) for row in normalized_rows)
    padded_rows = [row + [""] * (max_cols - len(row)) for row in normalized_rows]
    table_data = [
        [Paragraph(_format_inline_markup(cell), styles["table"]) for cell in row]
        for row in padded_rows
    ]

    available_width = A4[0] - (18 * mm * 2)
    col_width = available_width / max_cols
    table = Table(table_data, colWidths=[col_width] * max_cols, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAEAEA")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#777777")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _markdown_to_story(markdown_text: str) -> list:
    font_name = _register_font()
    styles = _build_styles(font_name)
    story: list = []
    lines = markdown_text.splitlines()
    index = 0

    # This renderer supports only the markdown features used by the generated report:
    # headings, bullets, paragraphs, and simple pipe tables.
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            story.append(Spacer(1, 4))
            index += 1
            continue
        if line == "---":
            story.append(Spacer(1, 8))
            index += 1
            continue
        if "|" in line and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            table_lines = [lines[index], lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            story.append(_build_table(table_lines, styles))
            story.append(Spacer(1, 8))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_format_inline_markup(line[2:].strip()), styles["h1"]))
            index += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(_format_inline_markup(line[3:].strip()), styles["h2"]))
            index += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(_format_inline_markup(line[4:].strip()), styles["h3"]))
            index += 1
            continue
        if line.startswith("- "):
            story.append(Paragraph(_format_inline_markup(line[2:].strip()), styles["bullet"], bulletText="•"))
            index += 1
            continue
        story.append(Paragraph(_format_inline_markup(line), styles["body"]))
        index += 1

    return story


def render_report_pdf(markdown_text: str, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="반도체 기술 전략 분석 보고서",
    )
    story = _markdown_to_story(markdown_text)
    document.build(story)
    return str(output_path)
