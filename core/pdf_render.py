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
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PRIMARY_FONT_NAME = "Pretendard"
PRIMARY_FONT_REGULAR_PATH = "/Users/minhu/Library/Fonts/PretendardVariable.ttf"
FALLBACK_FONT_NAME = "AppleGothic"
FALLBACK_FONT_PATH = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

TITLE_COLOR = colors.HexColor("#173B63")
SECTION_COLOR = colors.HexColor("#1F4E79")
ACCENT_COLOR = colors.HexColor("#D8E7F5")
BORDER_COLOR = colors.HexColor("#B9C9D8")
TEXT_COLOR = colors.HexColor("#1E2933")
MUTED_COLOR = colors.HexColor("#6B7280")


def _register_font() -> str:
    if Path(PRIMARY_FONT_REGULAR_PATH).exists():
        try:
            if PRIMARY_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(PRIMARY_FONT_NAME, PRIMARY_FONT_REGULAR_PATH))
            pdfmetrics.registerFontFamily(
                PRIMARY_FONT_NAME,
                normal=PRIMARY_FONT_NAME,
                bold=PRIMARY_FONT_NAME,
            )
            return PRIMARY_FONT_NAME
        except Exception:
            pass

    if FALLBACK_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FALLBACK_FONT_NAME, FALLBACK_FONT_PATH))
    pdfmetrics.registerFontFamily(
        FALLBACK_FONT_NAME,
        normal=FALLBACK_FONT_NAME,
        bold=FALLBACK_FONT_NAME,
    )
    return FALLBACK_FONT_NAME


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    base_styles = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "KoreanHeading1",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=22,
            leading=28,
            textColor=TITLE_COLOR,
            spaceBefore=0,
            spaceAfter=12,
            alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "KoreanHeading2",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=15,
            leading=20,
            textColor=SECTION_COLOR,
            spaceBefore=14,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "h3": ParagraphStyle(
            "KoreanHeading3",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=12.5,
            leading=17,
            textColor=SECTION_COLOR,
            spaceBefore=8,
            spaceAfter=5,
            alignment=TA_LEFT,
        ),
        "label": ParagraphStyle(
            "KoreanLabel",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10.6,
            leading=14,
            textColor=SECTION_COLOR,
            spaceBefore=2,
            spaceAfter=2,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "KoreanBody",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10.2,
            leading=15.5,
            textColor=TEXT_COLOR,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "KoreanBullet",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10.2,
            leading=15.5,
            textColor=TEXT_COLOR,
            leftIndent=12,
            bulletIndent=0,
            spaceBefore=1,
            spaceAfter=5,
            alignment=TA_LEFT,
        ),
        "numbered": ParagraphStyle(
            "KoreanNumbered",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=10.2,
            leading=15.5,
            textColor=TEXT_COLOR,
            leftIndent=14,
            bulletIndent=0,
            spaceBefore=1,
            spaceAfter=5,
            alignment=TA_LEFT,
        ),
        "meta": ParagraphStyle(
            "KoreanMeta",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=9.2,
            leading=12,
            textColor=MUTED_COLOR,
            spaceAfter=8,
            alignment=TA_LEFT,
        ),
        "table": ParagraphStyle(
            "KoreanTable",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=13,
            textColor=TEXT_COLOR,
            alignment=TA_LEFT,
        ),
        "reference": ParagraphStyle(
            "KoreanReference",
            parent=base_styles["BodyText"],
            fontName=font_name,
            fontSize=8.8,
            leading=12.4,
            textColor=TEXT_COLOR,
            leftIndent=12,
            bulletIndent=0,
            spaceAfter=4,
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
    table_style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE8F5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), TITLE_COLOR),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER_COLOR),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, SECTION_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, 0), PRIMARY_FONT_NAME),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for row_index in range(1, len(table_data)):
        background = colors.white if row_index % 2 else colors.HexColor("#F7FAFC")
        table_style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), background))
    table.setStyle(TableStyle(table_style_commands))
    return table


def _is_heading(line: str) -> bool:
    return line.startswith("# ") or line.startswith("## ") or line.startswith("### ")


def _looks_like_reference_entry(line: str) -> bool:
    return " | http" in line or line.startswith("http")


def _is_section_heading(line: str) -> bool:
    return bool(re.match(r"^\d+\.\s+", line)) or line.strip() == "REFERENCE"


def _is_indented_continuation(line: str) -> bool:
    return bool(line) and line[:1].isspace()


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
        if line == "## 메트릭":
            story.append(Paragraph("메트릭", styles["h2"]))
            index += 1
            continue
        if line == "---":
            story.append(HRFlowable(width="100%", thickness=0.8, color=BORDER_COLOR, spaceBefore=4, spaceAfter=10))
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
            story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT_COLOR, spaceBefore=2, spaceAfter=10))
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
        if _is_section_heading(line):
            story.append(Paragraph(_format_inline_markup(line), styles["h2"]))
            index += 1
            continue
        if line.startswith("- 생성 시각:"):
            story.append(Paragraph(_format_inline_markup(line[2:].strip()), styles["meta"]))
            index += 1
            continue
        if line.startswith("- "):
            label = line[2:].strip()
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines) and _is_indented_continuation(lines[next_index]):
                story.append(Paragraph(_format_inline_markup(label), styles["label"]))
                story.append(Paragraph(_format_inline_markup(lines[next_index].strip()), styles["body"]))
                index = next_index + 1
                continue
        if line.startswith("- "):
            bullet_style = styles["reference"] if _looks_like_reference_entry(line[2:].strip()) else styles["bullet"]
            story.append(Paragraph(_format_inline_markup(line[2:].strip()), bullet_style, bulletText="•"))
            index += 1
            continue
        numbered_match = re.match(r"^(\d+\))\s+(.*)$", line)
        if numbered_match:
            story.append(
                Paragraph(
                    _format_inline_markup(numbered_match.group(2).strip()),
                    styles["numbered"],
                    bulletText=numbered_match.group(1),
                )
            )
            index += 1
            continue
        story.append(Paragraph(_format_inline_markup(line), styles["body"]))
        index += 1

    return story


def _draw_page_frame(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(ACCENT_COLOR)
    canvas.setLineWidth(0.8)
    canvas.line(doc.leftMargin, height - 11 * mm, width - doc.rightMargin, height - 11 * mm)
    canvas.line(doc.leftMargin, 10 * mm, width - doc.rightMargin, 10 * mm)
    canvas.setFont(_register_font(), 8.5)
    canvas.setFillColor(MUTED_COLOR)
    canvas.drawString(doc.leftMargin, height - 8 * mm, "Semiconductor Strategy Report")
    canvas.drawRightString(width - doc.rightMargin, 6.5 * mm, f"{canvas.getPageNumber()}")
    canvas.restoreState()


def render_report_pdf(markdown_text: str, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = _register_font()
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title="반도체 기술 전략 분석 보고서",
    )
    story = _markdown_to_story(markdown_text)
    document.build(story, onFirstPage=_draw_page_frame, onLaterPages=_draw_page_frame)
    return str(output_path)
