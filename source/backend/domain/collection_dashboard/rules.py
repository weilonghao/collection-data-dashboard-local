"""Deterministic rules for the collection data dashboard."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from domain.weekly_report.rules import attach_week_over_week_comparison, parse_weekly_records, summarize_weekly_records

STATUS_PRIORITY = {"active": 4, "abnormal": 3, "idle": 2, "unknown": 1}
STATUS_LABELS = {"active": "活跃", "abnormal": "异常", "idle": "空闲", "unknown": "未知"}
IGNORED_NOTE_COLUMNS = ("出车异常记录", "数采问题记录")
ABNORMAL_KEYWORDS = ("扣车", "维修", "事故", "拖车", "下发失败", "接车网卡", "车没电")


def build_collection_dashboard(
    raw_paths: Iterable[str | Path],
    *,
    anchor_date: date | str | None = None,
    generated_at: str | None = None,
    source_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a multi-period collection dashboard from raw Feishu exports."""
    paths = [Path(path) for path in raw_paths]
    metadata_by_source = source_metadata or {}
    collection_paths = [
        path
        for path in paths
        if _source_metadata(path, metadata_by_source).get("parser") in {"", "collection_detail"}
    ]
    records, diagnostics = parse_weekly_records(collection_paths)
    records = [_enrich_record(record, _source_metadata(str(record.get("source") or ""), metadata_by_source)) for record in records]

    vehicle_rows: list[dict[str, Any]] = []
    resource_schedule_records: list[dict[str, Any]] = []
    collection_output_records: list[dict[str, Any]] = []
    for path in paths:
        source_name = _source_name(path)
        metadata = _source_metadata(path, metadata_by_source)
        parser = str(metadata.get("parser") or "collection_detail")
        csv_text = path.read_text(encoding="utf-8-sig")
        if parser == "human_driving_output":
            output_rows = parse_human_driving_output_records(csv_text, source_name, metadata=metadata)
            collection_output_records.extend(output_rows)
            records.extend(_output_rows_to_attendance_records(output_rows))
            continue

        parsed_vehicle_rows = parse_vehicle_status_rows(csv_text, source_name, metadata=metadata)
        vehicle_rows.extend(parsed_vehicle_rows)
        schedule_rows = _vehicle_rows_to_resource_schedule_records(parsed_vehicle_rows)
        resource_schedule_records.extend(schedule_rows)
        if parser == "human_driving_schedule":
            records.extend(_schedule_rows_to_attendance_records(schedule_rows))

    vehicle_daily_status = dedupe_vehicle_daily_status(vehicle_rows)
    vehicle_daily_summary = summarize_vehicle_daily_status(vehicle_daily_status)
    resolved_anchor = _resolve_anchor_date([*records, *collection_output_records], vehicle_daily_status, anchor_date)
    period_views = {
        grain: _build_period_view(records, vehicle_daily_status, grain, resolved_anchor)
        for grain in ("day", "week", "month", "year")
    }

    return {
        "dashboard_id": "collection_data_dashboard",
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "anchor_date": resolved_anchor.isoformat() if resolved_anchor else None,
        "source_files": [_source_file_info(path) for path in paths],
        "record_count": len(records),
        "vehicle_row_count": len(vehicle_rows),
        "vehicle_daily_status_count": len(vehicle_daily_status),
        "records": records,
        "resource_schedule_records": resource_schedule_records,
        "collection_output_records": collection_output_records,
        "vehicle_daily_status": vehicle_daily_status,
        "vehicle_daily_summary": vehicle_daily_summary,
        "vehicle_status_summary_by_date": {item["date"]: item for item in vehicle_daily_summary},
        "period_views": period_views,
        "diagnostics": diagnostics,
        "diagnostics_count": len(diagnostics),
        "vehicle_status_rules": {
            "status_priority": ["active", "abnormal", "idle", "unknown"],
            "ignored_status_columns": list(IGNORED_NOTE_COLUMNS),
            "abnormal_keywords": list(ABNORMAL_KEYWORDS),
            "active_rule": "date + car_number has a valid assigned driver",
        },
    }


