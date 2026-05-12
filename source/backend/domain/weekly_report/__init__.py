"""Deterministic weekly SD report rules and renderers."""

from .rules import build_weekly_report, parse_weekly_records, summarize_weekly_records
from .render import render_detail_html, render_html, render_markdown

__all__ = [
    "build_weekly_report",
    "parse_weekly_records",
    "summarize_weekly_records",
    "render_html",
    "render_detail_html",
    "render_markdown",
]
