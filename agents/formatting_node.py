from pathlib import Path
import markdown
from weasyprint import HTML

from agents.models import FinalArtifactResult, RunContext
from agents.utils import write_text


class FormattingNode:
    def __init__(self, context: RunContext) -> None:
        self.context = context

    def _markdown_to_html(self, markdown_text: str) -> str:
        body_html = markdown.markdown(
            markdown_text,
            extensions=["tables", "fenced_code", "toc"],
        )

        return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Technology Strategy Report</title>
<style>
@page {{
    size: A4;
    margin: 20mm 18mm 22mm 18mm;
}}

html, body {{
    margin: 0;
    padding: 0;
    background: #ffffff;
    color: #111111;
    font-family: "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans CJK KR", sans-serif;
    line-height: 1.72;
    font-size: 12pt;
}}

body {{
    padding: 0;
}}

.report-wrap {{
    width: 100%;
}}

.cover-title {{
    font-size: 24pt;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0 0 14px 0;
}}

.top-rule {{
    border: none;
    border-top: 3px solid #111111;
    margin: 0 0 28px 0;
}}

.summary-box {{
    background: #f6f6f6;
    border-left: 6px solid #111111;
    padding: 18px 20px 16px 20px;
    margin: 0 0 28px 0;
}}

.summary-box h2 {{
    margin-top: 0;
    margin-bottom: 12px;
    font-size: 18pt;
    font-weight: 800;
    border: none;
    padding: 0;
}}

.summary-box p {{
    margin: 0 0 10px 0;
}}

h1 {{
    font-size: 24pt;
    font-weight: 800;
    margin: 0 0 12px 0;
    letter-spacing: -0.02em;
}}

h2 {{
    font-size: 18pt;
    font-weight: 800;
    margin: 30px 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 2px solid #111111;
    letter-spacing: -0.01em;
}}

h3 {{
    font-size: 14pt;
    font-weight: 700;
    margin: 20px 0 8px 0;
}}

h4 {{
    font-size: 12.5pt;
    font-weight: 700;
    margin: 16px 0 6px 0;
}}

p {{
    margin: 0 0 12px 0;
    text-align: justify;
}}

strong {{
    font-weight: 700;
}}

ul, ol {{
    margin: 8px 0 14px 20px;
    padding: 0;
}}

li {{
    margin: 0 0 6px 0;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0 20px 0;
    table-layout: fixed;
    font-size: 11pt;
}}

th {{
    background: #1f1f1f;
    color: #ffffff;
    text-align: left;
    padding: 9px 10px;
    border: 1px solid #1f1f1f;
    font-weight: 700;
}}

td {{
    border: 1px solid #cfcfcf;
    padding: 8px 10px;
    vertical-align: top;
}}

blockquote {{
    margin: 12px 0 16px 0;
    padding: 10px 14px;
    border-left: 4px solid #666666;
    background: #fafafa;
}}

code {{
    background: #f3f3f3;
    padding: 1px 4px;
    border-radius: 3px;
}}

hr {{
    border: none;
    border-top: 1px solid #d9d9d9;
    margin: 20px 0;
}}

.reference-list p,
.reference-list li {{
    font-size: 10.5pt;
    line-height: 1.55;
    margin-bottom: 6px;
}}

.reference-list ol {{
    margin-left: 18px;
}}

.reference-list li {{
    padding-left: 4px;
}}

.small-note {{
    font-size: 10pt;
    color: #555555;
}}

.no-break {{
    page-break-inside: avoid;
}}
</style>
</head>
<body>
<div class="report-wrap">
{self._post_process_html(body_html)}
</div>
</body>
</html>
"""

    def _post_process_html(self, body_html: str) -> str:
        html = body_html

        html = html.replace(
            "<h1>반도체 기술 전략 분석 보고서</h1>",
            """
<h1 class="cover-title">반도체 기술 전략 분석 보고서</h1>
<hr class="top-rule">
"""
        )

        if "<h2>SUMMARY</h2>" in html:
            parts = html.split("<h2>SUMMARY</h2>", 1)
            before_summary = parts[0]
            rest = parts[1]

            next_h2_idx = rest.find("<h2>")
            if next_h2_idx != -1:
                summary_content = rest[:next_h2_idx]
                after_summary = rest[next_h2_idx:]
            else:
                summary_content = rest
                after_summary = ""

            html = (
                before_summary
                + f'<div class="summary-box"><h2>SUMMARY</h2>{summary_content}</div>'
                + after_summary
            )

        if "<h2>REFERENCE</h2>" in html:
            html = html.replace('<h2>REFERENCE</h2>', '<h2>REFERENCE</h2><div class="reference-list">')
            html += "</div>"

        return html

    def run(self, markdown_text: str, run_id: str) -> FinalArtifactResult:
        final_dir = Path(self.context.outputs_dir) / "final"
        final_dir.mkdir(parents=True, exist_ok=True)

        markdown_path = final_dir / f"final_report_{run_id}.md"
        html_path = final_dir / f"final_report_{run_id}.html"
        pdf_path = final_dir / f"final_report_{run_id}.pdf"

        html_text = self._markdown_to_html(markdown_text)

        write_text(markdown_path, markdown_text)
        write_text(html_path, html_text)

        HTML(string=html_text).write_pdf(str(pdf_path))

        return FinalArtifactResult(
            markdown_path=str(markdown_path),
            html_path=str(html_path),
            pdf_path=str(pdf_path),
        )