def parse_vehicle_status_rows(
    csv_text: str,
    source_name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse every vehicle row, including idle/abnormal rows that weekly records skip."""
    metadata = _normalized_source_metadata(source_name, metadata)
    rows = _parse_csv_text(csv_text)
    if len(rows) < 2:
        return []

    header_index = _find_header_row(rows, ["车号"])
    if header_index < 0:
        return []

    headers = rows[header_index]
    col_date = _find_col(headers, ["时间"])
    task_columns = _find_task_columns(headers)
    col_shift = _find_col(headers, ["班次"])
    col_sensor = _find_col(headers, ["传感器"])
    col_car = _find_col(headers, ["车号"])
    col_driver = _find_col(headers, ["出车人SD", "出车人"])
    col_departure = _find_col(headers, ["出车时间"])
    col_total = _find_col(headers, ["采集总容量"])
    col_effective = _find_col(headers, ["有效采集时间"])
    ignored_cols = [(name, _find_col(headers, [name])) for name in IGNORED_NOTE_COLUMNS]

    current_date: tuple[int, int, int] | None = None
    current_tasks: dict[str, str | None] = {"default": None, "white": None, "night": None}
    parsed: list[dict[str, Any]] = []

    for row_index in range(header_index + 1, len(rows)):
        cells = rows[row_index]
        if not cells or all(not str(cell).strip() for cell in cells):
            continue

        date_parts = _parse_date(_get_cell(cells, col_date))
        if date_parts:
            current_date = date_parts
            current_tasks = {"default": None, "white": None, "night": None}
        if not current_date:
            continue

        _update_current_tasks(cells, task_columns, current_tasks)

        car_number = _get_cell(cells, col_car)
        if not _is_valid_vehicle(car_number):
            continue

        shift_table = _get_cell(cells, col_shift)
        raw_driver = _get_cell(cells, col_driver)
        driver_names = _valid_driver_names(raw_driver)
        departure_time = _get_cell(cells, col_departure)
        total_collection = _get_cell(cells, col_total)
        effective_time = _get_cell(cells, col_effective)
        ignored_notes = {
            name: _get_cell(cells, col)
            for name, col in ignored_cols
            if col >= 0 and _get_cell(cells, col)
        }
        status, reason = _classify_vehicle_status(
            raw_driver=raw_driver,
            driver_names=driver_names,
            departure_time=departure_time,
            total_collection=total_collection,
            effective_time=effective_time,
        )
        parsed.append(
            {
                "date": _format_date_parts(current_date),
                "department": metadata["department"],
                "site": metadata["site"],
                "source_role": metadata["source_role"],
                "parser": metadata["parser"],
                "car_number": car_number,
                "source": source_name,
                "source_line": row_index + 1,
                "row_index": row_index,
                "task": _task_for_shift(current_tasks, shift_table) or "未知任务",
                "shift_table": shift_table,
                "sensor": _get_cell(cells, col_sensor),
                "raw_driver": raw_driver,
                "drivers": driver_names,
                "departure_time": departure_time,
                "total_collection_raw": total_collection,
                "effective_time_raw": effective_time,
                "ignored_notes": ignored_notes,
                "ignored_note_columns": sorted(ignored_notes),
                "status": status,
                "status_label": STATUS_LABELS[status],
                "status_reason": reason,
            }
        )
    return parsed


def dedupe_vehicle_daily_status(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse row-level vehicle status into one status per date + vehicle."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(
            row.get("department") or "",
            row.get("site") or "",
            row.get("date") or "",
            row.get("car_number") or "",
        )].append(row)

    daily: list[dict[str, Any]] = []
    for (_department, _site, date_text, car_number), items in grouped.items():
        ordered = sorted(items, key=lambda item: (-STATUS_PRIORITY.get(str(item.get("status")), 0), int(item.get("source_line") or 0)))
        selected = ordered[0]
        drivers = sorted({driver for item in items for driver in item.get("drivers", [])})
        ignored_note_columns = sorted({column for item in items for column in item.get("ignored_note_columns", [])})
        reasons = [str(item.get("status_reason") or "") for item in items if item.get("status") == selected.get("status") and item.get("status_reason")]
        daily.append(
            {
                "date": date_text,
                "department": selected.get("department") or "数采",
                "site": selected.get("site") or "",
                "source_role": selected.get("source_role") or "",
                "parser": selected.get("parser") or "",
                "car_number": car_number,
                "status": selected.get("status"),
                "status_label": selected.get("status_label"),
                "status_reason": "；".join(dict.fromkeys(reasons)) or selected.get("status_reason") or "",
                "drivers": drivers,
                "tasks": sorted({str(item.get("task") or "") for item in items if item.get("task")}),
                "shift_tables": sorted({str(item.get("shift_table") or "") for item in items if item.get("shift_table")}),
                "sensors": sorted({str(item.get("sensor") or "") for item in items if item.get("sensor")}),
                "sources": sorted({str(item.get("source") or "") for item in items if item.get("source")}),
                "source_lines": [item.get("source_line") for item in items],
                "ignored_note_columns": ignored_note_columns,
                "row_count": len(items),
            }
        )
    daily.sort(key=lambda item: (item["date"], item["car_number"]), reverse=True)
    return daily


def summarize_vehicle_daily_status(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["date"]].append(row)
    summaries = []
    for date_text, items in grouped.items():
        counts = Counter(str(item.get("status") or "unknown") for item in items)
        summaries.append(_vehicle_summary_payload(date_text, items, counts))
    summaries.sort(key=lambda item: item["date"], reverse=True)
    return summaries


def parse_human_driving_output_records(
    csv_text: str,
    source_name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse human-driving trial operation rows into collection output records."""
    metadata = _normalized_source_metadata(source_name, metadata)
    rows = _parse_csv_text(csv_text)
    if len(rows) < 2:
        return []

    headers = rows[0]
    col_taken = _find_col(headers, ["是否已取数"])
    car_cols = _find_cols(headers, ["车号"])
    col_start = _find_col(headers, ["采集开始时间"])
    col_end = _find_col(headers, ["采集结束时间"])
    scene_cols = _find_cols(headers, ["采集场景"])
    col_route = _find_col(headers, ["路线名称", "起点名称"])
    col_mileage = _find_col(headers, ["里程数"])
    col_collector = _find_col(headers, ["采集员"])
    col_note = _find_col(headers, ["异常情况备注"])
    col_date = _find_col(headers, ["日期"])
    col_duration = _find_col(headers, ["时长"])

    parsed: list[dict[str, Any]] = []
    for row_index, cells in enumerate(rows[1:], start=1):
        car_number = next((_get_cell(cells, col) for col in car_cols if _get_cell(cells, col)), "")
        collector = _get_cell(cells, col_collector)
        start_raw = _get_cell(cells, col_start)
        end_raw = _get_cell(cells, col_end)
        if not any((car_number, collector, start_raw, end_raw)):
            continue

        start_dt = _datetime_from_lark_value(start_raw)
        end_dt = _datetime_from_lark_value(end_raw)
        date_text = _date_text_from_any(_get_cell(cells, col_date)) or (
            start_dt.date().isoformat() if start_dt else ""
        )
        if not date_text:
            continue

        scene_values = [_get_cell(cells, col) for col in scene_cols]
        scene = next((value for value in scene_values if value), "")
        route = _get_cell(cells, col_route)
        if not route and len(scene_values) > 1:
            route = next((value for value in scene_values[1:] if value and value != scene), "")
        duration_minutes = _number_or_none(_get_cell(cells, col_duration))
        if duration_minutes is None and start_dt and end_dt:
            duration_minutes = max((end_dt - start_dt).total_seconds() / 60, 0)

        parsed.append(
            {
                "date": date_text,
                "department": metadata["department"],
                "site": metadata["site"],
                "source_role": metadata["source_role"],
                "parser": metadata["parser"],
                "source": source_name,
                "source_line": row_index + 1,
                "car_number": car_number,
                "collector": collector,
                "scene": scene or "未标注场景",
                "route": route,
                "start_time": _format_datetime(start_dt) if start_dt else start_raw,
                "end_time": _format_datetime(end_dt) if end_dt else end_raw,
                "duration_minutes": round(duration_minutes, 2) if duration_minutes is not None else None,
                "mileage_km": _number_or_none(_get_cell(cells, col_mileage)),
                "is_collected": _get_cell(cells, col_taken),
                "exception_note": _get_cell(cells, col_note),
            }
        )
    return parsed


def _vehicle_rows_to_resource_schedule_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "date": row.get("date"),
            "department": row.get("department") or "数采",
            "site": row.get("site") or "",
            "source_role": row.get("source_role") or "resource_schedule",
            "parser": row.get("parser") or "collection_detail",
            "source": row.get("source"),
            "source_line": row.get("source_line"),
            "task": row.get("task"),
            "shift": row.get("shift_table"),
            "car_number": row.get("car_number"),
            "driver": "、".join(row.get("drivers") or []),
            "departure_time": row.get("departure_time"),
            "exception_note": "；".join(str(value) for value in (row.get("ignored_notes") or {}).values() if value),
        }
        for row in rows
    ]


