"""Fetch and parse Neolix dashboard HTML snapshots for weekly reports."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from jobs.weekly_report_config import DashboardSourceConfig


HtmlFetcher = Callable[[str], str]


def fetch_dashboard_sources(
    sources: list[DashboardSourceConfig],
    raw_dir: str | Path,
    fetcher: HtmlFetcher | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch configured dashboard HTML sources into ``raw_dir`` and parse their data."""
    target_dir = Path(raw_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    fetch_html = fetcher or _fetch_html

    manifest: list[dict[str, object]] = []
    merged_overview: dict[str, object] = _empty_overview()
    for source in sources:
        base = _base_manifest(source)
        if not source.enabled:
            manifest.append(base | {"status": "skipped", "message": "source disabled"})
            continue

        try:
            html = fetch_html(source.url)
            html_path = target_dir / f"{source.id}.html"
            html_path.write_text(html, encoding="utf-8")
            overview = parse_dashboard_overview_html(html, start_date=start_date, end_date=end_date)
            merged_overview = _merge_overview(merged_overview, overview)
            manifest.append(
                base
                | {
                    "status": "success",
                    "local_path": html_path.as_posix(),
                    "file_sha256": _sha256(html_path),
                    "kpi_count": len(overview.get("kpis", {})),
                    "scene_count": len(overview.get("scene_summary", [])),
                    "vehicle_collection_count": len(overview.get("vehicle_collection_summary", [])),
                    "vehicle_quality_count": len(overview.get("vehicle_quality_summary", [])),
                }
            )
        except Exception as exc:
            merged_overview["diagnostics"] = [
                *list(merged_overview.get("diagnostics", [])),
                {
                    "source_id": source.id,
                    "code": "dashboard_source_failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            ]
            manifest.append(base | {"status": "failed", "error_type": type(exc).__name__, "message": str(exc)})

    overview_path = target_dir / "dashboard_overview.json"
    overview_path.write_text(json.dumps(merged_overview, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest, merged_overview


def parse_dashboard_overview_html(
    html: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    """Parse the self-contained collection overview dashboard HTML."""
    parser = _DashboardOverviewParser()
    parser.feed(html)
    parser.close()
    dom_overview = _overview_from_dom(parser)
    data_overview = _overview_from_embedded_data(html, start_date=start_date, end_date=end_date)
    overview = data_overview or dom_overview
    if not _has_dashboard_payload(overview):
        overview["diagnostics"] = [
            *list(overview.get("diagnostics", [])),
            {
                "code": "dashboard_data_not_found",
                "message": "No KPI, scene, vehicle collection, or vehicle quality data found in dashboard HTML.",
            },
        ]
    return overview


def _overview_from_dom(parser: _DashboardOverviewParser) -> dict[str, object]:
    tables = parser.tables
    collection_rows: list[dict[str, str]] = []
    quality_rows: list[dict[str, str]] = []
    for table in tables:
        rows = table.get("rows", [])
        if len(rows) < 2:
            continue
        header = rows[0]
        body = [_row_to_dict(header, row) for row in rows[1:]]
        header_text = "|".join(header)
        if "Records" in header_text and "里程" in header_text:
            collection_rows = body
        elif "总 Clips" in header_text or "不通过率" in header_text:
            quality_rows = body

    return {
        "kpis": parser.kpis,
        "scene_summary": parser.scene_options,
        "vehicle_collection_summary": collection_rows,
        "vehicle_quality_summary": quality_rows,
        "tables": tables,
        "diagnostics": [],
    }


def _overview_from_embedded_data(
    html: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object] | None:
    data = _extract_embedded_data_object(html)
    if not isinstance(data, dict):
        return None

    all_overall = data.get("overall") if isinstance(data.get("overall"), dict) else {}
    by_date = data.get("by_date") if isinstance(data.get("by_date"), dict) else {}
    filtered_by_date = _filter_date_map(by_date, start_date, end_date)
    overall = _overall_for_date_range(data, all_overall, filtered_by_date) if (start_date or end_date) else all_overall
    by_primary_scenario = _scenario_summary_for_date_range(
        data.get("by_date_primary_scenario") if isinstance(data.get("by_date_primary_scenario"), dict) else {},
        data.get("by_primary_scenario") if isinstance(data.get("by_primary_scenario"), dict) else {},
        start_date,
        end_date,
    )
    by_scenario = _scenario_summary_for_date_range(
        data.get("by_date_scenario") if isinstance(data.get("by_date_scenario"), dict) else {},
        data.get("by_scenario") if isinstance(data.get("by_scenario"), dict) else {},
        start_date,
        end_date,
    )
    by_city = data.get("by_city") if isinstance(data.get("by_city"), dict) else {}
    by_vehicle = data.get("by_vehicle") if isinstance(data.get("by_vehicle"), dict) else {}
    qc_by_vehicle = data.get("qc_by_vehicle") if isinstance(data.get("qc_by_vehicle"), dict) else {}
    diagnostics = []
    if start_date or end_date:
        diagnostics.append(
            {
                "code": "dashboard_date_filter_applied",
                "level": "info",
                "message": "KPI and scene summaries were aggregated from date-level dashboard data.",
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        diagnostics.append(
            {
                "code": "dashboard_vehicle_tables_snapshot_scope",
                "level": "info",
                "message": "Vehicle collection and vehicle quality tables do not expose date-level rows in overview_live.html and remain dashboard snapshot tables.",
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    return {
        "kpis": _embedded_kpis(overall, filtered_by_date if (start_date or end_date) else by_date),
        "scene_summary": _embedded_scene_options(overall, by_primary_scenario, by_scenario),
        "primary_scene_summary": _summary_rows(by_primary_scenario, "primary_scene"),
        "city_summary": _summary_rows(by_city, "city"),
        "vehicle_collection_summary": _embedded_vehicle_collection_rows(by_vehicle),
        "vehicle_quality_summary": _embedded_vehicle_quality_rows(qc_by_vehicle),
        "date_filter": {
            "start_date": start_date,
            "end_date": end_date,
            "kpi_scope": "date_filtered" if (start_date or end_date) else "dashboard_snapshot",
            "vehicle_table_scope": "dashboard_snapshot",
            "quality_table_scope": "dashboard_snapshot",
        },
        "tables": [],
        "diagnostics": diagnostics,
    }


def _extract_embedded_data_object(html: str) -> dict[str, object] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\b(?:let|const|var)\s+DATA\s*=", html):
        object_start = html.find("{", match.end())
        if object_start < 0:
            continue
        try:
            value, _ = decoder.raw_decode(html[object_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _filter_date_map(items: dict[str, object], start_date: str | None, end_date: str | None) -> dict[str, object]:
    if not start_date and not end_date:
        return items
    result: dict[str, object] = {}
    for date_key, value in items.items():
        date_text = str(date_key)
        if start_date and date_text < start_date:
            continue
        if end_date and date_text > end_date:
            continue
        result[date_text] = value
    return result


def _overall_for_date_range(
    data: dict[str, object],
    fallback_overall: dict[str, object],
    filtered_by_date: dict[str, object],
) -> dict[str, object]:
    total_count = 0.0
    total_bos = 0.0
    total_records = 0.0
    total_mileage = 0.0
    total_intersections = 0.0
    has_records = False
    has_intersections = False
    for item in filtered_by_date.values():
        if not isinstance(item, dict):
            continue
        total_count += _number(item.get("count"))
        total_bos += _number(item.get("on_bos"))
        total_mileage += _number(item.get("mileage"))
        if item.get("records") is not None:
            total_records += _number(item.get("records"))
            has_records = True
        if item.get("intersections") is not None:
            total_intersections += _number(item.get("intersections"))
            has_intersections = True

    overall = dict(fallback_overall)
    overall["total_collections"] = total_count
    overall["on_bos"] = total_bos
    overall["total_mileage"] = round(total_mileage, 2)
    overall["bos_rate"] = round(_safe_divide(total_bos, total_count) * 1000) / 10 if total_count else 0
    if has_records:
        overall["record_files"] = total_records
    if has_intersections:
        overall["total_intersections"] = total_intersections

    qc_by_date = data.get("qc_by_date") if isinstance(data.get("qc_by_date"), dict) else {}
    filtered_qc = _filter_date_map(qc_by_date, min(filtered_by_date.keys(), default=None), max(filtered_by_date.keys(), default=None))
    qc_clips = 0.0
    qc_all_pass = 0.0
    for item in filtered_qc.values():
        if not isinstance(item, dict):
            continue
        qc_clips += _number(item.get("clips"))
        qc_all_pass += _number(item.get("all_pass"))
    if filtered_qc:
        overall["qc_clips"] = qc_clips
        overall["qc_all_pass"] = qc_all_pass
        overall["qc_all_pass_rate"] = round(_safe_divide(qc_all_pass, qc_clips) * 1000) / 10 if qc_clips else 0

    return overall


def _scenario_summary_for_date_range(
    by_date_scenario: dict[str, object],
    fallback: dict[str, object],
    start_date: str | None,
    end_date: str | None,
) -> dict[str, object]:
    if not start_date and not end_date:
        return fallback
    summary: dict[str, dict[str, float]] = {}
    for daily in _filter_date_map(by_date_scenario, start_date, end_date).values():
        if not isinstance(daily, dict):
            continue
        for name, item in daily.items():
            if not isinstance(item, dict):
                continue
            row = summary.setdefault(str(name), {"count": 0, "on_bos": 0, "records": 0, "mileage": 0, "intersections": 0, "vehicles": 0})
            row["count"] += _number(item.get("count"))
            row["on_bos"] += _number(item.get("on_bos"))
            row["records"] += _number(item.get("records"))
            row["mileage"] += _number(item.get("mileage"))
            row["intersections"] += _number(item.get("intersections"))
    return summary


def _embedded_kpis(overall: dict[str, object], by_date: dict[str, object]) -> dict[str, dict[str, str]]:
    total_collections = _number(overall.get("total_collections"))
    on_bos = _number(overall.get("on_bos"))
    record_files = _number(overall.get("record_files"))
    total_mileage = _number(overall.get("total_mileage"))
    qc_clips = _number(overall.get("qc_clips"))
    qc_all_pass = _number(overall.get("qc_all_pass"))
    dates = sorted(str(item) for item in by_date.keys())
    date_range = f"{dates[0]} ~ {dates[-1]}" if dates else "-"
    pending_bos = max(total_collections - on_bos, 0)

    items = [
        ("采集总次数", _format_number(total_collections), date_range),
        ("已入库 BOS", _format_number(on_bos), f"{_format_number(pending_bos)} 待入库"),
        ("入库率", _format_percent(overall.get("bos_rate")), "采集 -> BOS"),
        ("Record 文件", _format_number(record_files), f"平均 {_safe_divide(record_files, on_bos):.1f} 个/次"),
        ("总里程", f"{_format_number(total_mileage)} km", f"平均 {_safe_divide(total_mileage, total_collections):.1f} km/次"),
        ("车辆数", _format_number(overall.get("vehicles")), "参与采集车辆"),
        ("城市数", _format_number(overall.get("cities")), "城市分布"),
        ("场景数", _format_number(overall.get("scenarios")), f"一级场景 {_format_number(overall.get('primary_scenarios'))}"),
        ("质检通过率", _format_percent(overall.get("qc_all_pass_rate")), f"{_format_number(qc_all_pass)} / {_format_number(qc_clips)} clips"),
    ]
    return {
        label: {"label": label, "value": value, "sub": sub, "allText": "\n".join([label, value, sub])}
        for label, value, sub in items
    }


def _embedded_scene_options(
    overall: dict[str, object],
    by_primary_scenario: dict[str, object],
    by_scenario: dict[str, object],
) -> list[dict[str, str]]:
    options = [
        {
            "value": "all",
            "text": f"全部场景 ({_format_number(overall.get('total_collections'))})",
            "level": "all",
            "count": _format_number(overall.get("total_collections")),
        }
    ]
    for name, item in _sorted_summary_items(by_primary_scenario):
        count = _number(item.get("count") if isinstance(item, dict) else 0)
        options.append(
            {
                "value": f"p:{name}",
                "text": f"[一级] {name} ({_format_number(count)})",
                "level": "primary",
                "count": _format_number(count),
            }
        )
    for name, item in _sorted_summary_items(by_scenario):
        count = _number(item.get("count") if isinstance(item, dict) else 0)
        options.append(
            {
                "value": name,
                "text": f"{name} ({_format_number(count)})",
                "level": "secondary",
                "count": _format_number(count),
            }
        )
    return options


def _summary_rows(items: dict[str, object], label_key: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, item in _sorted_summary_items(items):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                label_key: name,
                "采集": _format_number(item.get("count")),
                "入库": _format_number(item.get("on_bos")),
                "Records": _format_number(item.get("records")),
                "入库率": _format_percent(_safe_divide(_number(item.get("on_bos")), _number(item.get("count"))) * 100),
                "里程": _format_number(item.get("mileage")),
                "车辆数": _format_number(item.get("vehicles")),
            }
        )
    return rows


def _embedded_vehicle_collection_rows(by_vehicle: dict[str, object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for vehicle, item in _sorted_summary_items(by_vehicle):
        if not isinstance(item, dict):
            continue
        count = _number(item.get("count"))
        on_bos = _number(item.get("on_bos"))
        storage_rate = round(_safe_divide(on_bos, count) * 100)
        rows.append(
            {
                "车辆": vehicle,
                "城市": str(item.get("city") or ""),
                "场景": str(item.get("scenario") or ""),
                "采集": _format_number(count),
                "入库": _format_number(on_bos),
                "Records": _format_number(item.get("records")),
                "入库率": f"{storage_rate:g}%",
                "里程": _format_number(item.get("mileage")),
            }
        )
    return rows


def _embedded_vehicle_quality_rows(qc_by_vehicle: dict[str, object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for vehicle, item in qc_by_vehicle.items():
        if not isinstance(item, dict):
            continue
        clips = _number(item.get("clips"))
        all_fail = max(clips - _number(item.get("all_pass")), 0)
        fail_rate = round(_safe_divide(all_fail, clips) * 1000) / 10
        row = {
            "车辆": str(vehicle),
            "总 Clips": _format_number(clips),
            "不通过率": f"{fail_rate:g}%",
            "不通过数": _format_number(all_fail),
        }
        for code in ("loss_camera_sensor", "pcd_loss", "seq_frame_interval_too_large", "camera_interval_too_large"):
            fail_count = max(clips - _number(item.get(code)), 0)
            fail_pct = round(_safe_divide(fail_count, clips) * 1000) / 10
            row[code] = f"{_format_number(fail_count)} ({fail_pct:g}%)"
        rows.append(row)
    rows.sort(key=lambda item: _number(item.get("不通过率")), reverse=True)
    return rows


def _sorted_summary_items(items: dict[str, object]) -> list[tuple[str, object]]:
    return sorted(
        ((str(key), value) for key, value in items.items()),
        key=lambda pair: _number(pair[1].get("count") if isinstance(pair[1], dict) else 0),
        reverse=True,
    )


def _has_dashboard_payload(overview: dict[str, object]) -> bool:
    return any(
        overview.get(key)
        for key in ("kpis", "scene_summary", "vehicle_collection_summary", "vehicle_quality_summary")
    )


class _DashboardOverviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[dict[str, object]] = []
        self._current_kpi: dict[str, str] | None = None
        self._current_kpi_field: str | None = None
        self._current_option: dict[str, str] | None = None
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self.kpis: dict[str, dict[str, str]] = {}
        self.scene_options: list[dict[str, str]] = []
        self.tables: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        self._stack.append({"tag": tag, "classes": classes})

        if "kpi-card" in classes:
            self._current_kpi = {"label": "", "value": "", "sub": ""}
        elif self._current_kpi is not None:
            if "kpi-label" in classes:
                self._current_kpi_field = "label"
            elif "kpi-value" in classes:
                self._current_kpi_field = "value"
            elif "kpi-sub" in classes:
                self._current_kpi_field = "sub"

        if tag == "option":
            self._current_option = {"value": attr_map.get("value", ""), "text": ""}
        elif tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"th", "td"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        text = _normalize_text(data)
        if not text:
            return

        if self._current_kpi is not None and self._current_kpi_field:
            existing = self._current_kpi.get(self._current_kpi_field, "")
            self._current_kpi[self._current_kpi_field] = _join_text(existing, text)
        if self._current_option is not None:
            self._current_option["text"] = _join_text(self._current_option["text"], text)
        if self._current_cell is not None:
            self._current_cell.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(_normalize_text(" ".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            self.tables.append({"rows": self._current_table})
            self._current_table = None
        elif tag == "option" and self._current_option is not None:
            if self._current_option["text"]:
                self.scene_options.append(self._current_option)
            self._current_option = None
        elif tag == "div" and self._current_kpi is not None:
            if self._stack and "kpi-card" in self._stack[-1].get("classes", set()):
                label = self._current_kpi.get("label", "")
                if label:
                    all_text = "\n".join(
                        item for item in (self._current_kpi.get("label"), self._current_kpi.get("value"), self._current_kpi.get("sub")) if item
                    )
                    self.kpis[label] = {**self._current_kpi, "allText": all_text}
                self._current_kpi = None
            self._current_kpi_field = None

        if self._stack:
            self._stack.pop()


def _row_to_dict(header: list[str], row: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for index, name in enumerate(header):
        key = name or f"col_{index + 1}"
        result[key] = row[index] if index < len(row) else ""
    return result


def _empty_overview() -> dict[str, object]:
    return {
        "kpis": {},
        "scene_summary": [],
        "primary_scene_summary": [],
        "city_summary": [],
        "vehicle_collection_summary": [],
        "vehicle_quality_summary": [],
        "date_filter": {},
        "tables": [],
        "diagnostics": [],
    }


def _merge_overview(base: dict[str, object], item: dict[str, object]) -> dict[str, object]:
    return {
        "kpis": {**dict(base.get("kpis", {})), **dict(item.get("kpis", {}))},
        "scene_summary": [*list(base.get("scene_summary", [])), *list(item.get("scene_summary", []))],
        "primary_scene_summary": [
            *list(base.get("primary_scene_summary", [])),
            *list(item.get("primary_scene_summary", [])),
        ],
        "city_summary": [*list(base.get("city_summary", [])), *list(item.get("city_summary", []))],
        "vehicle_collection_summary": [
            *list(base.get("vehicle_collection_summary", [])),
            *list(item.get("vehicle_collection_summary", [])),
        ],
        "vehicle_quality_summary": [
            *list(base.get("vehicle_quality_summary", [])),
            *list(item.get("vehicle_quality_summary", [])),
        ],
        "date_filter": dict(item.get("date_filter") or base.get("date_filter") or {}),
        "tables": [*list(base.get("tables", [])), *list(item.get("tables", []))],
        "diagnostics": [*list(base.get("diagnostics", [])), *list(item.get("diagnostics", []))],
    }


def _fetch_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": "data-analyst-agent/weekly-resource-report"})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def _base_manifest(source: DashboardSourceConfig) -> dict[str, object]:
    return {
        "source_id": source.id,
        "source_type": source.source_type,
        "original_url": source.url,
        "role": source.role,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _join_text(left: str, right: str) -> str:
    if not left:
        return right
    return f"{left} {right}"


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "")
    match = re.search(r"-?[\d,]+(?:\.\d+)?", text)
    if not match:
        return 0.0
    return float(match.group(0).replace(",", ""))


def _format_number(value: object) -> str:
    number = _number(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _format_percent(value: object) -> str:
    number = _number(value)
    if number.is_integer():
        return f"{int(number)}%"
    return f"{number:g}%"


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
