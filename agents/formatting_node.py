"""
Formatting Node
- 최종 승인된 보고서 초안을 PDF로 변환
- outputs/ 폴더에 저장
- reportlab 사용 (시스템 라이브러리 불필요, macOS 완벽 호환)
- 핵심 원칙: formatting은 내용을 다시 쓰지 않고, draft_report를 그대로 렌더링한다.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from agents.states import FormattingState

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

DEFAULT_TITLE = "반도체 핵심 기술 경쟁사 기술 전략 분석 보고서"


def normalize_text_for_compare(s: str) -> str:
    s = s.replace("\u00A0", " ")
    s = s.replace("\u200B", "")
    s = s.replace("\u200C", "")
    s = s.replace("\u200D", "")
    s = s.replace("\ufeff", "")
    s = re.sub(r"\s+", " ", s.strip())
    return s


def clean_duplicate_lines(text: str) -> str:
    """
    연속 중복 줄 제거
    """
    lines = text.splitlines()
    cleaned = []
    prev = None

    for line in lines:
        current = normalize_text_for_compare(line)
        if current and current == prev:
            continue
        cleaned.append(line)
        if current:
            prev = current

    return "\n".join(cleaned)


def normalize_heading(line: str) -> str:
    """
    제목 표기 통일
    """
    stripped = normalize_text_for_compare(line)

    if not stripped:
        return ""

    if re.fullmatch(r"SUMMARY\s*:?\s*.*", stripped, flags=re.IGNORECASE):
        title = re.sub(r"^SUMMARY\s*:?\s*", "", stripped, flags=re.IGNORECASE).strip()
        return "## SUMMARY" if not title else f"## SUMMARY: {title}"

    if re.fullmatch(r"#{1,6}\s+.+", stripped):
        level, title = stripped.split(" ", 1)
        return f"{level} {title.strip()}"

    if re.fullmatch(r"\d+\.\s+.+", stripped):
        return f"## {stripped}"

    if re.fullmatch(r"\d+\.\d+\s+.+", stripped):
        return f"### {stripped}"

    return line.rstrip()

def extract_heading_key(line: str) -> str:
    """
    제목을 비교용 key로 정규화
    """
    stripped = normalize_text_for_compare(line)

    # markdown 제거
    stripped = re.sub(r"^#{1,6}\s+", "", stripped)

    # SUMMARY 통일
    if re.match(r"summary\s*:?", stripped, re.IGNORECASE):
        stripped = re.sub(r"summary\s*:?\s*", "", stripped, flags=re.IGNORECASE)
        return f"summary:{stripped.lower()}"

    return stripped.lower()

def normalize_markdown_headings(text: str) -> str:
    normalized = []
    for line in text.splitlines():
        normalized.append(normalize_heading(line))
    return "\n".join(normalized)


def remove_duplicate_sections(text: str) -> str:
    seen = set()
    result = []

    for line in text.splitlines():
        stripped = normalize_text_for_compare(line)

        if not stripped:
            result.append("")
            continue

        # 제목 후보인지 판단
        is_heading = bool(
            re.match(r"(#{1,6}\s+.+)|(\d+\.\s+.+)|(SUMMARY\s*:?.+)", stripped, re.IGNORECASE)
        )

        if is_heading:
            key = extract_heading_key(line)

            if key in seen:
                continue  # 🔥 중복 제거 핵심

            seen.add(key)

        result.append(line.rstrip())

    return "\n".join(result)


def ensure_spacing_around_headings(text: str) -> str:
    """
    제목 전후 여백 정리
    """
    lines = text.splitlines()
    result = []

    for i, line in enumerate(lines):
        stripped = normalize_text_for_compare(line)
        is_heading = bool(re.fullmatch(r"#{1,3}\s+.+", stripped))

        if is_heading and result and result[-1].strip():
            result.append("")

        result.append(line.rstrip())

        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if is_heading and normalize_text_for_compare(next_line):
            result.append("")

    # 과도한 빈 줄 축소
    collapsed = []
    blank_count = 0
    for line in result:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                collapsed.append("")
        else:
            blank_count = 0
            collapsed.append(line)

    return "\n".join(collapsed).strip()


def ensure_report_markdown(draft: str) -> str:
    """
    draft_report를 PDF 렌더링 가능한 markdown 형태로 정리
    """
    cleaned = (draft or "").strip()
    now = datetime.now().strftime("%Y년 %m월 %d일")

    if not cleaned:
        return "\n".join([
            f"# {DEFAULT_TITLE}",
            f"**작성일:** {now}  |  **분류:** 대외비",
            "",
            "보고서 내용이 생성되지 않았습니다.",
        ])

    # 제목 표기 통일
    cleaned = clean_duplicate_lines(cleaned)
    cleaned = ensure_spacing_around_headings(cleaned)   

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    has_title = any(DEFAULT_TITLE in line for line in lines[:10])
    has_meta = any(line.startswith("**작성일:**") for line in lines)

    prefix_lines = []

    if not has_title:
        prefix_lines.append(f"# {DEFAULT_TITLE}")
    if not has_meta:
        prefix_lines.append(f"**작성일:** {now}  |  **분류:** 대외비")

    if prefix_lines:
        result = "\n".join(prefix_lines + [cleaned])    
    else:
        result = cleaned
        
    result = clean_duplicate_lines(result)
    result = remove_duplicate_sections(result)
    result = ensure_spacing_around_headings(result)

    return result.strip()


def markdown_to_pdf(markdown_text: str, output_path: str) -> bool:
    logger.info(f"[Formatting] PDF 생성 중: {output_path}")

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            HRFlowable,
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        font_name = "Helvetica"
        font_candidates = [
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/System/Library/Fonts/Supplemental/Apple SD Gothic Neo.ttc",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/NanumGothic.ttf",
        ]

        for fp in font_candidates:
            if Path(fp).exists():
                try:
                    pdfmetrics.registerFont(TTFont("KoreanFont", fp))
                    font_name = "KoreanFont"
                    logger.info(f"[Formatting] 한글 폰트 로드: {fp}")
                    break
                except Exception:
                    continue

        base = dict(fontName=font_name, wordWrap="CJK")

        style_h1 = ParagraphStyle(
            "h1",
            parent=None,
            fontName=font_name,
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#102A43"),
            spaceBefore=0,
            spaceAfter=8,
        )
        style_h2 = ParagraphStyle(
            "h2",
            parent=None,
            fontName=font_name,
            fontSize=13.5,
            leading=17,
            alignment=TA_LEFT,
            textColor=colors.white,
            backColor=colors.HexColor("#1F3C88"),
            leftIndent=0,
            rightIndent=0,
            borderPadding=6,
            spaceBefore=10,
            spaceAfter=6,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_h3 = ParagraphStyle(
            "h3",
            parent=None,
            fontName=font_name,
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#1F2937"),
            backColor=colors.HexColor("#EEF2FF"),
            borderPadding=4,
            leftIndent=0,
            rightIndent=0,
            spaceBefore=6,
            spaceAfter=4,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_body = ParagraphStyle(
            "body",
            parent=None,
            fontName=font_name,
            fontSize=9.6,
            leading=15.5,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#222222"),
            spaceBefore=0,
            spaceAfter=5,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_meta = ParagraphStyle(
            "meta",
            parent=None,
            fontName=font_name,
            fontSize=8.7,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#6B7280"),
            spaceBefore=0,
            spaceAfter=4,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_bullet = ParagraphStyle(
            "bullet",
            parent=None,
            fontName=font_name,
            fontSize=9.4,
            leading=14.5,
            textColor=colors.HexColor("#222222"),
            leftIndent=13,
            bulletIndent=2,
            spaceBefore=0,
            spaceAfter=3,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_quote = ParagraphStyle(
            "quote",
            parent=None,
            fontName=font_name,
            fontSize=9.2,
            leading=14,
            textColor=colors.HexColor("#374151"),
            backColor=colors.HexColor("#F3F4F6"),
            leftIndent=10,
            rightIndent=4,
            borderPadding=6,
            spaceBefore=3,
            spaceAfter=6,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_code = ParagraphStyle(
            "code",
            parent=None,
            fontName=font_name,
            fontSize=8.4,
            leading=12,
            textColor=colors.HexColor("#111827"),
            backColor=colors.HexColor("#F8FAFC"),
            leftIndent=8,
            rightIndent=4,
            borderPadding=6,
            spaceBefore=2,
            spaceAfter=6,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_table_header = ParagraphStyle(
            "table_header",
            parent=None,
            fontName=font_name,
            fontSize=8.6,
            leading=10.8,
            textColor=colors.white,
            alignment=TA_CENTER,
            **{k: v for k, v in base.items() if k != "fontName"},
        )
        style_table_body = ParagraphStyle(
            "table_body",
            parent=None,
            fontName=font_name,
            fontSize=8.3,
            leading=10.8,
            textColor=colors.HexColor("#111827"),
            alignment=TA_LEFT,
            **{k: v for k, v in base.items() if k != "fontName"},
        )

        def escape(text: str) -> str:
            return (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        def inline_fmt(text: str) -> str:
            text = escape(text)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"`(.+?)`", rf"<font name='{font_name}'>\1</font>", text)
            text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
            return text

        def build_col_widths(col_count: int, available_width: float):
            if col_count <= 0:
                return []

            if col_count == 1:
                return [available_width]
            if col_count == 2:
                return [available_width * 0.30, available_width * 0.70]
            if col_count == 3:
                return [available_width * 0.18, available_width * 0.22, available_width * 0.60]
            if col_count == 4:
                return [available_width * 0.14, available_width * 0.18, available_width * 0.18, available_width * 0.50]
            if col_count == 5:
                return [
                    available_width * 0.12,
                    available_width * 0.14,
                    available_width * 0.14,
                    available_width * 0.14,
                    available_width * 0.46,
                ]

            even = available_width / col_count
            return [even] * col_count

        story = []
        lines = markdown_text.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if line.startswith("# ") and not line.startswith("## "):
                story.append(Spacer(1, 4))
                story.append(Paragraph(inline_fmt(line[2:]), style_h1))
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=1.4,
                        color=colors.HexColor("#1F3C88"),
                        spaceBefore=2,
                        spaceAfter=10,
                    )
                )

            elif line.startswith("**작성일:**") or line.startswith("**분류:**") or line.startswith("**분석 대상 기술:**"):
                story.append(Paragraph(inline_fmt(line), style_meta))

            elif line.startswith("## ") and not line.startswith("### "):
                story.append(Spacer(1, 5))
                story.append(Paragraph(inline_fmt(line[3:]), style_h2))

            elif line.startswith("### "):
                story.append(Spacer(1, 2))
                story.append(Paragraph(inline_fmt(line[4:]), style_h3))

            elif stripped == "---":
                story.append(Spacer(1, 4))
                story.append(
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=colors.HexColor("#D1D5DB"),
                        spaceBefore=2,
                        spaceAfter=6,
                    )
                )

            elif line.startswith(">"):
                quote_text = line.lstrip("> ").strip()
                story.append(Paragraph(inline_fmt(quote_text), style_quote))

            elif line.startswith("|"):
                table_lines = []
                while i < len(lines) and lines[i].startswith("|"):
                    table_lines.append(lines[i])
                    i += 1

                rows = []
                max_cols = 0

                for row_idx, row in enumerate(table_lines):
                    if re.match(r"^\|[-| :]+\|$", row.strip()):
                        continue

                    cells = [cell.strip() for cell in row.strip("|").split("|")]
                    max_cols = max(max_cols, len(cells))
                    row_style = style_table_header if row_idx == 0 else style_table_body
                    rows.append([Paragraph(inline_fmt(cell), row_style) for cell in cells])

                if rows:
                    normalized_rows = []
                    for row in rows:
                        if len(row) < max_cols:
                            row = row + [Paragraph("", style_table_body) for _ in range(max_cols - len(row))]
                        normalized_rows.append(row)

                    available_width = A4[0] - 40 * mm
                    col_widths = build_col_widths(max_cols, available_width)

                    table = Table(
                        normalized_rows,
                        colWidths=col_widths,
                        repeatRows=1,
                        hAlign="LEFT",
                    )
                    table.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3C88")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                            colors.white,
                            colors.HexColor("#F8FAFC"),
                        ]),
                        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#CBD5E1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]))
                    story.append(Spacer(1, 3))
                    story.append(KeepTogether([table]))
                    story.append(Spacer(1, 6))

                continue

            elif line.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(escape(lines[i]))
                    i += 1
                story.append(Paragraph("<br/>".join(code_lines), style_code))

            elif re.match(r"^[-*]\s+", stripped):
                story.append(Paragraph("• " + inline_fmt(stripped[2:]), style_bullet))

            elif stripped == "":
                story.append(Spacer(1, 3))

            else:
                story.append(Paragraph(inline_fmt(line), style_body))

            i += 1

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
        )
        doc.build(story)

        logger.info(f"[Formatting] 저장 완료: {output_path}")
        return True

    except ImportError as e:
        logger.error(f"[Formatting] 라이브러리 미설치: {e}\n  → pip install reportlab")
        return False
    except Exception as e:
        logger.error(f"[Formatting] PDF 생성 실패: {e}", exc_info=True)
        return False


def run_formatting_node(state: FormattingState) -> FormattingState:
    draft = state.get("draft_report", "")
    state["status"] = "running"

    if not draft:
        logger.warning("[Formatting] draft_report 없음 — 생성된 본문 없이 진행")

    structured = ensure_report_markdown(draft)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = str(OUTPUT_DIR / f"semiconductor_strategy_report_{timestamp}.pdf")

    success = markdown_to_pdf(structured, output_path)

    state["final_report"] = structured

    if success:
        state["output_path"] = output_path
        state["status"] = "done"
        logger.info(f"[Formatting] 최종 보고서 저장: {output_path}")
    else:
        logger.error("[Formatting] PDF 생성 실패")
        state["status"] = "done"

    return state