def _schedule_rows_to_attendance_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        driver_text = str(row.get("driver") or "").strip()
        if not driver_text:
            continue
        for driver in [item.strip() for item in re.split(r"[/／、]", driver_text) if item.strip()]:
            records.append(
                {
                    "date": row.get("date"),
                    "location": row.get("site") or row.get("source"),
                    "department": row.get("department") or "人驾",
                    "site": row.get("site") or "",
                    "source_role": row.get("source_role") or "resource_schedule",
                    "parser": row.get("parser") or "human_driving_schedule",
                    "task": row.get("task") or "未标注任务",
                    "shift_table": row.get("shift") or "",
                    "sensor": "",
                    "car_number": row.get("car_number") or "",
                    "driver": driver,
                    "raw_driver": driver_text,
                    "departure_time": row.get("departure_time") or "",
                    "all_departure_times": row.get("departure_time") or "",
                    "shift": _shift_label_from_text(row.get("shift") or row.get("departure_time") or ""),
                    "raw_departure_time": row.get("departure_time") or "",
                    "total_collection": 0.0,
                    "effective_time": 0.0,
                    "source": row.get("source"),
                    "source_line": row.get("source_line") or 0,
                    "row_index": 0,
                    "candidate_index": 0,
                    "driver_col": 0,
                    "time_col": 0,
                }
            )
    return records


