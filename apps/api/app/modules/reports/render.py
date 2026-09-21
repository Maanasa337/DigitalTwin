"""Rendering (FR-RP-02): one data dict, four output formats.

Jinja2 produces the HTML; WeasyPrint paginates it into the PDF, python-docx writes the same figures
into a Word file and the Markdown writer emits them as text. All four read the *same* stored data,
so the PDF and the DOCX of one report cannot say different things.

**PDF fallback.** WeasyPrint needs pango and cairo. They are installed in the API image, which is
the runtime this platform ships as; on a bare developer machine without them the HTML is stored
instead and the report records `format="html"`. The report still opens in a browser and still prints
— it is simply not paginated — and the caller can see from the format which one it got.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

log = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

TITLES = {
    "machine_health": "Machine health report",
    "weekly_maintenance": "Weekly maintenance report",
    "energy": "Energy report",
    "benchmark": "Model benchmark report",
    "incident": "Incident report",
}

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown; charset=utf-8",
    "html": "text/html; charset=utf-8",
}


def environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        # A report that silently prints an empty cell because a key was renamed is worse than one
        # that fails loudly in the worker, where the error lands on the report row.
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(context: dict[str, Any]) -> str:
    template = environment().get_template(f"{context['type']}.html.j2")
    return template.render(**context)


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def render_pdf(html: str) -> bytes | None:
    """PDF bytes, or None when the native rendering libraries are not installed on this host."""
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except Exception:
        log.warning("weasyprint unavailable or failed; storing HTML instead", exc_info=True)
        return None


def render_markdown(context: dict[str, Any]) -> str:
    """Markdown for the benchmark report and for anyone who wants the figures in plain text."""
    data = context["data"]
    lines = [
        f"# {context['title']}",
        "",
        f"{context['scope_name']} · generated {context['generated_at']:%d %b %Y %H:%M %Z}",
        "",
        "## Summary",
        "",
        context["summary_text"],
        "",
    ]
    for heading, body in _sections(data):
        lines += [f"## {heading}", ""]
        lines += body
        lines.append("")
    return "\n".join(lines)


def render_docx(context: dict[str, Any]) -> bytes:
    """The same sections as the Markdown, in a Word file (FR-RP-02)."""
    import io

    from docx import Document

    document = Document()
    document.add_heading(context["title"], level=0)
    document.add_paragraph(f"{context['scope_name']} · generated {context['generated_at']:%d %b %Y %H:%M %Z}")
    document.add_heading("Summary", level=1)
    document.add_paragraph(context["summary_text"])

    for heading, body in _sections(context["data"]):
        document.add_heading(heading, level=1)
        for line in body:
            document.add_paragraph(line.lstrip("- ").strip())

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _sections(data: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Flatten the report data into headed text blocks: scalars as figures, lists as rows."""
    figures = [
        f"- **{_label(key)}**: {value}"
        for key, value in data.items()
        if not isinstance(value, dict | list) and value is not None
    ]
    sections: list[tuple[str, list[str]]] = []
    if figures:
        sections.append(("Figures", figures))
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            sections.append((_label(key), _rows(value)))
        elif isinstance(value, dict) and value and key != "asset":
            sections.append((_label(key), [f"- **{_label(k)}**: {v}" for k, v in value.items()]))
    return sections


def _rows(rows: list[dict[str, Any]], limit: int = 25) -> list[str]:
    return ["- " + ", ".join(f"{_label(k)}: {v}" for k, v in row.items() if v is not None) for row in rows[:limit]]


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def build_context(
    *,
    report_id: str,
    report_type: str,
    scope_name: str,
    period_start: datetime | None,
    period_end: datetime | None,
    generated_at: datetime,
    data: dict[str, Any],
    charts: dict[str, str],
    summary_text: str,
    summary_audit: dict[str, Any],
    llm_model: str,
    lang: str = "en",
) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "type": report_type,
        "title": TITLES.get(report_type, "Report"),
        "scope_name": scope_name,
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": generated_at,
        "data": data,
        "charts": charts,
        "summary_text": summary_text,
        "summary_audit": summary_audit,
        "llm_model": llm_model,
        "lang": lang,
    }


def render(context: dict[str, Any], fmt: str) -> tuple[bytes, str]:
    """Return (bytes, the format actually produced). PDF may degrade to HTML; nothing else does."""
    if fmt == "md":
        return render_markdown(context).encode(), "md"
    if fmt == "docx":
        return render_docx(context), "docx"

    html = render_html(context)
    if fmt == "html":
        return html.encode(), "html"
    pdf = render_pdf(html)
    return (pdf, "pdf") if pdf is not None else (html.encode(), "html")
