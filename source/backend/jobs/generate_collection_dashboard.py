"""Generate the collection data dashboard from configured Feishu sources."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.collection_dashboard.metrics import attach_configured_metrics, load_collection_metric_config
from domain.collection_dashboard.local_app_v2 import render_collection_dashboard_local_app_v2
from domain.collection_dashboard.local_app import render_collection_dashboard_local_app
from domain.collection_dashboard.render import (
    render_collection_dashboard_embed,
    render_collection_dashboard_iframe_preview,
)
from domain.collection_dashboard.rules import build_collection_dashboard
from integrations.dashboard_html import fetch_dashboard_sources, parse_dashboard_overview_html
from integrations.lark_fetch import fetch_weekly_sources
from jobs.weekly_report_config import DashboardSourceConfig, SourceConfig, load_weekly_config





@dataclass(frozen=True)
class CollectionDashboardConfig:
    cron: str
    timezone: str
    refresh_mode: str
    output_base_dir: str
    update_latest: bool
    weekly_sources_config: str
    metric_config: str
    sources: list[SourceConfig]
    dashboard_sources: list[DashboardSourceConfig]


def load_collection_dashboard_config(path: str | Path) -> CollectionDashboardConfig:
    """Load the dashboard config and reuse weekly source definitions."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Collection dashboard config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    schedule = raw.get("schedule") or {}
    output = raw.get("output") or {}
    sources = raw.get("sources") or {}
    weekly_sources_config = str(sources.get("include") or "config/weekly_sources.yaml").strip()
    weekly_sources_config = _resolve_existing_config_path(weekly_sources_config, config_path)
    weekly_config = load_weekly_config(weekly_sources_config)

    return CollectionDashboardConfig(
        cron=str(schedule.get("cron") or "0 9 * * *").strip(),
        timezone=str(schedule.get("timezone") or "Asia/Shanghai").strip(),
        refresh_mode=str(schedule.get("refresh_mode") or "daily_snapshot").strip(),
        output_base_dir=str(output.get("base_dir") or "data/collection-dashboard").strip(),
        update_latest=bool(output.get("update_latest", True)),
        weekly_sources_config=weekly_sources_config,
        metric_config=_resolve_existing_config_path(
            str(raw.get("metric_config") or "config/collection_dashboard_metrics.yaml").strip(),
            config_path,
        ),
        sources=weekly_config.sources,
        dashboard_sources=weekly_config.dashboard_sources,
    )


def _resolve_existing_config_path(value: str, config_path: Path) -> str:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return str(path)
    for base in (config_path.parent, config_path.parent.parent):
        candidate = base / path
        if candidate.exists():
            return candidate.as_posix()
    return value


