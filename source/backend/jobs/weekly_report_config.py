"""Configuration loading for the weekly SD report workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml


@dataclass(frozen=True)
class ScheduleConfig:
    cron: str
    timezone: str
    week_mode: str


@dataclass(frozen=True)
class OutputConfig:
    mode: str
    base_dir: str
    update_latest: bool


@dataclass(frozen=True)
class SourceConfig:
    id: str
    source_type: str
    url: str
    sheet_id: str
    enabled: bool
    url_type: str
    token: str
    department: str
    site: str
    source_role: str
    parser: str


@dataclass(frozen=True)
class DashboardSourceConfig:
    id: str
    source_type: str
    url: str
    enabled: bool
    role: str


@dataclass(frozen=True)
class QueueSourceConfig:
    enabled: bool


@dataclass(frozen=True)
class WeeklyReportConfig:
    schedule: ScheduleConfig
    output: OutputConfig
    sources: list[SourceConfig]
    dashboard_sources: list[DashboardSourceConfig]
    queue_source: QueueSourceConfig
    resource_metrics_config: str


def load_weekly_config(path: str | Path) -> WeeklyReportConfig:
    """Load and validate the weekly source config."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Weekly source config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    schedule_raw = _required_mapping(raw, "schedule")
    output_raw = _required_mapping(raw, "output")
    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ValueError("weekly_sources.yaml must define at least one source")

    schedule = ScheduleConfig(
        cron=_required_string(schedule_raw, "cron"),
        timezone=_required_string(schedule_raw, "timezone"),
        week_mode=_required_string(schedule_raw, "week_mode"),
    )
    output = OutputConfig(
        mode=_required_string(output_raw, "mode"),
        base_dir=_required_string(output_raw, "base_dir"),
        update_latest=bool(output_raw.get("update_latest", True)),
    )
    sources = [_parse_source(item, index) for index, item in enumerate(sources_raw)]
    dashboard_sources_raw = raw.get("dashboard_sources") or []
    if not isinstance(dashboard_sources_raw, list):
        raise ValueError("weekly_sources.yaml dashboard_sources must be a list when defined")
    dashboard_sources = [_parse_dashboard_source(item, index) for index, item in enumerate(dashboard_sources_raw)]
    queue_source_raw = raw.get("queue_source") or {}
    queue_source = QueueSourceConfig(enabled=bool(queue_source_raw.get("enabled", False)))
    resource_metrics_config = str(raw.get("resource_metrics_config") or "config/resource_weekly_metrics.yaml").strip()

    return WeeklyReportConfig(
        schedule=schedule,
        output=output,
        sources=sources,
        dashboard_sources=dashboard_sources,
        queue_source=queue_source,
        resource_metrics_config=resource_metrics_config,
    )


def _parse_source(item: Any, index: int) -> SourceConfig:
    if not isinstance(item, dict):
        raise ValueError(f"sources[{index}] must be a mapping")

    source_id = _required_string(item, "id")
    url = _required_string(item, "url")
    url_type, token, query_sheet_id = parse_lark_source_url(url)
    configured_sheet_id = str(item.get("sheet_id") or "").strip()
    sheet_id = configured_sheet_id or query_sheet_id
    if not sheet_id:
        raise ValueError(f"{source_id} must define sheet_id or a sheet= query value")
    if configured_sheet_id and query_sheet_id and configured_sheet_id != query_sheet_id:
        raise ValueError(
            f"{source_id} sheet_id {configured_sheet_id!r} does not match URL sheet {query_sheet_id!r}"
        )

    return SourceConfig(
        id=source_id,
        source_type=str(item.get("source_type") or "collection_detail"),
        url=url,
        sheet_id=sheet_id,
        enabled=bool(item.get("enabled", True)),
        url_type=url_type,
        token=token,
        department=str(item.get("department") or "数采").strip(),
        site=str(item.get("site") or "").strip(),
        source_role=str(item.get("source_role") or "collection_detail").strip(),
        parser=str(item.get("parser") or item.get("source_type") or "collection_detail").strip(),
    )


def _parse_dashboard_source(item: Any, index: int) -> DashboardSourceConfig:
    if not isinstance(item, dict):
        raise ValueError(f"dashboard_sources[{index}] must be a mapping")

    source_id = _required_string(item, "id")
    source_type = str(item.get("source_type") or "dashboard_html").strip()
    if source_type != "dashboard_html":
        raise ValueError(f"{source_id} unsupported dashboard source_type: {source_type}")

    return DashboardSourceConfig(
        id=source_id,
        source_type=source_type,
        url=_required_string(item, "url"),
        enabled=bool(item.get("enabled", True)),
        role=str(item.get("role") or "production_quality_snapshot").strip(),
    )


def parse_lark_source_url(url: str) -> tuple[str, str, str]:
    """Return ``(url_type, token, sheet_id_from_query)`` for supported Lark URLs."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"Unsupported Lark source URL: {url}")

    query_sheet_id = (parse_qs(parsed.query).get("sheet") or [""])[0]
    for marker, url_type in (("wiki", "wiki"), ("sheets", "sheet")):
        if marker in parts:
            marker_index = parts.index(marker)
            if marker_index + 1 >= len(parts):
                raise ValueError(f"Missing token in Lark source URL: {url}")
            return url_type, parts[marker_index + 1], query_sheet_id

    raise ValueError(f"Unsupported Lark source URL type: {url}")


def _required_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"weekly_sources.yaml must define mapping {key!r}")
    return value


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing required config value: {key}")
    return str(value).strip()