def _output_rows_to_attendance_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        collector = str(row.get("collector") or "").strip()
        if not collector:
            continue
        records.append(
            {
                "date": row.get("date"),
                "location": row.get("site") or row.get("source"),
                "department": row.get("department") or "人驾",
                "site": row.get("site") or "",
                "source_role": row.get("source_role") or "collection_output",
                "parser": row.get("parser") or "human_driving_output",
                "task": row.get("scene") or row.get("route") or "未标注场景",
                "shift_table": "",
                "sensor": "",
                "car_number": row.get("car_number") or "",
                "driver": collector,
                "raw_driver": collector,
                "departure_time": str(row.get("start_time") or "")[-5:],
                "all_departure_times": str(row.get("start_time") or "")[-5:],
                "shift": _shift_label_from_text(row.get("start_time") or ""),
                "raw_departure_time": row.get("start_time") or "",
                "total_collection": float(row.get("mileage_km") or 0),
                "effective_time": float(row.get("duration_minutes") or 0) / 60,
                "source": row.get("source"),
                "source_line": row.get("source_line") or 0,
                "row_index": 0,
                "candidate_index": 0,
                "driver_col": 0,
                "time_col": 0,
            }
        )
    return records


def _enrich_record(record: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        **record,
        "department": record.get("department") or metadata["department"],
        "site": record.get("site") or metadata["site"],
        "source_role": record.get("source_role") or metadata["source_role"],
        "parser": record.get("parser") or metadata["parser"],
    }