def plan_collection_dashboard_run(
    config_path: str | Path,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic run plan for dry-runs and OpenClaw registration checks."""
    config = load_collection_dashboard_config(config_path)
    resolved_run_id = run_id or datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    base_dir = Path(config.output_base_dir)
    run_dir = base_dir / "runs" / resolved_run_id

    return {
        "run_id": resolved_run_id,
        "refresh_mode": config.refresh_mode,
        "output_dir": run_dir.as_posix(),
        "raw_dir": (run_dir / "raw").as_posix(),
        "latest_dir": (base_dir / "latest").as_posix(),
        "warehouse_dir": (base_dir / "warehouse").as_posix(),
        "source_count": len(config.sources),
        "enabled_source_count": sum(1 for source in config.sources if source.enabled),
        "dashboard_source_count": len(config.dashboard_sources),
        "enabled_dashboard_source_count": sum(1 for source in config.dashboard_sources if source.enabled),
        "weekly_sources_config": config.weekly_sources_config,
        "metric_config": config.metric_config,
        "cron": config.cron,
        "timezone": config.timezone,
    }


def generate_collection_dashboard(
    config_path: str | Path,
    *,
    from_raw_dir: str | Path | None = None,
    anchor_date: str | date | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Generate dashboard artifacts and return the run result payload."""
    config = load_collection_dashboard_config(config_path)
    run_plan = plan_collection_dashboard_run(config_path, run_id=run_id)
    output_dir = Path(run_plan["output_dir"])
    raw_dir = Path(run_plan["raw_dir"])
    warehouse_dir = Path(run_plan["warehouse_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    warehouse_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]]
    dashboard_manifest: list[dict[str, Any]] = []
    dashboard_overview: dict[str, Any] = {}
    source_metadata = {source.id: _source_config_metadata(source) for source in config.sources}

    if from_raw_dir:
        raw_paths = _copy_raw_snapshot(Path(from_raw_dir), raw_dir)
        manifest = _manifest_from_raw_paths(raw_paths, source_metadata)
        dashboard_overview = _load_dashboard_overview(raw_dir)
    else:
        manifest = fetch_weekly_sources(config.sources, raw_dir)
        dashboard_manifest, dashboard_overview = fetch_dashboard_sources(config.dashboard_sources, raw_dir)
        raw_paths = [
            Path(str(item["local_path"]))
            for item in manifest
            if item.get("status") == "success"
            and item.get("source_type") in {"collection_detail", "human_driving_output", "human_driving_schedule"}
            and item.get("local_path")
        ]

    full_manifest = [*manifest, *dashboard_manifest]
    if not raw_paths:
        payload = {"status": "failed", "reason": "no_collection_raw_sources", **run_plan}
        (output_dir / "run.log").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    dashboard = build_collection_dashboard(
        raw_paths,
        anchor_date=anchor_date,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        source_metadata=source_metadata,
    )
    dashboard["run_id"] = run_plan["run_id"]
    dashboard["refresh_mode"] = config.refresh_mode
    dashboard["sources_manifest"] = full_manifest
    dashboard["dashboard_overview"] = dashboard_overview
    dashboard["active_grain"] = "day"
    source_fetch_diagnostics = _source_fetch_diagnostics(full_manifest)
    if source_fetch_diagnostics:
        dashboard["metric_diagnostics"] = [
            *list(dashboard.get("metric_diagnostics") or []),
            *source_fetch_diagnostics,
        ]
    if dashboard_overview.get("diagnostics"):
        dashboard["metric_diagnostics"] = [
            *list(dashboard.get("metric_diagnostics") or []),
            *[
                {"source": "dashboard_overview", **item}
                for item in dashboard_overview.get("diagnostics", [])
                if isinstance(item, dict)
            ],
        ]

    metric_config = load_collection_metric_config(config.metric_config)
    attach_configured_metrics(dashboard, metric_config)
    weekly_report = _load_latest_weekly_report(Path(config.output_base_dir))

    _write_warehouse(warehouse_dir, dashboard, run_plan)
    _write_artifacts(output_dir, raw_dir, dashboard, dashboard_overview, full_manifest, run_plan, weekly_report)

    latest_dir = Path(run_plan["latest_dir"])
    if config.update_latest:
        update_collection_dashboard_latest(output_dir, latest_dir)

    return {
        "status": "collection_dashboard_generated",
        "collection_dashboard_path": (output_dir / "collection_dashboard.json").as_posix(),
        "local_app_html_path": (output_dir / "collection_data_dashboard.html").as_posix(),
        "embed_html_path": (output_dir / "collection_data_dashboard_embed.html").as_posix(),
        "iframe_preview_html_path": (output_dir / "collection_data_dashboard_iframe_preview.html").as_posix(),
        "latest_dir": latest_dir.as_posix(),
        "record_count": dashboard.get("record_count", 0),
        "vehicle_daily_status_count": dashboard.get("vehicle_daily_status_count", 0),
        "diagnostics_count": len(dashboard.get("diagnostics") or []) + len(dashboard.get("metric_diagnostics") or []),
        **run_plan,
    }


def update_collection_dashboard_latest(output_dir: str | Path, latest_dir: str | Path) -> None:
    """Mirror a collection dashboard run into ``latest``."""
    source_dir = Path(output_dir)
    target_dir = Path(latest_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    for filename in (
        "sources_manifest.json",
        "dashboard_overview.json",
        "collection_dashboard.json",
        "collection_data_dashboard.html",
        "collection_data_dashboard_embed.html",
        "collection_data_dashboard_iframe_preview.html",
        "run.log",
    ):
        source_file = source_dir / filename
        if source_file.exists():
            shutil.copy2(source_file, target_dir / filename)

    raw_source_dir = source_dir / "raw"
    if raw_source_dir.exists():
        raw_target_dir = target_dir / "raw"
        raw_target_dir.mkdir(parents=True, exist_ok=True)
        for source_file in raw_source_dir.iterdir():
            if source_file.is_file():
                shutil.copy2(source_file, raw_target_dir / source_file.name)


def _copy_raw_snapshot(source_dir: Path, raw_dir: Path) -> list[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Raw source directory not found: {source_dir}")
    raw_paths: list[Path] = []
    for source_file in sorted(source_dir.iterdir()):
        if not source_file.is_file():
            continue
        target_file = raw_dir / source_file.name
        if source_file.resolve() != target_file.resolve():
            shutil.copy2(source_file, target_file)
        if target_file.suffix.lower() == ".csv":
            raw_paths.append(target_file)
    return raw_paths


def _manifest_from_raw_paths(raw_paths: list[Path], source_metadata: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in raw_paths:
        metadata = source_metadata.get(path.stem) or {}
        items.append(
            {
                "source_id": path.stem,
                "source_type": metadata.get("source_type") or "collection_detail",
                "department": metadata.get("department") or "数采",
                "site": metadata.get("site") or "",
                "source_role": metadata.get("source_role") or "resource_schedule",
                "parser": metadata.get("parser") or "collection_detail",
                "sheet_id": metadata.get("sheet_id") or "",
                "status": "success",
                "local_path": path.as_posix(),
                "row_count": _count_rows(path),
                "reuse_mode": "local_raw_snapshot",
            }
        )
    return items


def _source_config_metadata(source: SourceConfig) -> dict[str, Any]:
    return {
        "source_id": source.id,
        "department": source.department,
        "site": source.site,
        "source_role": source.source_role,
        "parser": source.parser,
        "source_type": source.source_type,
        "sheet_id": source.sheet_id,
    }


def _load_dashboard_overview(raw_dir: Path) -> dict[str, Any]:
    overview_path = raw_dir / "dashboard_overview.json"
    if overview_path.exists():
        return json.loads(overview_path.read_text(encoding="utf-8"))
    html_files = sorted(raw_dir.glob("*.html"))
    for html_path in html_files:
        if "overview" not in html_path.stem and "collection" not in html_path.stem:
            continue
        return parse_dashboard_overview_html(html_path.read_text(encoding="utf-8"))
    return {
        "kpis": {},
        "scene_summary": [],
        "vehicle_collection_summary": [],
        "vehicle_quality_summary": [],
        "diagnostics": [{"code": "dashboard_overview_not_found", "message": "No dashboard overview snapshot found in raw directory."}],
    }


def _source_fetch_diagnostics(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for item in manifest:
        if item.get("status") != "failed":
            continue
        diagnostics.append(
            {
                "source": "sources_manifest",
                "code": "source_fetch_failed",
                "source_id": item.get("source_id"),
                "source_type": item.get("source_type"),
                "department": item.get("department"),
                "site": item.get("site"),
                "message": item.get("message") or item.get("error_type") or "source fetch failed",
            }
        )
    return diagnostics


def _load_latest_weekly_report(collection_output_base_dir: Path) -> dict[str, Any] | None:
    weekly_report_path = collection_output_base_dir.parent / "weekly" / "latest" / "report.json"
    if not weekly_report_path.exists():
        return None
    try:
        return json.loads(weekly_report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "risk_items": [
                {
                    "type": "weekly_report",
                    "target": weekly_report_path.as_posix(),
                    "reason": f"最新周报 JSON 解析失败: {exc}",
                    "level": "high",
                }
            ],
        }


def _write_warehouse(warehouse_dir: Path, dashboard: dict[str, Any], run_plan: dict[str, Any]) -> None:
    _write_jsonl(warehouse_dir / "collection_records.jsonl", dashboard.get("records") or [])
    _write_jsonl(warehouse_dir / "vehicle_daily_status.jsonl", dashboard.get("vehicle_daily_status") or [])
    _write_jsonl(warehouse_dir / "resource_schedule_records.jsonl", dashboard.get("resource_schedule_records") or [])
    _write_jsonl(warehouse_dir / "collection_output_records.jsonl", dashboard.get("collection_output_records") or [])
    _write_jsonl(
        warehouse_dir / "source_snapshots.jsonl",
        [
            {
                "run_id": run_plan["run_id"],
                "generated_at": dashboard.get("generated_at"),
                **item,
            }
            for item in dashboard.get("source_files") or []
        ],
    )
    _write_jsonl(
        warehouse_dir / "diagnostics.jsonl",
        [
            {"run_id": run_plan["run_id"], **item}
            for item in [
                *list(dashboard.get("diagnostics") or []),
                *list(dashboard.get("metric_diagnostics") or []),
            ]
            if isinstance(item, dict)
        ],
    )


def _write_artifacts(
    output_dir: Path,
    raw_dir: Path,
    dashboard: dict[str, Any],
    dashboard_overview: dict[str, Any],
    manifest: list[dict[str, Any]],
    run_plan: dict[str, Any],
    weekly_report: dict[str, Any] | None,
) -> None:
    (output_dir / "sources_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "dashboard_overview.json").write_text(json.dumps(dashboard_overview, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "collection_dashboard.json").write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "collection_data_dashboard.html").write_text(
        render_collection_dashboard_local_app(dashboard, weekly_report=weekly_report),
        encoding="utf-8",
    )
    (output_dir / "collection_data_dashboard_embed.html").write_text(render_collection_dashboard_embed(dashboard), encoding="utf-8")
    (output_dir / "collection_data_dashboard_iframe_preview.html").write_text(
        render_collection_dashboard_iframe_preview(),
        encoding="utf-8",
    )
    (output_dir / "run.log").write_text(
        "collection_data_dashboard workflow initialized\n"
        + json.dumps(run_plan, ensure_ascii=False, indent=2)
        + "\n\nartifacts\n"
        + f"collection_dashboard.json: {(output_dir / 'collection_dashboard.json').as_posix()}\n"
        + f"collection_data_dashboard.html: {(output_dir / 'collection_data_dashboard.html').as_posix()}\n"
        + f"collection_data_dashboard_embed.html: {(output_dir / 'collection_data_dashboard_embed.html').as_posix()}\n"
        + f"collection_data_dashboard_iframe_preview.html: {(output_dir / 'collection_data_dashboard_iframe_preview.html').as_posix()}\n"
        + f"raw_dir: {raw_dir.as_posix()}\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _count_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in handle)


def _parse_anchor_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the collection data dashboard.")
    parser.add_argument("--config", default="config/collection_dashboard.yaml")
    parser.add_argument("--from-raw-dir", help="Reuse an existing raw CSV/HTML snapshot directory instead of fetching Feishu.")
    parser.add_argument("--anchor-date", help="Anchor date for default day/week/month/year views, formatted as YYYY-MM-DD.")
    parser.add_argument("--run-id", help="Deterministic run id, mainly for tests.")
    parser.add_argument("--dry-run", action="store_true", help="Print the run plan without fetching or writing artifacts.")
    args = parser.parse_args()

    if args.dry_run:
        print(json.dumps(plan_collection_dashboard_run(args.config, run_id=args.run_id), ensure_ascii=False, indent=2))
        return 0

    result = generate_collection_dashboard(
        args.config,
        from_raw_dir=args.from_raw_dir,
        anchor_date=_parse_anchor_date(args.anchor_date),
        run_id=args.run_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "collection_dashboard_generated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