def _source_metadata(source: str | Path, metadata_by_source: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_name = _source_name(source) if isinstance(source, Path) else str(source)
    return _normalized_source_metadata(source_name, metadata_by_source.get(source_name))


def _normalized_source_metadata(source_name: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    metadata = metadata or {}
    return {
        "source_id": str(metadata.get("source_id") or source_name),
        "department": str(metadata.get("department") or "数采"),
        "site": str(metadata.get("site") or ""),
        "source_role": str(metadata.get("source_role") or "resource_schedule"),
        "parser": str(metadata.get("parser") or "collection_detail"),
        "source_type": str(metadata.get("source_type") or "collection_detail"),
    }


def _shift_label_from_text(value: Any) -> str:
    text = str(value or "")
    if "夜" in text or "night" in text.lower():
        return "夜班"
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if match and int(match.group(1)) >= 18:
        return "夜班"
    return "白班"


def _build_period_view(records: list[dict[str, Any]], vehicle_daily_status: list[dict[str, Any]], grain: str, anchor: date | None) -> dict[str, Any]:
    current_start, current_end = _period_bounds(grain, anchor)
    compare_start, compare_end = _previous_period_bounds(grain, current_start, current_end)
    current_report = _period_report(records, current_start, current_end, f"{grain}-current")
    previous_report = _period_report(records, compare_start, compare_end, f"{grain}-previous")
    history_report = _period_report(records, current_start - timedelta(days=28), current_start - timedelta(days=1), f"{grain}-history")
    rolling_report = _period_report(records, current_start - timedelta(days=21), current_end, f"{grain}-rolling")
    attach_week_over_week_comparison(current_report, previous_report, history_report=history_report, rolling_report=rolling_report)

    current_vehicle = _aggregate_vehicle_period(vehicle_daily_status, current_start, current_end)
    previous_vehicle = _aggregate_vehicle_period(vehicle_daily_status, compare_start, compare_end)
    metrics = _period_metrics(current_report, current_vehicle)
    previous_metrics = _period_metrics(previous_report, previous_vehicle)
    return {
        "grain": grain,
        "label": {"day": "日", "week": "周", "month": "月", "year": "年"}[grain],
        "current_period": {"start_date": current_start.isoformat(), "end_date": current_end.isoformat()},
        "compare_period": {"start_date": compare_start.isoformat(), "end_date": compare_end.isoformat()},
        "metrics": metrics,
        "comparison": _compare_metrics(metrics, previous_metrics),
        "top5_tasks": (current_report.get("focus_summary") or {}).get("top5_tasks") or [],
        "personnel_stability": (current_report.get("focus_summary") or {}).get("top_task_personnel_stability") or [],
        "vehicle_status": current_vehicle,
    }


def _period_report(records: list[dict[str, Any]], start: date, end: date, report_id: str) -> dict[str, Any]:
    report = summarize_weekly_records(records, start_date=start, end_date=end)
    report["week_id"] = report_id
    report["period"] = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    return report


def _period_metrics(report: dict[str, Any], vehicle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    kpis = report.get("kpis") or {}
    focus = report.get("focus_summary") or {}
    overview = focus.get("scheduling_control_overview") or {}
    return {
        "active_people": {"name": "参与人数", "value": int(kpis.get("unique_drivers") or 0), "display_value": str(int(kpis.get("unique_drivers") or 0))},
        "attendance_count": {"name": "出勤人次", "value": int(kpis.get("total_attendance") or 0), "display_value": str(int(kpis.get("total_attendance") or 0))},
        "white_attendance": {"name": "白班人次", "value": int(kpis.get("white_attendance") or 0), "display_value": str(int(kpis.get("white_attendance") or 0))},
        "night_attendance": {"name": "夜班人次", "value": int(kpis.get("night_attendance") or 0), "display_value": str(int(kpis.get("night_attendance") or 0))},
        "sd_per_day": {"name": "SD 个数/天", "value": float(kpis.get("avg_daily_sd") or 0), "display_value": _fmt_number(kpis.get("avg_daily_sd") or 0)},
        "stable_participant_coverage": {
            "name": "稳定参与者覆盖率",
            "value": float(overview.get("stable_candidate_coverage") or 0),
            "display_value": _fmt_pct(overview.get("stable_candidate_coverage") or 0),
        },
        "top_task_count": {"name": "Top5 任务数", "value": len((focus.get("top5_tasks") or [])[:5]), "display_value": str(len((focus.get("top5_tasks") or [])[:5]))},
        "task_types": {"name": "任务类型数", "value": int(kpis.get("task_types") or 0), "display_value": str(int(kpis.get("task_types") or 0))},
        "vehicle_count": {"name": "车辆总数", "value": vehicle["vehicle_count"], "display_value": str(vehicle["vehicle_count"])},
        "vehicle_active_count": {"name": "活跃车辆", "value": vehicle["active_count"], "display_value": str(vehicle["active_count"])},
        "vehicle_idle_count": {"name": "空闲车辆", "value": vehicle["idle_count"], "display_value": str(vehicle["idle_count"])},
        "vehicle_abnormal_count": {"name": "异常车辆", "value": vehicle["abnormal_count"], "display_value": str(vehicle["abnormal_count"])},
        "vehicle_unknown_count": {"name": "未知车辆", "value": vehicle["unknown_count"], "display_value": str(vehicle["unknown_count"])},
    }


def _compare_metrics(current: dict[str, dict[str, Any]], previous: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    comparison = {}
    for metric_id, metric in current.items():
        current_value = float(metric.get("value") or 0)
        previous_value = float((previous.get(metric_id) or {}).get("value") or 0)
        delta = current_value - previous_value
        comparison[metric_id] = {
            "name": metric.get("name"),
            "current_value": current_value,
            "compare_value": previous_value,
            "delta": round(delta, 4),
            "delta_pct": round(delta / previous_value, 4) if previous_value else None,
            "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
        }
    return comparison


def _aggregate_vehicle_period(rows: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    filtered = [row for row in rows if start.isoformat() <= row.get("date", "") <= end.isoformat()]
    counts = Counter(str(row.get("status") or "unknown") for row in filtered)
    vehicles = sorted({str(row.get("car_number") or "") for row in filtered if row.get("car_number")})
    return {
        "vehicle_count": len(vehicles),
        "vehicle_day_count": len(filtered),
        "active_count": counts.get("active", 0),
        "idle_count": counts.get("idle", 0),
        "abnormal_count": counts.get("abnormal", 0),
        "unknown_count": counts.get("unknown", 0),
        "abnormal_items": [row for row in filtered if row.get("status") == "abnormal"][:20],
    }


def _vehicle_summary_payload(date_text: str, items: list[dict[str, Any]], counts: Counter[str]) -> dict[str, Any]:
    return {
        "date": date_text,
        "vehicle_count": len(items),
        "active_count": counts.get("active", 0),
        "idle_count": counts.get("idle", 0),
        "abnormal_count": counts.get("abnormal", 0),
        "unknown_count": counts.get("unknown", 0),
        "active_vehicles": sorted(item["car_number"] for item in items if item.get("status") == "active"),
        "idle_vehicles": sorted(item["car_number"] for item in items if item.get("status") == "idle"),
        "abnormal_vehicles": sorted(item["car_number"] for item in items if item.get("status") == "abnormal"),
        "unknown_vehicles": sorted(item["car_number"] for item in items if item.get("status") == "unknown"),
    }


def _classify_vehicle_status(
    *,
    raw_driver: str,
    driver_names: list[str],
    departure_time: str,
    total_collection: str,
    effective_time: str,
) -> tuple[str, str]:
    if driver_names:
        return "active", "安排司机：" + "、".join(driver_names)
    if raw_driver.strip():
        return "abnormal", raw_driver.strip()
    if departure_time.strip() or total_collection.strip() or effective_time.strip():
        return "unknown", "缺少有效司机但存在时间或产出字段"
    return "idle", "未安排司机"


def _valid_driver_names(raw_driver: str) -> list[str]:
    names = [name.strip().replace(" ", "") for name in re.split(r"[/／]", str(raw_driver or "")) if name.strip()]
    if not names:
        return []
    if all(re.fullmatch(r"[\u4e00-\u9fff]{2,5}", name) for name in names):
        return names
    return []


def _resolve_anchor_date(records: list[dict[str, Any]], vehicle_rows: list[dict[str, Any]], anchor_date: date | str | None) -> date | None:
    if isinstance(anchor_date, date):
        return anchor_date
    if anchor_date:
        return date.fromisoformat(str(anchor_date))
    today = date.today()
    dates = sorted(
        {
            date.fromisoformat(str(item.get("date")))
            for item in [*records, *vehicle_rows]
            if item.get("date") and str(item.get("date")) <= today.isoformat()
        }
    )
    if dates:
        return dates[-1]
    all_dates = sorted(
        {
            date.fromisoformat(str(item.get("date")))
            for item in [*records, *vehicle_rows]
            if item.get("date")
        }
    )
    return all_dates[-1] if all_dates else today


def _period_bounds(grain: str, anchor: date | None) -> tuple[date, date]:
    anchor = anchor or date.today()
    if grain == "day":
        return anchor, anchor
    if grain == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, anchor
    if grain == "month":
        return date(anchor.year, anchor.month, 1), anchor
    if grain == "year":
        return date(anchor.year, 1, 1), anchor
    raise ValueError(f"Unsupported period grain: {grain}")


def _previous_period_bounds(grain: str, start: date, end: date) -> tuple[date, date]:
    length = (end - start).days
    if grain in {"day", "week"}:
        previous_end = start - timedelta(days=1)
        return previous_end - timedelta(days=length), previous_end
    if grain == "month":
        previous_month_last = start - timedelta(days=1)
        previous_start = date(previous_month_last.year, previous_month_last.month, 1)
        return previous_start, min(previous_start + timedelta(days=length), previous_month_last)
    if grain == "year":
        previous_start = date(start.year - 1, 1, 1)
        return previous_start, previous_start + timedelta(days=length)
    raise ValueError(f"Unsupported period grain: {grain}")


def _parse_csv_text(text: str) -> list[list[str]]:
    return [[str(cell).strip() for cell in row] for row in csv.reader(text.splitlines()) if any(str(cell).strip() for cell in row)]


def _find_header_row(rows: list[list[str]], required_names: list[str]) -> int:
    for index, row in enumerate(rows[:5]):
        if all(_find_col(row, [name]) >= 0 for name in required_names):
            return index
    return -1


def _find_col(headers: list[str], names: list[str]) -> int:
    for index, header in enumerate(headers):
        normalized = re.sub(r"\s+", "", str(header or ""))
        if any(name.replace("\n", "") in normalized for name in names):
            return index
    return -1


def _find_cols(headers: list[str], names: list[str]) -> list[int]:
    columns: list[int] = []
    for index, header in enumerate(headers):
        normalized = re.sub(r"\s+", "", str(header or ""))
        if any(name.replace("\n", "") in normalized for name in names):
            columns.append(index)
    return columns


def _find_task_columns(headers: list[str]) -> dict[str, int]:
    """Find legacy and split day/night collection-task columns."""
    columns = {"default": -1, "white": -1, "night": -1}
    for index, header in enumerate(headers):
        normalized = re.sub(r"\s+", "", str(header or "").replace("\n", ""))
        if "采集任务" not in normalized:
            continue
        if "白班" in normalized:
            columns["white"] = index
        elif "夜班" in normalized:
            columns["night"] = index
        elif columns["default"] < 0:
            columns["default"] = index
    return columns


def _update_current_tasks(cells: list[str], columns: dict[str, int], current_tasks: dict[str, str | None]) -> None:
    for key in ("default", "white", "night"):
        value = _get_cell(cells, columns.get(key, -1))
        if value:
            current_tasks[key] = value


def _task_for_shift(current_tasks: dict[str, str | None], shift_text: str) -> str | None:
    shift_key = _shift_key_from_text(shift_text)
    if shift_key and current_tasks.get(shift_key):
        return current_tasks[shift_key]
    return current_tasks.get("default") or current_tasks.get("white") or current_tasks.get("night")


def _shift_key_from_text(value: str) -> str | None:
    text = str(value or "").strip().lower()
    if "夜" in text or "night" in text:
        return "night"
    if "白" in text or "day" in text or "white" in text:
        return "white"
    return None


def _get_cell(cells: list[str], col: int) -> str:
    if col < 0 or col >= len(cells):
        return ""
    return str(cells[col] or "").strip()


def _parse_date(value: str) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", text)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    parsed = _date_from_lark_serial(text)
    if parsed:
        return parsed.year, parsed.month, parsed.day
    return None


def _date_text_from_any(value: Any) -> str:
    date_parts = _parse_date(str(value or ""))
    return _format_date_parts(date_parts) if date_parts else ""


def _date_from_lark_serial(value: Any) -> date | None:
    number = _number_or_none(value)
    if number is None or number < 20000:
        return None
    return (date(1899, 12, 30) + timedelta(days=int(number)))


def _datetime_from_lark_value(value: Any) -> datetime | None:
    text = str(value or "").strip()
    number = _number_or_none(text)
    if number is not None and number >= 20000:
        base = datetime(1899, 12, 30)
        return base + timedelta(days=number)
    match = re.match(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", text)
    if not match:
        return None
    return datetime(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        int(match.group(4) or 0),
        int(match.group(5) or 0),
    )


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _number_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text.startswith("=") or text.upper().startswith("IF"):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _format_date_parts(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"


def _is_valid_vehicle(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text and text != "车号")


def _source_name(path: Path) -> str:
    return path.stem


def _source_file_info(path: Path) -> dict[str, Any]:
    return {"name": path.name, "path": path.as_posix(), "size_bytes": path.stat().st_size if path.exists() else 0}


def _fmt_number(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"
