"""Self-contained local HTML app for the collection data dashboard."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date as date_cls, datetime, timedelta
from html import escape
from typing import Any


def build_collection_frontend_payload(
    dashboard: dict[str, Any],
    *,
    weekly_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the compact payload used by the file:// friendly dashboard."""
    records = list(dashboard.get("records") or [])
    collection_records = [record for record in records if _is_collection_detail(record)]
    daily_attendance = build_daily_attendance_summary(collection_records)
    task_units = build_task_attendance_units(collection_records)
    resource_schedule_records = list(dashboard.get("resource_schedule_records") or [])
    collection_output_records = list(dashboard.get("collection_output_records") or [])
    vehicle_daily_status = list(dashboard.get("vehicle_daily_status") or [])
    dispatch_vehicle_daily_status = [row for row in vehicle_daily_status if _is_collection_detail(row)]
    human_dispatch_vehicle_daily_status = [row for row in vehicle_daily_status if _is_human_schedule(row)]
    human_dispatch_schedule_records = [row for row in resource_schedule_records if _is_human_schedule(row)]
    human_dispatch_output_records = [row for row in collection_output_records if _is_human_output(row)]
    human_dispatch_risks = build_human_dispatch_risks(
        human_dispatch_schedule_records,
        human_dispatch_output_records,
    )
    dates = sorted(
        {
            str(item.get("date"))
            for item in [
                *daily_attendance,
                *vehicle_daily_status,
                *resource_schedule_records,
                *collection_output_records,
            ]
            if item.get("date")
        }
    )
    anchor_date = str(dashboard.get("anchor_date") or (dates[-1] if dates else ""))
    weekly_summary = build_weekly_report_summary(weekly_report)
    weekly_reports = build_weekly_reports(
        daily_attendance,
        task_units,
        list(dashboard.get("vehicle_daily_status") or []),
        weekly_summary=weekly_summary,
    )
    return {
        "dashboard_id": dashboard.get("dashboard_id") or "collection_data_dashboard",
        "generated_at": dashboard.get("generated_at"),
        "anchor_date": anchor_date,
        "record_count": dashboard.get("record_count", 0),
        "date_bounds": {
            "min": dates[0] if dates else anchor_date,
            "max": dates[-1] if dates else anchor_date,
        },
        "dispatch_date_bounds": _date_bounds(dispatch_vehicle_daily_status),
        "human_dispatch_date_bounds": _date_bounds(
            [*human_dispatch_schedule_records, *human_dispatch_output_records, *human_dispatch_vehicle_daily_status]
        ),
        "daily_attendance_summary": daily_attendance,
        "task_attendance_units": task_units,
        "resource_schedule_records": resource_schedule_records,
        "collection_output_records": collection_output_records,
        "vehicle_daily_status": vehicle_daily_status,
        "dispatch_vehicle_daily_status": dispatch_vehicle_daily_status,
        "human_dispatch_vehicle_daily_status": human_dispatch_vehicle_daily_status,
        "human_dispatch_schedule_records": human_dispatch_schedule_records,
        "human_dispatch_output_records": human_dispatch_output_records,
        "human_dispatch_summary": build_human_dispatch_summary(
            human_dispatch_schedule_records,
            human_dispatch_output_records,
            human_dispatch_vehicle_daily_status,
            human_dispatch_risks,
        ),
        "human_dispatch_daily_series": build_human_dispatch_daily_series(
            human_dispatch_schedule_records,
            human_dispatch_output_records,
            human_dispatch_vehicle_daily_status,
        ),
        "human_dispatch_task_rankings": build_human_dispatch_task_rankings(human_dispatch_schedule_records),
        "human_dispatch_output_rankings": build_human_dispatch_output_rankings(human_dispatch_output_records),
        "human_dispatch_risks": human_dispatch_risks,
        "dashboard_overview": dashboard.get("dashboard_overview") or {},
        "diagnostics": [
            *list(dashboard.get("diagnostics") or []),
            *list(dashboard.get("metric_diagnostics") or []),
        ],
        "filter_options": build_filter_options(dashboard, task_units),
        "weekly_report_summary": weekly_summary,
        "weekly_reports": weekly_reports,
    }


def _is_collection_detail(row: dict[str, Any]) -> bool:
    return str(row.get("parser") or "collection_detail") == "collection_detail"


def _date_bounds(rows: list[dict[str, Any]]) -> dict[str, str]:
    dates = sorted({str(row.get("date")) for row in rows if row.get("date")})
    return {"min": dates[0] if dates else "", "max": dates[-1] if dates else ""}


def _is_human_schedule(row: dict[str, Any]) -> bool:
    return str(row.get("parser") or "") == "human_driving_schedule"


def _is_human_output(row: dict[str, Any]) -> bool:
    return str(row.get("parser") or "") == "human_driving_output"


def build_human_dispatch_summary(
    schedules: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    vehicles: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    dates = sorted(
        {
            str(row.get("date"))
            for row in [*schedules, *outputs, *vehicles]
            if row.get("date")
        }
    )
    drivers = _split_people(row.get("driver") for row in schedules)
    collectors = _unique_texts(row.get("collector") for row in outputs)
    vehicle_numbers = _unique_texts(
        [
            *[row.get("car_number") for row in schedules],
            *[row.get("car_number") for row in outputs],
            *[row.get("car_number") for row in vehicles],
        ]
    )
    duration_minutes = sum(_float_value(row.get("duration_minutes")) for row in outputs)
    mileage = sum(_float_value(row.get("mileage_km")) for row in outputs)
    status_counts = _status_counts(vehicles)
    return {
        "schedule_count": len(schedules),
        "output_count": len(outputs),
        "vehicle_count": len(vehicle_numbers),
        "driver_count": len(drivers),
        "collector_count": len(collectors),
        "people_count": len(_unique_texts([*drivers, *collectors])),
        "output_hours": round(duration_minutes / 60, 2),
        "output_mileage_km": round(mileage, 2),
        "risk_count": len(risks),
        "date_min": dates[0] if dates else "",
        "date_max": dates[-1] if dates else "",
        **status_counts,
    }


def build_human_dispatch_daily_series(
    schedules: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    vehicles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    def item_for(date_text: str) -> dict[str, Any]:
        return grouped.setdefault(
            date_text,
            {
                "date": date_text,
                "schedule_count": 0,
                "output_count": 0,
                "output_hours": 0.0,
                "output_mileage_km": 0.0,
                "vehicle_count": 0,
                "active_count": 0,
                "idle_count": 0,
                "abnormal_count": 0,
                "unknown_count": 0,
                "_vehicles": set(),
            },
        )

    for row in schedules:
        date_text = str(row.get("date") or "")
        if not date_text:
            continue
        item = item_for(date_text)
        item["schedule_count"] += 1
        if row.get("car_number"):
            item["_vehicles"].add(str(row["car_number"]))

    for row in outputs:
        date_text = str(row.get("date") or "")
        if not date_text:
            continue
        item = item_for(date_text)
        item["output_count"] += 1
        item["output_hours"] += _float_value(row.get("duration_minutes")) / 60
        item["output_mileage_km"] += _float_value(row.get("mileage_km"))
        if row.get("car_number"):
            item["_vehicles"].add(str(row["car_number"]))

    for row in vehicles:
        date_text = str(row.get("date") or "")
        if not date_text:
            continue
        item = item_for(date_text)
        if row.get("car_number"):
            item["_vehicles"].add(str(row["car_number"]))
        status = str(row.get("status") or "unknown")
        key = f"{status}_count"
        if key in item:
            item[key] += 1

    rows: list[dict[str, Any]] = []
    for item in grouped.values():
        vehicle_set = item.pop("_vehicles")
        item["vehicle_count"] = len(vehicle_set)
        item["output_hours"] = round(float(item["output_hours"]), 2)
        item["output_mileage_km"] = round(float(item["output_mileage_km"]), 2)
        rows.append(item)
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows


def build_human_dispatch_task_rankings(schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in schedules:
        task = str(row.get("task") or "未标注任务").strip() or "未标注任务"
        item = grouped.setdefault(task, {"task": task, "record_count": 0, "vehicles": set(), "drivers": set()})
        item["record_count"] += 1
        if row.get("car_number"):
            item["vehicles"].add(str(row["car_number"]))
        for driver in _split_people([row.get("driver")]):
            item["drivers"].add(driver)
    rows = [
        {
            "task": item["task"],
            "record_count": item["record_count"],
            "vehicle_count": len(item["vehicles"]),
            "driver_count": len(item["drivers"]),
        }
        for item in grouped.values()
    ]
    rows.sort(key=lambda row: (-row["driver_count"], -row["vehicle_count"], -row["record_count"], row["task"]))
    return rows[:12]


def build_human_dispatch_output_rankings(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in outputs:
        label = str(row.get("route") or row.get("scene") or "未标注路线").strip() or "未标注路线"
        item = grouped.setdefault(label, {"label": label, "record_count": 0, "duration_minutes": 0.0, "mileage_km": 0.0})
        item["record_count"] += 1
        item["duration_minutes"] += _float_value(row.get("duration_minutes"))
        item["mileage_km"] += _float_value(row.get("mileage_km"))
    rows = [
        {
            "label": item["label"],
            "record_count": item["record_count"],
            "output_hours": round(item["duration_minutes"] / 60, 2),
            "mileage_km": round(item["mileage_km"], 2),
        }
        for item in grouped.values()
    ]
    rows.sort(key=lambda row: (-row["mileage_km"], -row["output_hours"], row["label"]))
    return rows[:12]


def build_human_dispatch_risks(
    schedules: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for row in schedules:
        note = str(row.get("exception_note") or row.get("data_issue_note") or "").strip()
        if not note:
            continue
        risks.append(
            {
                "type": "排班异常",
                "date": row.get("date") or "",
                "site": row.get("site") or "",
                "target": row.get("car_number") or row.get("driver") or "-",
                "message": note,
                "source": row.get("source") or "",
                "source_line": row.get("source_line") or "",
            }
        )
    for row in outputs:
        note = str(row.get("exception_note") or "").strip()
        if not note:
            continue
        risks.append(
            {
                "type": "产出异常",
                "date": row.get("date") or "",
                "site": row.get("site") or "",
                "target": row.get("car_number") or row.get("collector") or "-",
                "message": note,
                "source": row.get("source") or "",
                "source_line": row.get("source_line") or "",
            }
        )
    risks.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("source_line") or "")), reverse=True)
    return risks


def build_filter_options(dashboard: dict[str, Any], task_units: list[dict[str, Any]]) -> dict[str, list[str]]:
    rows = [
        *task_units,
        *list(dashboard.get("vehicle_daily_status") or []),
        *list(dashboard.get("resource_schedule_records") or []),
        *list(dashboard.get("collection_output_records") or []),
    ]
    return {
        "departments": _unique_texts(row.get("department") for row in rows),
        "sites": _unique_texts(row.get("site") for row in rows),
        "source_roles": _unique_texts(row.get("source_role") for row in rows),
    }


def build_daily_attendance_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize attendance by date with one SD counted once per day."""
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        date_text = str(record.get("date") or "").strip()
        driver = str(record.get("driver") or "").strip()
        if not date_text or not driver:
            continue
        item = grouped.setdefault(
            date_text,
            {
                "date": date_text,
                "drivers": set(),
                "white_drivers": set(),
                "night_drivers": set(),
                "tasks": set(),
            },
        )
        item["drivers"].add(driver)
        if record.get("task"):
            item["tasks"].add(str(record.get("task")))
        shift = _shift_text(record)
        if "白" in shift:
            item["white_drivers"].add(driver)
        if "夜" in shift:
            item["night_drivers"].add(driver)

    rows = []
    for item in grouped.values():
        drivers = sorted(item["drivers"])
        white = sorted(item["white_drivers"])
        night = sorted(item["night_drivers"])
        rows.append(
            {
                "date": item["date"],
                "total_count": len(drivers),
                "white_count": len(white),
                "night_count": len(night),
                "task_count": len(item["tasks"]),
                "drivers": drivers,
                "white_drivers": white,
                "night_drivers": night,
                "departments": _unique_texts(record.get("department") for record in records if record.get("date") == item["date"]),
                "sites": _unique_texts(record.get("site") for record in records if record.get("date") == item["date"]),
            }
        )
    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows


def build_task_attendance_units(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one unit per date + task + driver for range Top5 calculations."""
    units: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        date_text = str(record.get("date") or "").strip()
        task = str(record.get("task") or "未知任务").strip() or "未知任务"
        driver = str(record.get("driver") or "").strip()
        if not date_text or not driver:
            continue
        department = str(record.get("department") or "数采")
        site = str(record.get("site") or "")
        source_role = str(record.get("source_role") or "")
        key = (date_text, department, site, task, driver)
        item = units.setdefault(
            key,
            {
                "date": date_text,
                "department": department,
                "site": site,
                "source_role": source_role,
                "parser": str(record.get("parser") or ""),
                "task": task,
                "driver": driver,
                "car_number": str(record.get("car_number") or ""),
                "shift_labels": set(),
                "white": False,
                "night": False,
            },
        )
        shift = _shift_text(record)
        if shift:
            item["shift_labels"].add(shift)
        if "白" in shift:
            item["white"] = True
        if "夜" in shift:
            item["night"] = True

    rows = []
    for item in units.values():
        labels = sorted(item["shift_labels"])
        rows.append(
            {
                "date": item["date"],
                "department": item["department"],
                "site": item["site"],
                "source_role": item["source_role"],
                "parser": item["parser"],
                "task": item["task"],
                "driver": item["driver"],
                "car_number": item["car_number"],
                "shift": " / ".join(labels) if labels else "-",
                "white": bool(item["white"]),
                "night": bool(item["night"]),
            }
        )
    rows.sort(key=lambda item: (item["date"], item["task"], item["driver"]), reverse=True)
    return rows


def build_weekly_report_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {"available": False}
    focus = report.get("focus_summary") or {}
    kpis = report.get("kpis") or {}
    resource = focus.get("resource_collection_status") or {}
    return {
        "available": True,
        "week_id": report.get("week_id"),
        "period": report.get("period") or {},
        "generated_at": report.get("generated_at"),
        "kpis": {
            "total_attendance": kpis.get("total_attendance", 0),
            "unique_drivers": kpis.get("unique_drivers", 0),
            "avg_daily_sd": kpis.get("avg_daily_sd", resource.get("current_value", 0)),
            "task_types": kpis.get("task_types", 0),
        },
        "resource_status": resource,
        "top5_tasks": list(focus.get("top5_tasks") or [])[:5],
        "personnel_stability": list(focus.get("top_task_personnel_stability") or [])[:8],
        "risk_items": list(report.get("risk_items") or [])[:12],
        "dashboard_overview": report.get("dashboard_overview") or {},
    }


def build_weekly_reports(
    daily_attendance: list[dict[str, Any]],
    task_units: list[dict[str, Any]],
    vehicle_daily_status: list[dict[str, Any]],
    *,
    weekly_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build one local weekly report for every week covered by the current data."""
    buckets: dict[str, dict[str, Any]] = {}

    def bucket_for(date_text: str) -> dict[str, Any] | None:
        parsed = _parse_date_text(date_text)
        if not parsed:
            return None
        iso_year, iso_week, _ = parsed.isocalendar()
        week_id = f"{iso_year}-W{iso_week:02d}"
        week_start = parsed - timedelta(days=parsed.weekday())
        week_end = week_start + timedelta(days=6)
        return buckets.setdefault(
            week_id,
            {
                "week_id": week_id,
                "period": {
                    "start_date": week_start.isoformat(),
                    "end_date": week_end.isoformat(),
                },
                "daily_rows": [],
                "task_units": [],
                "vehicle_rows": [],
            },
        )

    for row in daily_attendance:
        bucket = bucket_for(str(row.get("date") or ""))
        if bucket is not None:
            bucket["daily_rows"].append(row)

    for row in task_units:
        bucket = bucket_for(str(row.get("date") or ""))
        if bucket is not None:
            bucket["task_units"].append(row)

    for row in vehicle_daily_status:
        bucket = bucket_for(str(row.get("date") or ""))
        if bucket is not None:
            bucket["vehicle_rows"].append(row)

    reports = [_weekly_bucket_to_report(bucket) for bucket in buckets.values()]
    reports.sort(key=lambda item: item["week_id"], reverse=True)

    latest = weekly_summary or {}
    latest_week_id = latest.get("week_id")
    if latest.get("available") and latest_week_id:
        for report in reports:
            if report["week_id"] == latest_week_id:
                report["generated_at"] = latest.get("generated_at")
                report["source"] = "weekly_report_json+current_data"
                report["kpis"] = {**report["kpis"], **(latest.get("kpis") or {})}
                if latest.get("top5_tasks"):
                    report["top5_tasks"] = latest["top5_tasks"]
                break

    return reports


def _weekly_bucket_to_report(bucket: dict[str, Any]) -> dict[str, Any]:
    daily_rows = list(bucket.get("daily_rows") or [])
    task_units = list(bucket.get("task_units") or [])
    vehicle_rows = list(bucket.get("vehicle_rows") or [])
    attendance_count = sum(int(row.get("total_count") or 0) for row in daily_rows)
    active_days = len(daily_rows)
    unique_people = sorted({str(row.get("driver")) for row in task_units if row.get("driver")})
    tasks = sorted({str(row.get("task")) for row in task_units if row.get("task")})
    vehicles = sorted({str(row.get("car_number")) for row in vehicle_rows if row.get("car_number")})
    abnormal_vehicle_days = sum(1 for row in vehicle_rows if row.get("status") == "abnormal")
    active_vehicle_days = sum(1 for row in vehicle_rows if row.get("status") == "active")
    return {
        "available": True,
        "source": "current_data",
        "week_id": bucket["week_id"],
        "period": bucket["period"],
        "kpis": {
            "total_attendance": attendance_count,
            "unique_drivers": len(unique_people),
            "avg_daily_sd": attendance_count / active_days if active_days else 0,
            "task_types": len(tasks),
            "active_days": active_days,
            "vehicle_count": len(vehicles),
            "active_vehicle_days": active_vehicle_days,
            "abnormal_vehicle_days": abnormal_vehicle_days,
        },
        "top5_tasks": _weekly_top_tasks(task_units),
        "personnel_stability": _weekly_task_personnel_rows(task_units),
    }


def _weekly_top_tasks(task_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for unit in task_units:
        task = str(unit.get("task") or "未知任务")
        item = grouped.setdefault(task, {"task": task, "current_total": 0, "white": 0, "night": 0, "drivers": set()})
        item["current_total"] += 1
        if unit.get("white"):
            item["white"] += 1
        if unit.get("night"):
            item["night"] += 1
        if unit.get("driver"):
            item["drivers"].add(str(unit["driver"]))

    rows = []
    for item in grouped.values():
        rows.append(
            {
                "task": item["task"],
                "current_total": item["current_total"],
                "previous_total": 0,
                "delta": item["current_total"],
                "white": item["white"],
                "night": item["night"],
                "driver_count": len(item["drivers"]),
            }
        )
    rows.sort(key=lambda item: (-item["current_total"], item["task"]))
    for index, row in enumerate(rows[:5], start=1):
        row["rank"] = index
    return rows[:5]


def _weekly_task_personnel_rows(task_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for unit in task_units:
        if unit.get("task") and unit.get("driver"):
            grouped[str(unit["task"])].add(str(unit["driver"]))
    rows = [
        {
            "task": task,
            "driver_count": len(drivers),
        }
        for task, drivers in grouped.items()
    ]
    rows.sort(key=lambda item: (-item["driver_count"], item["task"]))
    return rows[:8]


def _unique_texts(values: Any) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value or "").strip()})


def _split_people(values: Any) -> list[str]:
    people: set[str] = set()
    for value in values:
        for item in re.split(r"[/／、,，\s]+", str(value or "")):
            text = item.strip()
            if text:
                people.add(text)
    return sorted(people)


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"active_count": 0, "idle_count": 0, "abnormal_count": 0, "unknown_count": 0}
    for row in rows:
        key = f"{row.get('status') or 'unknown'}_count"
        if key in counts:
            counts[key] += 1
    return counts


def _parse_date_text(value: str) -> date_cls | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def render_collection_dashboard_local_app(
    dashboard: dict[str, Any],
    *,
    weekly_report: dict[str, Any] | None = None,
) -> str:
    payload = build_collection_frontend_payload(dashboard, weekly_report=weekly_report)
    title = "采集数据看板"
    return _LOCAL_APP_TEMPLATE.replace("__TITLE__", escape(title)).replace("__PAYLOAD__", _json_script_payload(payload))


def _shift_text(record: dict[str, Any]) -> str:
    return f"{record.get('shift') or ''}{record.get('shift_table') or ''}"


def _json_script_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/")


_LOCAL_APP_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>__TITLE__</title>
<link rel="icon" href="data:," />
<style>
*{box-sizing:border-box}body{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',Arial,sans-serif;background:#f4f6fb;color:#1f2329;font-size:14px;line-height:1.55}button,input,select{font:inherit}.app{min-height:100vh;padding:16px 20px 28px}.top-tabs{height:44px;display:flex;gap:28px;align-items:flex-end;background:#fff;border-bottom:1px solid #e5e8ef;margin:-16px -20px 16px;padding:0 18px;overflow-x:auto}.top-tab{height:44px;border:0;background:transparent;color:#4e5969;font-weight:700;cursor:pointer;white-space:nowrap}.top-tab.active{color:#1677ff;border-bottom:2px solid #1677ff}.page{display:none}.page.active{display:block}.toolbar{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}h1{font-size:20px;line-height:1.2;margin:0 0 4px;font-weight:850}.meta{display:flex;gap:8px;flex-wrap:wrap;color:#86909c;font-size:12px}.filter-strip{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:#fff;border:1px solid #e5e8ef;border-radius:8px;padding:10px 12px;margin-bottom:12px}.filter-label{color:#86909c;font-size:12px;white-space:nowrap}.date-range{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.date-input{height:32px;min-width:142px;border:1px solid #d9dee8;border-radius:6px;background:#fff;color:#1f2329;padding:0 10px;font-size:13px}.date-input:focus{outline:0;border-color:#1677ff;box-shadow:0 0 0 2px rgba(22,119,255,.12)}.primary-button{height:32px;border:1px solid #1677ff;border-radius:6px;background:#1677ff;color:#fff;padding:0 14px;font-weight:700;cursor:pointer}.range-note{color:#86909c;font-size:12px;min-height:18px}.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(128px,1fr));gap:12px;margin-bottom:12px}.card{background:#fff;border:1px solid #e5e8ef;border-radius:8px;box-shadow:0 1px 2px rgba(31,35,41,.04)}.kpi{min-height:118px;padding:16px}.kpi-label{font-size:12px;color:#86909c;margin-bottom:10px}.kpi-value{font-size:28px;line-height:1.08;font-weight:850;word-break:break-word}.kpi-sub{font-size:12px;color:#86909c;margin-top:8px}.tone-blue .kpi-value{color:#1677ff}.tone-cyan .kpi-value{color:#13c2c2}.tone-green .kpi-value{color:#00a870}.tone-orange .kpi-value{color:#fa8c16}.tone-purple .kpi-value{color:#722ed1}.tone-red .kpi-value{color:#ff4d4f}.section{margin-bottom:12px;overflow:hidden}.section-head{min-height:48px;display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 16px;border-bottom:1px solid #eef1f6;background:#fff}.section-title{font-size:15px;font-weight:850}.section-sub{font-size:12px;color:#86909c;margin-top:2px}.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:10px;padding:12px}.summary-card{border:1px solid #eef1f6;border-radius:8px;padding:12px;background:#fbfcff}.summary-title{font-weight:800;margin-bottom:8px}.summary-metrics{display:grid;grid-template-columns:1fr 1fr;gap:8px;color:#4e5969;font-size:12px}.summary-metrics strong{display:block;color:#1f2329;font-size:18px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;min-width:820px}th{background:#f7f8fa;color:#4e5969;text-align:center;font-weight:750;padding:10px 12px;border-bottom:1px solid #e5e8ef;white-space:nowrap}td{padding:10px 12px;border-bottom:1px solid #eef1f6;text-align:center;vertical-align:top}td.left{text-align:left;font-weight:650}.status{display:inline-flex;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:750;white-space:nowrap}.active{background:#e8fffb;color:#08979c}.idle{background:#f2f3f5;color:#4e5969}.abnormal{background:#fff1f0;color:#cf1322}.unknown{background:#fff7e6;color:#d46b08}.bars{padding:14px 16px}.bar-row{display:grid;grid-template-columns:104px minmax(0,1fr) 60px;gap:10px;align-items:center;margin:8px 0}.bar-row button{border:0;background:transparent;color:#1f2329;text-align:left;cursor:pointer;padding:0}.bar-row button:hover{color:#1677ff}.bar-track{height:12px;background:#edf0f5;border-radius:999px;overflow:hidden;display:flex}.bar-active{background:#13c2c2}.bar-idle{background:#c9cdd4}.bar-abnormal{background:#ff4d4f}.bar-unknown{background:#faad14}.detail-chips{display:flex;gap:5px;flex-wrap:wrap;justify-content:center}.chip{display:inline-flex;border-radius:999px;border:1px solid #d9dee8;background:#fff;padding:2px 7px;font-size:12px;white-space:nowrap}.link-button{border:1px solid #d9dee8;background:#fff;border-radius:6px;padding:4px 9px;color:#1677ff;cursor:pointer;white-space:nowrap}.link-button:hover{border-color:#1677ff;background:#f0f7ff}.drawer-backdrop{position:fixed;inset:0;background:rgba(31,35,41,.28);opacity:0;pointer-events:none;transition:.18s opacity;z-index:20}.drawer-backdrop.open{opacity:1;pointer-events:auto}.drawer{position:fixed;right:0;top:0;width:min(1040px,94vw);height:100vh;background:#fff;box-shadow:-8px 0 24px rgba(31,35,41,.18);transform:translateX(100%);transition:.22s transform;z-index:21;display:flex;flex-direction:column}.drawer.open{transform:translateX(0)}.drawer-head{padding:16px 18px;border-bottom:1px solid #eef1f6;display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.drawer-title{font-size:18px;font-weight:850}.drawer-sub{font-size:12px;color:#86909c;margin-top:3px}.drawer-close{width:32px;height:32px;border:1px solid #d9dee8;background:#fff;border-radius:6px;cursor:pointer;font-size:18px;line-height:1}.drawer-body{padding:14px 18px 20px;overflow:auto}.drawer-summary{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));gap:10px;margin-bottom:12px}.drawer-summary-item{border:1px solid #eef1f6;border-radius:8px;background:#fbfcff;padding:10px}.drawer-summary-item strong{display:block;font-size:22px}.vehicle-visual{border:1px solid #eef1f6;border-radius:8px;background:#fbfcff;padding:14px;margin-bottom:12px}.visual-title{text-align:center;font-size:16px;font-weight:850;margin:0 0 14px}.visual-columns{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));gap:14px;align-items:end;margin-bottom:18px}.visual-column{height:126px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:8px}.visual-column-box{width:100%;height:96px;background:#e8eef6;display:flex;align-items:flex-end;justify-content:center;position:relative}.visual-column-fill{width:90%;min-height:3px}.visual-column-value{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:800;color:#1f2329}.visual-column-label{font-size:12px;color:#1f2329;white-space:nowrap}.fill-total{background:#5b9bd5}.fill-available{background:#63ba5f}.fill-active{background:#ff9637}.fill-idle{background:#b5a2d2}.fill-problem{background:#e25759}.shift-bars{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:-4px 0 18px}.shift-bar-card{border:1px solid #eef1f6;border-radius:8px;background:#fff;padding:10px}.shift-bar-label{font-size:12px;color:#4e5969;margin-bottom:6px}.shift-bar-track{height:24px;background:#edf0f5;border-radius:4px;overflow:hidden}.shift-bar-fill{height:100%;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;color:#fff;font-weight:800;font-size:12px;min-width:28px}.shift-white{background:#1677ff}.shift-night{background:#722ed1}.visual-charts{display:grid;grid-template-columns:1fr 1fr;gap:16px}.visual-chart{min-width:0}.visual-chart-title{text-align:center;font-weight:800;margin:0 0 10px}.visual-bar-row{display:grid;grid-template-columns:minmax(84px,150px) minmax(0,1fr) 36px;gap:8px;align-items:center;margin:7px 0;border:0;background:transparent;width:100%;padding:0;color:inherit;cursor:pointer}.visual-bar-row:hover .visual-bar-label{color:#1677ff}.visual-bar-label{text-align:right;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.visual-bar-track{height:22px;background:#edf0f5;border-radius:2px;overflow:hidden}.visual-bar-fill{height:100%;min-width:2px}.visual-task{background:#5b9bd5}.visual-problem{background:#e25759}.visual-bar-value{font-size:12px;color:#1f2329}.visual-detail-panel{border:1px solid #d9e8ff;background:#f7fbff;border-radius:8px;margin:0 0 12px;overflow:hidden}.visual-detail-head{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 12px;border-bottom:1px solid #d9e8ff}.visual-detail-title{font-weight:850}.visual-detail-sub{font-size:12px;color:#86909c;margin-top:2px}.status-filter{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}.status-filter button{border:1px solid #d9dee8;background:#fff;border-radius:6px;height:30px;padding:0 10px;cursor:pointer}.status-filter button.active{background:#1677ff;color:#fff;border-color:#1677ff}.empty{padding:22px;color:#86909c}.risk-high{color:#cf1322}.risk-medium{color:#d46b08}.risk-low{color:#00a870}.delta-up{color:#cf1322;font-weight:800}.delta-down{color:#00a870;font-weight:800}.delta-flat{color:#4e5969;font-weight:800}@media(max-width:1180px){.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.visual-charts{grid-template-columns:1fr}}@media(max-width:680px){.app{padding:12px}.top-tabs{margin:-12px -12px 12px;padding:0 12px;gap:18px}.toolbar{flex-direction:column}.date-range{width:100%}.date-input{flex:1 1 130px;min-width:0}.kpi-grid,.summary-grid,.drawer-summary,.visual-columns,.shift-bars{grid-template-columns:1fr}.kpi-value{font-size:24px}.bar-row{grid-template-columns:92px minmax(0,1fr) 42px}.drawer{width:100vw}.visual-bar-row{grid-template-columns:minmax(72px,118px) minmax(0,1fr) 28px}.visual-column{height:110px}}
</style>
<style>
.shift-bars{display:block;margin:-4px 0 18px}
.shift-combined-card{padding:12px}
.shift-bar-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px}
.shift-bar-head strong{font-size:18px;line-height:1;color:#1f2329}
.shift-combined-track{height:30px;display:flex;border-radius:5px;background:#edf0f5;overflow:hidden}
.shift-bar-segment{height:100%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:850;font-size:12px;min-width:0}
.shift-bar-segment.is-empty{color:#86909c;background:#edf0f5;width:100%}
.shift-bar-legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;color:#4e5969;font-size:12px}
.shift-dot{width:8px;height:8px;border-radius:2px;display:inline-block;margin-right:6px}
.shift-dot.shift-white{background:#1677ff}
.shift-dot.shift-night{background:#722ed1}
.top-updated-at{margin-left:auto;align-self:center;color:#4e5969;font-size:12px;white-space:nowrap;background:#f0f7ff;border:1px solid #d6e8ff;border-radius:999px;padding:4px 10px}
.page.active{display:block;background:transparent;color:inherit}.top-tab.active{background:transparent;color:#1677ff}
.dispatch-shell{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr);gap:12px;align-items:start;margin-bottom:12px}.dispatch-panel{background:#fff;border:1px solid #e5e8ef;border-radius:8px;overflow:hidden}.dispatch-panel-head{min-height:48px;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid #eef1f6}.dispatch-panel-title{font-size:15px;font-weight:850}.dispatch-panel-sub{font-size:12px;color:#86909c;margin-top:2px}.dispatch-board{padding:14px}.dispatch-kpis{display:grid;grid-template-columns:repeat(5,minmax(112px,1fr));gap:10px;margin-bottom:12px}.dispatch-kpi{border:1px solid #e5e8ef;border-radius:8px;background:#fbfcff;padding:12px;min-height:92px}.dispatch-kpi span{display:block;color:#4e5969;font-size:12px;margin-bottom:8px}.dispatch-kpi strong{display:block;font-size:26px;line-height:1;font-weight:900}.dispatch-kpi small{display:block;color:#86909c;font-size:12px;margin-top:8px}.dispatch-kpi.is-good strong{color:#00a870}.dispatch-kpi.is-work strong{color:#1677ff}.dispatch-kpi.is-idle strong{color:#8a63d2}.dispatch-kpi.is-risk strong{color:#cf1322}.dispatch-kpi.is-unknown strong{color:#d46b08}.dispatch-filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.dispatch-filters button{height:30px;border:1px solid #d9dee8;border-radius:6px;background:#fff;padding:0 10px;cursor:pointer;color:#1f2329}.dispatch-filters button.active{background:#1f2329;color:#fff;border-color:#1f2329}.dispatch-search{height:32px;min-width:220px;border:1px solid #d9dee8;border-radius:6px;padding:0 10px}.dispatch-trend{padding:12px 14px}.dispatch-trend-row{display:grid;grid-template-columns:92px minmax(0,1fr) 42px;gap:8px;align-items:center;margin:8px 0}.dispatch-trend-row button{border:0;background:transparent;text-align:left;padding:0;color:#1f2329;cursor:pointer;font-weight:700}.dispatch-trend-row button.active{color:#1677ff}.dispatch-detail-panel{border:1px solid #d9e8ff;background:#f7fbff;border-radius:8px;margin:0 0 12px;overflow:hidden}.dispatch-table-note{font-size:12px;color:#86909c}.dispatch-empty{padding:18px;color:#86909c}
.human-shell{display:grid;grid-template-columns:minmax(0,1.18fr) minmax(340px,.82fr);gap:12px;align-items:start;margin-bottom:12px}.human-panel{background:#fff;border:1px solid #e5e8ef;border-radius:8px;overflow:hidden}.human-panel-body{padding:12px 14px}.human-chart-row{display:grid;grid-template-columns:104px minmax(0,1fr) 86px;gap:8px;align-items:center;margin:8px 0}.human-chart-label{font-weight:750;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.human-chart-meta{font-size:12px;color:#4e5969;text-align:right}.human-track{height:18px;background:#edf0f5;border-radius:4px;overflow:hidden;display:flex}.human-seg-active{background:#13c2c2}.human-seg-idle{background:#b5a2d2}.human-seg-abnormal{background:#ff4d4f}.human-seg-unknown{background:#faad14}.human-rank-row{display:grid;grid-template-columns:minmax(92px,150px) minmax(0,1fr) 86px;gap:8px;align-items:center;margin:8px 0}.human-rank-bar{height:18px;background:#edf0f5;border-radius:4px;overflow:hidden}.human-rank-fill{height:100%;background:#5b9bd5}.human-output-fill{height:100%;background:#00a870}.human-risk-list{padding:4px 0}.human-risk{display:grid;grid-template-columns:78px minmax(0,1fr);gap:10px;padding:8px 0;border-bottom:1px solid #eef1f6}.human-risk-type{font-weight:850;color:#cf1322}.human-risk small{display:block;color:#86909c;margin-top:2px}
@media(max-width:1180px){.dispatch-shell{grid-template-columns:1fr}.dispatch-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:1180px){.human-shell{grid-template-columns:1fr}}
@media(max-width:680px){.dispatch-kpis{grid-template-columns:1fr}.dispatch-panel-head{align-items:flex-start;flex-direction:column}.dispatch-search{width:100%;min-width:0}.dispatch-trend-row,.human-chart-row,.human-rank-row{grid-template-columns:86px minmax(0,1fr) 58px}}
@media(max-width:680px){.top-tabs{align-items:center}.top-updated-at{margin-left:0;font-size:11px;padding:3px 8px}}
</style>
</head>
<body>
<main class="app" data-app="collection-dashboard-local">
  <nav class="top-tabs">
    <button class="top-tab active" type="button" data-page="dashboard">资源总览</button>
    <button class="top-tab" type="button" data-page="dispatch">数采调度</button>
    <button class="top-tab" type="button" data-page="human-dispatch">人驾调度</button>
    <button class="top-tab" type="button" data-page="weekly">周报</button>
    <span class="top-updated-at">更新时间 <span data-bind="top-updated-at"></span></span>
  </nav>
  <section class="page active" data-page-panel="dashboard">
    <div class="toolbar"><div><h1>采集数据看板</h1><div class="meta"><span>锚点日期 <span data-bind="anchor-date"></span></span><span>生成 <span data-bind="generated-at"></span></span><span>记录 <span data-bind="record-count"></span></span></div></div></div>
    <div class="filter-strip" data-section="overview-controls">
      <span class="filter-label">日期范围</span>
      <button class="link-button" type="button" data-action="overview-prev-day">前一日</button>
      <div class="date-range" data-control="date-range">
        <input class="date-input" type="date" data-control="start-date" aria-label="开始日期" />
        <span class="filter-label">至</span>
        <input class="date-input" type="date" data-control="end-date" aria-label="结束日期" />
        <button class="link-button" type="button" data-action="overview-next-day">后一日</button>
        <button class="primary-button" type="button" data-action="apply-date-range">应用</button>
        <span class="range-note" data-bind="range-note"></span>
      </div>
    </div>
    <section class="kpi-grid" id="kpi-grid"></section>
    <section class="card section" data-section="range-summary"><div class="section-head"><div><div class="section-title">汇总</div><div class="section-sub">出勤人数按每日出车人 SD 去重后累计，不同日期同一 SD 可重复计入</div></div></div><div class="summary-grid" id="range-summary"></div></section>
    <section class="card section" data-section="task-top5"><div class="section-head"><div><div class="section-title">Top5 任务</div><div class="section-sub">任务人次按 date + task + driver 去重</div></div></div><div class="table-wrap"><table><thead><tr><th>排名</th><th>任务</th><th>当前人次</th><th>对比人次</th><th>变化</th><th>白/夜班</th></tr></thead><tbody id="top-task-body"></tbody></table></div></section>
    <section class="card section" data-section="vehicle-status"><div class="section-head"><div><div class="section-title">每日车辆状态</div><div class="section-sub">点击日期查看当天车辆明细；出车异常记录与数采问题记录不参与状态判定</div></div></div><div id="vehicle-bars"></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>车辆数</th><th>活跃</th><th>空闲</th><th>异常</th><th>未知</th><th>状态明细</th><th>操作</th></tr></thead><tbody id="vehicle-summary-body"></tbody></table></div></section>
  </section>
  <section class="page" data-page-panel="dispatch">
    <div class="toolbar"><div><h1>车辆调度</h1><div class="meta" id="dispatch-meta"></div></div></div>
    <div class="filter-strip" data-section="dispatch-controls">
      <span class="filter-label">时间范围</span>
      <button class="link-button" type="button" data-action="dispatch-prev-day">前一日</button>
      <input class="date-input" type="date" data-control="dispatch-start-date" aria-label="数采开始日期" />
      <span class="filter-label">至</span>
      <input class="date-input" type="date" data-control="dispatch-end-date" aria-label="数采结束日期" />
      <button class="link-button" type="button" data-action="dispatch-next-day">后一日</button>
      <button class="primary-button" type="button" data-action="apply-dispatch-date-range">应用</button>
      <span class="range-note" id="dispatch-range-note"></span>
      <input class="dispatch-search" type="search" data-control="dispatch-keyword" placeholder="搜索车号 / 任务 / 原因 / 司机" />
    </div>
    <section class="dispatch-kpis" id="dispatch-kpi-grid"></section>
    <div class="dispatch-shell">
      <section class="dispatch-panel">
        <div class="dispatch-panel-head"><div><div class="dispatch-panel-title">当天车辆池</div><div class="dispatch-panel-sub">默认按调度日期查看，优先暴露异常与未知车辆</div></div><span class="dispatch-table-note" id="dispatch-table-note"></span></div>
        <div class="dispatch-board"><div id="dispatch-visualization"></div><div id="dispatch-detail-panel"></div></div>
      </section>
      <section class="dispatch-panel">
        <div class="dispatch-panel-head"><div><div class="dispatch-panel-title">近 14 天状态</div><div class="dispatch-panel-sub">点击日期切换当天调度视图</div></div></div>
        <div class="dispatch-trend" id="dispatch-trend"></div>
      </section>
    </div>
    <section class="card section">
      <div class="section-head"><div><div class="section-title">车辆明细</div><div class="section-sub">状态、任务、司机、班次、传感器与来源行可直接追溯</div></div><div class="dispatch-filters" id="dispatch-status-filter"></div></div>
      <div class="table-wrap"><table><thead><tr><th>日期</th><th>车号</th><th>状态</th><th>任务</th><th>司机</th><th>班次</th><th>传感器</th><th>原因</th><th>来源行</th></tr></thead><tbody id="dispatch-vehicle-body"></tbody></table></div>
    </section>
  </section>
  <section class="page" data-page-panel="human-dispatch">
    <div class="toolbar"><div><h1>人驾调度</h1><div class="meta" id="human-dispatch-meta"></div></div></div>
    <div class="filter-strip" data-section="human-dispatch-controls">
      <span class="filter-label">时间范围</span>
      <button class="link-button" type="button" data-action="human-prev-day">前一日</button>
      <div class="date-range">
        <input class="date-input" type="date" data-control="human-start-date" aria-label="人驾开始日期" />
        <span class="filter-label">至</span>
        <input class="date-input" type="date" data-control="human-end-date" aria-label="人驾结束日期" />
        <button class="link-button" type="button" data-action="human-next-day">后一日</button>
        <button class="primary-button" type="button" data-action="apply-human-date-range">应用</button>
        <span class="range-note" id="human-range-note"></span>
      </div>
    </div>
    <section class="dispatch-kpis" id="human-kpi-grid" aria-label="人驾 KPI"></section>
    <div class="human-shell">
      <section class="human-panel">
        <div class="dispatch-panel-head"><div><div class="dispatch-panel-title">人驾每日调度趋势</div><div class="dispatch-panel-sub">青岛排班车辆状态与盐城产出按日期对齐展示</div></div></div>
        <div class="human-panel-body" id="human-daily-trend"></div>
      </section>
      <section class="human-panel">
        <div class="dispatch-panel-head"><div><div class="dispatch-panel-title">人驾任务占用排行</div><div class="dispatch-panel-sub">按司机、车辆和排班记录综合排序</div></div></div>
        <div class="human-panel-body" id="human-task-ranking"></div>
      </section>
    </div>
    <div class="human-shell">
      <section class="human-panel">
        <div class="dispatch-panel-head"><div><div class="dispatch-panel-title">盐城产出路线排行</div><div class="dispatch-panel-sub">按里程和采集时长展示实际采集产出</div></div></div>
        <div class="human-panel-body" id="human-output-ranking"></div>
      </section>
      <section class="human-panel">
        <div class="dispatch-panel-head"><div><div class="dispatch-panel-title">人驾异常风险</div><div class="dispatch-panel-sub">合并排班异常、数采问题和产出异常备注</div></div></div>
        <div class="human-panel-body"><div class="human-risk-list" id="human-risk-list"></div></div>
      </section>
    </div>
    <section class="card section">
      <div class="section-head"><div><div class="section-title">青岛排班明细</div><div class="section-sub">日期、任务、班次、车号、司机、异常与来源行可追溯</div></div></div>
      <div class="table-wrap"><table><thead><tr><th>日期</th><th>任务</th><th>班次</th><th>车号</th><th>司机</th><th>出车时间</th><th>异常</th><th>来源行</th></tr></thead><tbody id="human-schedule-body"></tbody></table></div>
    </section>
    <section class="card section">
      <div class="section-head"><div><div class="section-title">盐城产出明细</div><div class="section-sub">实际采集时长、里程、取数状态与异常备注</div></div></div>
      <div class="table-wrap"><table><thead><tr><th>日期</th><th>车号</th><th>采集员</th><th>场景</th><th>路线</th><th>开始</th><th>结束</th><th>时长</th><th>里程</th><th>取数</th><th>异常备注</th><th>来源行</th></tr></thead><tbody id="human-output-body"></tbody></table></div>
    </section>
  </section>
  <section class="page" data-page-panel="weekly">
    <div class="toolbar"><div><h1>周报</h1><div class="meta" id="weekly-meta"></div></div></div>
    <div class="filter-strip" data-section="weekly-compare-controls">
      <span class="filter-label">当前周</span>
      <select class="date-input" data-control="weekly-current"></select>
      <span class="filter-label">对比周</span>
      <select class="date-input" data-control="weekly-compare"></select>
      <button class="primary-button" type="button" data-action="apply-weekly-compare">对比</button>
      <span class="range-note" id="weekly-compare-note"></span>
    </div>
    <section class="kpi-grid" id="weekly-kpi-grid"></section>
    <section class="card section"><div class="section-head"><div><div class="section-title">周报 Top5 任务对比</div><div class="section-sub">支持任意两周之间对比，任务人次按 date + task + driver 去重</div></div></div><div class="table-wrap"><table><thead><tr><th>排名</th><th>任务</th><th>当前周人次</th><th>对比周人次</th><th>变化</th><th>当前周白/夜班</th></tr></thead><tbody id="weekly-top-task-body"></tbody></table></div></section>
    <section class="card section"><div class="section-head"><div><div class="section-title">任务参与覆盖</div><div class="section-sub">当前周重点任务参与人数</div></div></div><div class="table-wrap"><table><thead><tr><th>任务</th><th>当前周参与人数</th><th>对比周参与人数</th><th>变化</th></tr></thead><tbody id="weekly-stability-body"></tbody></table></div></section>
    <div class="card empty" id="weekly-empty">暂无周报数据</div>
  </section>
</main>
<div class="drawer-backdrop" data-action="close-vehicle-drawer"></div>
<aside class="drawer" id="vehicle-drawer" aria-hidden="true" aria-label="每日车辆状态详情">
  <div class="drawer-head"><div><div class="drawer-title" id="drawer-title">车辆状态详情</div><div class="drawer-sub" id="drawer-subtitle"></div></div><button class="drawer-close" type="button" data-action="close-vehicle-drawer" aria-label="关闭">×</button></div>
  <div class="drawer-body"><div class="drawer-summary" id="drawer-summary"></div><div id="drawer-visualization"></div><div id="visual-detail-panel"></div><div class="status-filter" id="drawer-status-filter"></div><div class="table-wrap"><table><thead><tr><th>车号</th><th>状态</th><th>任务</th><th>司机</th><th>班次</th><th>传感器</th><th>原因</th><th>来源行</th></tr></thead><tbody id="drawer-vehicle-body"></tbody></table></div></div>
</aside>
<script id="collection-dashboard-data" type="application/json">__PAYLOAD__</script>
<script>
(() => {
  const dataNode = document.getElementById('collection-dashboard-data');
  const data = JSON.parse(dataNode.textContent || '{}');
  const state = { startDate: null, endDate: null, selectedDate: null, statusFilter: 'all', currentView: null, visualDetail: null, weeklyCurrent: null, weeklyCompare: null, dispatchDate: null, dispatchStartDate: null, dispatchEndDate: null, dispatchView: null, dispatchStatusFilter: 'all', dispatchKeyword: '', humanStartDate: null, humanEndDate: null, humanView: null };
  const statusLabels = { all: '全部', active: '活跃', idle: '空闲', abnormal: '异常', unknown: '未知' };
  const statusOrder = ['all', 'active', 'idle', 'abnormal', 'unknown'];
  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const join = (values) => Array.isArray(values) && values.length ? values.join('、') : '-';
  const dateInRange = (date, start, end) => Boolean(date && date >= start && date <= end);
  const unique = (values) => Array.from(new Set(values.filter(Boolean).map(String))).sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const formatNumber = (value) => {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return String(value ?? '-');
    return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/\\.?0+$/, '');
  };
  const statusPill = (status, label) => `<span class="status ${escapeHtml(status || 'unknown')}">${escapeHtml(label || statusLabels[status] || status || '未知')}</span>`;

  function boot() {
    bindEvents();
    $('[data-bind="anchor-date"]').textContent = data.anchor_date || '-';
    $('[data-bind="generated-at"]').textContent = String(data.generated_at || '-').replace('T', ' ').slice(0, 16);
    $('[data-bind="top-updated-at"]').textContent = String(data.generated_at || '-').replace('T', ' ').slice(0, 16);
    $('[data-bind="record-count"]').textContent = data.record_count ?? 0;
    initDateRange();
    applyDateRange();
    initDispatchControls();
    renderDispatchPage();
    initHumanDateRange();
    renderHumanDispatchPage();
    initWeeklyControls();
    renderWeeklyPage();
  }

  function bindEvents() {
    document.addEventListener('click', (event) => {
      const pageButton = event.target.closest('[data-page]');
      if (pageButton) {
        activatePage(pageButton.dataset.page);
        return;
      }
      if (event.target.closest('[data-action="apply-date-range"]')) {
        applyDateRange();
        return;
      }
      if (event.target.closest('[data-action="overview-prev-day"]')) {
        shiftOverviewDateRange(-1);
        return;
      }
      if (event.target.closest('[data-action="overview-next-day"]')) {
        shiftOverviewDateRange(1);
        return;
      }
      if (event.target.closest('[data-action="apply-weekly-compare"]')) {
        applyWeeklyCompare();
        return;
      }
      if (event.target.closest('[data-action="apply-dispatch-date"]')) {
        applyDispatchDate($('[data-control="dispatch-date"]').value || state.dispatchDate);
        return;
      }
      if (event.target.closest('[data-action="apply-dispatch-date-range"]')) {
        applyDispatchDateRange();
        return;
      }
      if (event.target.closest('[data-action="apply-human-date-range"]')) {
        applyHumanDateRange();
        return;
      }
      if (event.target.closest('[data-action="dispatch-prev-day"]')) {
        shiftDispatchDateRange(-1);
        return;
      }
      if (event.target.closest('[data-action="dispatch-next-day"]')) {
        shiftDispatchDateRange(1);
        return;
      }
      if (event.target.closest('[data-action="human-prev-day"]')) {
        shiftHumanDateRange(-1);
        return;
      }
      if (event.target.closest('[data-action="human-next-day"]')) {
        shiftHumanDateRange(1);
        return;
      }
      const dispatchDateButton = event.target.closest('[data-action="set-dispatch-date"]');
      if (dispatchDateButton) {
        applyDispatchDate(dispatchDateButton.dataset.date);
        activatePage('dispatch');
        return;
      }
      const dispatchFilterButton = event.target.closest('[data-dispatch-status-filter]');
      if (dispatchFilterButton) {
        state.dispatchStatusFilter = dispatchFilterButton.dataset.dispatchStatusFilter || 'all';
        renderDispatchVehicleTable(state.dispatchView?.vehicle_daily_status || []);
        return;
      }
      const dayButton = event.target.closest('[data-action="open-vehicle-day"]');
      if (dayButton) {
        openVehicleDay(dayButton.dataset.date);
        return;
      }
      if (event.target.closest('[data-action="close-vehicle-drawer"]')) {
        closeVehicleDrawer();
        return;
      }
      const filterButton = event.target.closest('[data-status-filter]');
      if (filterButton) {
        state.statusFilter = filterButton.dataset.statusFilter || 'all';
        renderVehicleDrawer();
        return;
      }
      const visualDetailButton = event.target.closest('[data-detail-kind]');
      if (visualDetailButton) {
        state.visualDetail = {
          kind: visualDetailButton.dataset.detailKind,
          label: visualDetailButton.dataset.detailLabel,
        };
        renderVisualDetailPanel();
        renderDispatchDetailPanel();
        return;
      }
      if (event.target.closest('[data-action="clear-visual-detail"]')) {
        state.visualDetail = null;
        renderVisualDetailPanel();
        renderDispatchDetailPanel();
      }
    });
    document.addEventListener('input', (event) => {
      if (event.target.closest('[data-control="dispatch-keyword"]')) {
        state.dispatchKeyword = event.target.value || '';
        renderDispatchVehicleTable(state.dispatchView?.vehicle_daily_status || []);
      }
    });
    document.addEventListener('change', (event) => {
      if (event.target.closest('[data-control="weekly-current"], [data-control="weekly-compare"]')) {
        applyWeeklyCompare();
      }
      if (event.target.closest('[data-control="dispatch-date"]')) {
        applyDispatchDate(event.target.value || state.dispatchDate);
      }
      if (event.target.closest('[data-control="dispatch-start-date"], [data-control="dispatch-end-date"]')) {
        applyDispatchDateRange();
      }
      if (event.target.closest('[data-control="human-start-date"], [data-control="human-end-date"]')) {
        applyHumanDateRange();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeVehicleDrawer();
      if (event.key === 'Enter' && event.target.closest('[data-control="start-date"], [data-control="end-date"]')) {
        event.preventDefault();
        applyDateRange();
      }
      if (event.key === 'Enter' && event.target.closest('[data-control="dispatch-start-date"], [data-control="dispatch-end-date"]')) {
        event.preventDefault();
        applyDispatchDateRange();
      }
      if (event.key === 'Enter' && event.target.closest('[data-control="human-start-date"], [data-control="human-end-date"]')) {
        event.preventDefault();
        applyHumanDateRange();
      }
    });
  }

  function activatePage(page) {
    document.querySelectorAll('[data-page]').forEach((button) => button.classList.toggle('active', button.dataset.page === page));
    document.querySelectorAll('[data-page-panel]').forEach((panel) => panel.classList.toggle('active', panel.dataset.pagePanel === page));
  }

  function initDateRange() {
    const bounds = data.date_bounds || {};
    const startInput = $('[data-control="start-date"]');
    const endInput = $('[data-control="end-date"]');
    state.startDate = data.anchor_date || bounds.max || bounds.min || '';
    state.endDate = state.startDate;
    [startInput, endInput].forEach((input) => {
      if (!input) return;
      if (bounds.min) input.min = bounds.min;
      if (bounds.max) input.max = bounds.max;
    });
    startInput.value = state.startDate;
    endInput.value = state.endDate;
  }

  function applyDateRange() {
    const startInput = $('[data-control="start-date"]');
    const endInput = $('[data-control="end-date"]');
    let startDate = startInput.value || state.startDate;
    let endDate = endInput.value || state.endDate || startDate;
    [startDate, endDate] = clampDateRange(startDate, endDate, data.date_bounds || {});
    startInput.value = startDate;
    endInput.value = endDate;
    state.startDate = startDate;
    state.endDate = endDate;
    state.currentView = buildRangeView(startDate, endDate);
    renderKpis(state.currentView);
    renderRangeSummary(state.currentView);
    renderTopTasks(state.currentView);
    renderVehicleStatus(state.currentView);
    $('[data-bind="range-note"]').textContent = `${startDate} 至 ${endDate}`;
  }

  function shiftOverviewDateRange(days) {
    const [startDate, endDate] = shiftDateRange(state.startDate, state.endDate, days, data.date_bounds || {});
    $('[data-control="start-date"]').value = startDate;
    $('[data-control="end-date"]').value = endDate;
    applyDateRange();
  }

  function buildRangeView(startDate, endDate) {
    const dailyRows = (data.daily_attendance_summary || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const taskUnits = (data.task_attendance_units || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const previous = previousRangeBounds(startDate, endDate);
    const previousUnits = (data.task_attendance_units || []).filter((item) => dateInRange(item.date, previous.start, previous.end));
    const vehicleRows = (data.dispatch_vehicle_daily_status || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const attendanceCount = dailyRows.reduce((sum, item) => sum + Number(item.total_count || 0), 0);
    const activeDays = dailyRows.length;
    const drivers = unique(taskUnits.map((item) => item.driver));
    const vehicleSummary = summarizeVehicleRows(vehicleRows);
    const vehicleStatus = aggregateVehicleRows(vehicleRows);
    return {
      current_period: { start_date: startDate, end_date: endDate },
      compare_period: { start_date: previous.start, end_date: previous.end },
      daily_attendance_summary: dailyRows,
      task_attendance_units: taskUnits,
      top5_tasks: buildTopTasks(taskUnits, previousUnits),
      vehicle_daily_status: vehicleRows,
      vehicle_daily_summary: vehicleSummary,
      metrics: {
        attendance_count: attendanceCount,
        unique_people: drivers.length,
        active_days: activeDays,
        white_attendance: dailyRows.reduce((sum, item) => sum + Number(item.white_count || 0), 0),
        night_attendance: dailyRows.reduce((sum, item) => sum + Number(item.night_count || 0), 0),
        sd_per_day: activeDays ? attendanceCount / activeDays : 0,
        top_task_count: Math.min(5, unique(taskUnits.map((item) => item.task)).length),
      },
      vehicle_status: vehicleStatus,
    };
  }

  function buildTopTasks(currentUnits, previousUnits) {
    const current = aggregateTasks(currentUnits);
    const previous = aggregateTasks(previousUnits);
    return Array.from(current.values()).sort((a, b) => b.current_total - a.current_total || a.task.localeCompare(b.task, 'zh-CN')).slice(0, 5).map((item, index) => {
      const previousTotal = previous.get(item.task)?.current_total || 0;
      return {
        rank: index + 1,
        task: item.task,
        current_total: item.current_total,
        previous_total: previousTotal,
        delta: item.current_total - previousTotal,
        white: item.white,
        night: item.night,
      };
    });
  }

  function aggregateTasks(units) {
    const tasks = new Map();
    units.forEach((unit) => {
      const task = unit.task || '未知任务';
      if (!tasks.has(task)) tasks.set(task, { task, current_total: 0, white: 0, night: 0 });
      const item = tasks.get(task);
      item.current_total += 1;
      if (unit.white) item.white += 1;
      if (unit.night) item.night += 1;
    });
    return tasks;
  }

  function renderKpis(view) {
    const metrics = view.metrics;
    const vehicle = view.vehicle_status;
    const cards = [
      ['attendance_count', '出勤人数', metrics.attendance_count, '每日 SD 去重后累计', 'blue'],
      ['sd_per_day', 'SD 个数/天', formatNumber(metrics.sd_per_day), '分母为有数据天', 'green'],
      ['vehicle_active_count', '活跃车辆', vehicle.active_count, '有效司机优先', 'purple'],
      ['vehicle_abnormal_count', '异常车辆', vehicle.abnormal_count, '未安排司机状态', 'red'],
    ];
    $('#kpi-grid').innerHTML = cards.map(([id, label, value, sub, tone]) => `<div class="card kpi tone-${tone}" data-kpi-id="${id}"><div class="kpi-label">${escapeHtml(label)}</div><div class="kpi-value">${escapeHtml(value)}</div><div class="kpi-sub">${escapeHtml(sub)}</div></div>`).join('');
  }

  function renderRangeSummary(view) {
    const m = view.metrics;
    const v = view.vehicle_status;
    const cards = [
      ['日期范围', [['开始', view.current_period.start_date], ['结束', view.current_period.end_date]]],
      ['班次出勤', [['白班', m.white_attendance], ['夜班', m.night_attendance]]],
      ['有效天数', [['有数据天', m.active_days], ['覆盖 SD', m.unique_people]]],
      ['车辆状态', [['车辆数', v.vehicle_count], ['车辆日', v.vehicle_day_count]]],
    ];
    $('#range-summary').innerHTML = cards.map(([title, rows]) => `<div class="summary-card"><div class="summary-title">${escapeHtml(title)}</div><div class="summary-metrics">${rows.map(([label, value]) => `<div><strong>${escapeHtml(value)}</strong>${escapeHtml(label)}</div>`).join('')}</div></div>`).join('');
  }

  function renderTopTasks(view) {
    const rows = view.top5_tasks.map((item) => `<tr><td>${item.rank}</td><td class="left">${escapeHtml(item.task)}</td><td>${item.current_total}</td><td>${item.previous_total}</td><td>${item.delta}</td><td>${item.white}/${item.night}</td></tr>`);
    $('#top-task-body').innerHTML = rows.join('') || '<tr><td colspan="6" class="empty">暂无 Top5 任务</td></tr>';
  }

  function aggregateVehicleRows(rows) {
    const vehicles = new Set();
    const counts = { active: 0, idle: 0, abnormal: 0, unknown: 0 };
    rows.forEach((row) => {
      if (row.car_number) vehicles.add(row.car_number);
      const status = row.status || 'unknown';
      counts[status] = (counts[status] || 0) + 1;
    });
    return { vehicle_count: vehicles.size, vehicle_day_count: rows.length, active_count: counts.active || 0, idle_count: counts.idle || 0, abnormal_count: counts.abnormal || 0, unknown_count: counts.unknown || 0 };
  }

  function summarizeVehicleRows(rows) {
    const grouped = new Map();
    rows.forEach((row) => {
      const date = row.date || '-';
      if (!grouped.has(date)) grouped.set(date, []);
      grouped.get(date).push(row);
    });
    return Array.from(grouped.entries()).map(([date, items]) => {
      const payload = { date, vehicle_count: items.length, active_count: 0, idle_count: 0, abnormal_count: 0, unknown_count: 0, active_vehicles: [], idle_vehicles: [], abnormal_vehicles: [], unknown_vehicles: [] };
      items.forEach((item) => {
        const status = item.status || 'unknown';
        payload[`${status}_count`] = (payload[`${status}_count`] || 0) + 1;
        const list = payload[`${status}_vehicles`];
        if (Array.isArray(list) && item.car_number) list.push(item.car_number);
      });
      ['active_vehicles', 'idle_vehicles', 'abnormal_vehicles', 'unknown_vehicles'].forEach((key) => payload[key] = unique(payload[key]));
      return payload;
    }).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }

  function initDispatchControls() {
    const bounds = data.dispatch_date_bounds || data.date_bounds || {};
    const startInput = $('[data-control="dispatch-start-date"]');
    const endInput = $('[data-control="dispatch-end-date"]');
    state.dispatchStartDate = bounds.max || data.anchor_date || bounds.min || '';
    state.dispatchEndDate = state.dispatchStartDate;
    [startInput, endInput].forEach((input) => {
      if (!input) return;
      if (bounds.min) input.min = bounds.min;
      if (bounds.max) input.max = bounds.max;
    });
    if (startInput) startInput.value = state.dispatchStartDate;
    if (endInput) endInput.value = state.dispatchEndDate;
    applyDispatchDateRange();
  }

  function applyDispatchDate(date) {
    const targetDate = date || state.dispatchDate;
    const startInput = $('[data-control="dispatch-start-date"]');
    const endInput = $('[data-control="dispatch-end-date"]');
    if (startInput) startInput.value = targetDate;
    if (endInput) endInput.value = targetDate;
    applyDispatchDateRange(targetDate, targetDate);
  }

  function applyDispatchDateRange(startDate, endDate) {
    const bounds = data.dispatch_date_bounds || data.date_bounds || {};
    const startInput = $('[data-control="dispatch-start-date"]');
    const endInput = $('[data-control="dispatch-end-date"]');
    let nextStart = startDate || startInput?.value || state.dispatchStartDate || bounds.max || data.anchor_date || bounds.min || '';
    let nextEnd = endDate || endInput?.value || state.dispatchEndDate || nextStart;
    [nextStart, nextEnd] = clampDateRange(nextStart, nextEnd, bounds);
    state.dispatchStartDate = nextStart;
    state.dispatchEndDate = nextEnd;
    state.dispatchDate = nextEnd;
    state.selectedDate = nextEnd;
    state.visualDetail = null;
    if (startInput) startInput.value = nextStart;
    if (endInput) endInput.value = nextEnd;
    state.dispatchView = buildDispatchRangeView(nextStart, nextEnd);
    renderDispatchPage();
  }

  function shiftDispatchDateRange(days) {
    const bounds = data.dispatch_date_bounds || data.date_bounds || {};
    const [startDate, endDate] = shiftDateRange(state.dispatchStartDate, state.dispatchEndDate, days, bounds);
    applyDispatchDateRange(startDate, endDate);
  }

  function buildDispatchRangeView(startDate, endDate) {
    const rows = (data.dispatch_vehicle_daily_status || []).filter((item) => dateInRange(item.date, startDate, endDate));
    return {
      current_period: { start_date: startDate, end_date: endDate },
      vehicle_daily_status: rows,
      vehicle_daily_summary: summarizeVehicleRows(rows),
      summary: dispatchSummary(rows),
    };
  }

  function dispatchRowsForDate(date) {
    return (data.dispatch_vehicle_daily_status || []).filter((item) => item.date === date);
  }

  function dispatchSummary(rows) {
    const counts = rows.reduce((acc, item) => {
      const key = item.status || 'unknown';
      acc[key] = (acc[key] || 0) + 1;
      acc.all += 1;
      return acc;
    }, { all: 0, active: 0, idle: 0, abnormal: 0, unknown: 0 });
    counts.available = counts.active + counts.idle;
    counts.problem = counts.abnormal + counts.unknown;
    counts.activeRate = counts.all ? counts.active / counts.all : 0;
    counts.problemRate = counts.all ? counts.problem / counts.all : 0;
    return counts;
  }

  function renderDispatchPage() {
    const view = state.dispatchView || buildDispatchRangeView(state.dispatchStartDate, state.dispatchEndDate);
    const rows = view.vehicle_daily_status || [];
    const summary = view.summary || dispatchSummary(rows);
    const period = view.current_period?.start_date && view.current_period?.end_date ? `${view.current_period.start_date} 至 ${view.current_period.end_date}` : (state.dispatchDate || '-');
    state.selectedDate = state.dispatchDate;
    $('#dispatch-meta').innerHTML = `<span>调度范围 ${escapeHtml(period)}</span><span>车辆记录 ${escapeHtml(summary.all)}</span><span>问题车辆 ${escapeHtml(summary.problem)}</span>`;
    const note = $('#dispatch-range-note');
    if (note) note.textContent = period;
    $('#dispatch-kpi-grid').innerHTML = [
      ['车辆记录', summary.all, '范围内车辆日记录', ''],
      ['可用车', summary.available, `活跃 + 空闲，占比 ${(summary.all ? summary.available / summary.all * 100 : 0).toFixed(1)}%`, 'is-good'],
      ['实际出车', summary.active, `活跃率 ${(summary.activeRate * 100).toFixed(1)}%`, 'is-work'],
      ['空闲车辆', summary.idle, '可调度但未出车', 'is-idle'],
      ['问题车辆', summary.problem, `异常 ${summary.abnormal} / 未知 ${summary.unknown}`, summary.unknown ? 'is-unknown' : 'is-risk'],
    ].map(([label, value, sub, cls]) => `<div class="dispatch-kpi ${cls}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></div>`).join('');
    $('#dispatch-visualization').innerHTML = rows.length ? vehicleVisualization(rows, summary) : '<div class="dispatch-empty">暂无当天车辆状态数据</div>';
    $('#dispatch-trend').innerHTML = dispatchTrendRows(view);
    renderDispatchDetailPanel();
    renderDispatchVehicleTable(rows);
  }

  function dispatchTrendRows(view = state.dispatchView) {
    const summaries = summarizeVehicleRows(data.dispatch_vehicle_daily_status || []).slice(0, 14);
    if (!summaries.length) return '<div class="dispatch-empty">暂无车辆状态趋势</div>';
    return summaries.map((item) => {
      const total = Math.max(Number(item.vehicle_count || 0), 1);
      const pct = (value) => `${(Number(value || 0) / total * 100).toFixed(2)}%`;
      const active = dateInRange(item.date, view?.current_period?.start_date, view?.current_period?.end_date) ? 'active' : '';
      return `<div class="dispatch-trend-row"><button class="${active}" type="button" data-action="set-dispatch-date" data-date="${escapeHtml(item.date)}">${escapeHtml(item.date)}</button><div class="bar-track"><span class="bar-active" style="width:${pct(item.active_count)}"></span><span class="bar-idle" style="width:${pct(item.idle_count)}"></span><span class="bar-abnormal" style="width:${pct(item.abnormal_count)}"></span><span class="bar-unknown" style="width:${pct(item.unknown_count)}"></span></div><div>${escapeHtml(item.vehicle_count)}</div></div>`;
    }).join('');
  }

  function renderDispatchVehicleTable(rows) {
    const summary = dispatchSummary(rows);
    $('#dispatch-status-filter').innerHTML = statusOrder.map((status) => {
      const value = status === 'all' ? summary.all : summary[status] || 0;
      return `<button type="button" class="${state.dispatchStatusFilter === status ? 'active' : ''}" data-dispatch-status-filter="${status}">${statusLabels[status]} ${escapeHtml(value)}</button>`;
    }).join('');
    const keyword = String(state.dispatchKeyword || '').trim().toLowerCase();
    const rank = { abnormal: 0, unknown: 1, active: 2, idle: 3 };
    const filtered = rows.filter((item) => {
      if (state.dispatchStatusFilter !== 'all' && item.status !== state.dispatchStatusFilter) return false;
      if (!keyword) return true;
      const haystack = [item.car_number, item.status_label, item.status_reason, join(item.tasks), join(item.drivers), join(item.shift_tables), join(item.sensors)].join(' ').toLowerCase();
      return haystack.includes(keyword);
    }).sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || String(a.car_number || '').localeCompare(String(b.car_number || ''), 'zh-CN'));
    $('#dispatch-table-note').textContent = `当前筛选 ${filtered.length} / ${rows.length} 台`;
    $('#dispatch-vehicle-body').innerHTML = filtered.map((item) => `<tr><td>${escapeHtml(item.date || '-')}</td><td>${escapeHtml(item.car_number)}</td><td>${statusPill(item.status, item.status_label)}</td><td class="left">${escapeHtml(join(item.tasks))}</td><td>${escapeHtml(join(item.drivers))}</td><td>${escapeHtml(join(item.shift_tables))}</td><td>${escapeHtml(join(item.sensors))}</td><td class="left">${escapeHtml(item.status_reason || '-')}</td><td>${escapeHtml(join(item.sources))}:${escapeHtml(join(item.source_lines))}</td></tr>`).join('') || '<tr><td colspan="9" class="empty">暂无匹配车辆</td></tr>';
  }

  function renderDispatchDetailPanel() {
    const panel = $('#dispatch-detail-panel');
    if (!panel) return;
    const detail = state.visualDetail;
    if (!detail || !detail.label || !state.dispatchDate) {
      panel.innerHTML = '';
      return;
    }
    const rows = visualDetailRowsInRows(detail, state.dispatchView?.vehicle_daily_status || []);
    const title = detail.kind === 'problem' ? '问题车辆明细' : '出车任务车辆明细';
    const period = state.dispatchStartDate && state.dispatchEndDate ? `${state.dispatchStartDate} 至 ${state.dispatchEndDate}` : state.dispatchDate;
    panel.innerHTML = `<section class="dispatch-detail-panel"><div class="visual-detail-head"><div><div class="visual-detail-title">${escapeHtml(title)}：${escapeHtml(detail.label)}</div><div class="visual-detail-sub">共 ${rows.length} 条记录，来自 ${escapeHtml(period)}</div></div><button class="link-button" type="button" data-action="clear-visual-detail">关闭</button></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>车号</th><th>状态</th><th>任务</th><th>司机</th><th>班次</th><th>原因</th></tr></thead><tbody>${rows.map((item) => `<tr><td>${escapeHtml(item.date || '-')}</td><td>${escapeHtml(item.car_number || '-')}</td><td>${statusPill(item.status, item.status_label)}</td><td class="left">${escapeHtml(join(item.tasks))}</td><td>${escapeHtml(join(item.drivers))}</td><td>${escapeHtml(join(item.shift_tables))}</td><td class="left">${escapeHtml(item.status_reason || '-')}</td></tr>`).join('') || '<tr><td colspan="7" class="empty">暂无匹配车辆</td></tr>'}</tbody></table></div></section>`;
  }

  function renderVehicleStatus(view) {
    const summaries = view.vehicle_daily_summary || [];
    $('#vehicle-bars').innerHTML = `<div class="bars">${summaries.slice(0, 14).map(vehicleBarRow).join('')}</div>`;
    $('#vehicle-summary-body').innerHTML = summaries.slice(0, 30).map(vehicleSummaryRow).join('') || '<tr><td colspan="8" class="empty">暂无车辆状态数据</td></tr>';
  }

  function vehicleBarRow(item) {
    const total = Math.max(Number(item.vehicle_count || 0), 1);
    const pct = (value) => `${(Number(value || 0) / total * 100).toFixed(2)}%`;
    return `<div class="bar-row"><button type="button" data-action="open-vehicle-day" data-date="${escapeHtml(item.date)}">${escapeHtml(item.date)}</button><div class="bar-track"><span class="bar-active" style="width:${pct(item.active_count)}"></span><span class="bar-idle" style="width:${pct(item.idle_count)}"></span><span class="bar-abnormal" style="width:${pct(item.abnormal_count)}"></span><span class="bar-unknown" style="width:${pct(item.unknown_count)}"></span></div><div>${escapeHtml(item.vehicle_count)}</div></div>`;
  }

  function vehicleSummaryRow(item) {
    return `<tr><td><button class="link-button" type="button" data-action="open-vehicle-day" data-date="${escapeHtml(item.date)}">${escapeHtml(item.date)}</button></td><td>${escapeHtml(item.vehicle_count)}</td><td>${escapeHtml(item.active_count)}</td><td>${escapeHtml(item.idle_count)}</td><td>${escapeHtml(item.abnormal_count)}</td><td>${escapeHtml(item.unknown_count)}</td><td>${vehicleSummaryChips(item)}</td><td><button class="link-button" type="button" data-action="open-vehicle-day" data-date="${escapeHtml(item.date)}">查看详情</button></td></tr>`;
  }

  function vehicleSummaryChips(item) {
    return `<div class="detail-chips">${[['active_vehicles', '活跃', 'active'], ['idle_vehicles', '空闲', 'idle'], ['abnormal_vehicles', '异常', 'abnormal'], ['unknown_vehicles', '未知', 'unknown']].map(([key, label, cls]) => {
      const vehicles = item[key] || [];
      const sample = vehicles.slice(0, 3).join('、');
      return `<span class="chip ${cls}">${label} ${vehicles.length}${sample ? `：${escapeHtml(sample)}` : ''}</span>`;
    }).join('')}</div>`;
  }

  function renderDashboardKpis() {
    const kpis = data.dashboard_overview?.kpis || {};
    const rows = Object.values(kpis).map((item) => `<tr><td class="left">${escapeHtml(item.label || '-')}</td><td>${escapeHtml(item.value || '-')}</td><td class="left">${escapeHtml(item.sub || '-')}</td></tr>`);
    $('#dashboard-kpi-body').innerHTML = rows.join('') || '<tr><td colspan="3" class="empty">看板数据未接入</td></tr>';
  }

  function openVehicleDay(date) {
    state.selectedDate = date;
    state.statusFilter = 'all';
    state.visualDetail = null;
    renderVehicleDrawer();
    $('#vehicle-drawer').classList.add('open');
    $('#vehicle-drawer').setAttribute('aria-hidden', 'false');
    document.querySelector('.drawer-backdrop').classList.add('open');
  }

  function closeVehicleDrawer() {
    $('#vehicle-drawer').classList.remove('open');
    $('#vehicle-drawer').setAttribute('aria-hidden', 'true');
    document.querySelector('.drawer-backdrop').classList.remove('open');
  }

  function renderVehicleDrawer() {
    const date = state.selectedDate;
    const rows = (state.currentView?.vehicle_daily_status || []).filter((item) => item.date === date);
    const counts = rows.reduce((acc, item) => {
      const key = item.status || 'unknown';
      acc[key] = (acc[key] || 0) + 1;
      acc.all += 1;
      return acc;
    }, { all: 0, active: 0, idle: 0, abnormal: 0, unknown: 0 });
    $('#drawer-title').textContent = `${date} 车辆状态`;
    $('#drawer-subtitle').textContent = `共 ${counts.all} 台车；点击状态筛选当天明细`;
    $('#drawer-summary').innerHTML = statusOrder.slice(1).map((status) => `<div class="drawer-summary-item"><span>${statusLabels[status]}</span><strong>${counts[status] || 0}</strong></div>`).join('') + `<div class="drawer-summary-item"><span>总车辆</span><strong>${counts.all}</strong></div>`;
    $('#drawer-visualization').innerHTML = vehicleVisualization(rows, counts);
    renderVisualDetailPanel();
    $('#drawer-status-filter').innerHTML = statusOrder.map((status) => `<button type="button" class="${state.statusFilter === status ? 'active' : ''}" data-status-filter="${status}">${statusLabels[status]} ${counts[status] || 0}</button>`).join('');
    const filtered = state.statusFilter === 'all' ? rows : rows.filter((item) => item.status === state.statusFilter);
    $('#drawer-vehicle-body').innerHTML = filtered.map((item) => `<tr><td>${escapeHtml(item.car_number)}</td><td>${statusPill(item.status, item.status_label)}</td><td class="left">${escapeHtml(join(item.tasks))}</td><td>${escapeHtml(join(item.drivers))}</td><td>${escapeHtml(join(item.shift_tables))}</td><td>${escapeHtml(join(item.sensors))}</td><td class="left">${escapeHtml(item.status_reason || '-')}</td><td>${escapeHtml(join(item.sources))}:${escapeHtml(join(item.source_lines))}</td></tr>`).join('') || '<tr><td colspan="8" class="empty">暂无车辆明细</td></tr>';
  }

  function vehicleVisualization(rows, counts) {
    const available = Number(counts.active || 0) + Number(counts.idle || 0);
    const problem = Number(counts.abnormal || 0) + Number(counts.unknown || 0);
    const columns = [
      ['总车辆数', counts.all || 0, 'fill-total'],
      ['可用车', available, 'fill-available'],
      ['实际出车', counts.active || 0, 'fill-active'],
      ['空闲车辆', counts.idle || 0, 'fill-idle'],
      ['问题车辆', problem, 'fill-problem'],
    ];
    const taskRows = topVehicleTasks(rows);
    const problemRows = topVehicleProblems(rows);
    const shiftCounts = vehicleShiftCounts(rows);
    const maxColumn = Math.max(...columns.map((item) => Number(item[1] || 0)), 1);
    return `<section class="vehicle-visual" aria-label="车辆状态概览"><div class="visual-title">车辆状态概览</div><div class="visual-columns">${columns.map(([label, value, cls]) => {
      const height = Math.max(Number(value || 0) / maxColumn * 100, value ? 4 : 0);
      return `<div class="visual-column"><div class="visual-column-box"><div class="visual-column-fill ${cls}" style="height:${height}%"></div><div class="visual-column-value">${escapeHtml(value)}</div></div><div class="visual-column-label">${escapeHtml(label)}</div></div>`;
    }).join('')}</div>${shiftBars(shiftCounts)}<div class="visual-charts"><div class="visual-chart"><div class="visual-chart-title">出车任务明细（按出车数倒序）</div>${visualBarRows(taskRows, 'visual-task', '暂无出车任务')}</div><div class="visual-chart"><div class="visual-chart-title">问题车辆明细（按问题数倒序）</div>${visualBarRows(problemRows, 'visual-problem', '暂无问题车辆')}</div></div></section>`;
  }

  function vehicleShiftCounts(rows) {
    const counts = { white: 0, night: 0 };
    rows.filter((item) => item.status === 'active').forEach((item) => {
      const shiftText = join(item.shift_tables);
      if (shiftText.includes('白')) counts.white += 1;
      if (shiftText.includes('夜')) counts.night += 1;
    });
    return counts;
  }

  function shiftBars(counts) {
    const maxValue = Math.max(Number(counts.white || 0), Number(counts.night || 0), 1);
    const items = [
      ['白班出车车辆', counts.white || 0, 'shift-white'],
      ['夜班出车车辆', counts.night || 0, 'shift-night'],
    ];
    return `<div class="shift-bars" aria-label="白班夜班出车车辆">${items.map(([label, value, cls]) => {
      const width = Math.max(Number(value || 0) / maxValue * 100, value ? 4 : 0);
      return `<div class="shift-bar-card"><div class="shift-bar-label">${escapeHtml(label)}</div><div class="shift-bar-track"><div class="shift-bar-fill ${cls}" style="width:${width}%">${escapeHtml(value)}</div></div></div>`;
    }).join('')}</div>`;
  }

  function shiftBars(counts) {
    const white = Number(counts.white || 0);
    const night = Number(counts.night || 0);
    const total = white + night;
    const whiteWidth = total ? (white / total * 100) : 0;
    const nightWidth = total ? (night / total * 100) : 0;
    const segment = (label, value, width, cls) => {
      if (!value) return '';
      return `<div class="shift-bar-segment ${cls}" style="width:${width}%">${escapeHtml(label)} ${escapeHtml(value)}</div>`;
    };
    const track = total
      ? `${segment('白班', white, whiteWidth, 'shift-white')}${segment('夜班', night, nightWidth, 'shift-night')}`
      : '<div class="shift-bar-segment is-empty">暂无出车车辆</div>';
    return `<div class="shift-bars" aria-label="白班夜班出车车辆"><div class="shift-bar-card shift-combined-card"><div class="shift-bar-head"><span class="shift-bar-label">白班 / 夜班出车车辆</span><strong>${escapeHtml(total)}</strong></div><div class="shift-bar-track shift-combined-track">${track}</div><div class="shift-bar-legend"><span><i class="shift-dot shift-white"></i>白班 ${escapeHtml(white)}</span><span><i class="shift-dot shift-night"></i>夜班 ${escapeHtml(night)}</span></div></div></div>`;
  }

  function topVehicleTasks(rows) {
    const counts = new Map();
    rows.filter((item) => item.status === 'active').forEach((item) => {
      const tasks = Array.isArray(item.tasks) && item.tasks.length ? item.tasks : ['未标注任务'];
      tasks.forEach((task) => {
        const label = String(task || '未标注任务').trim() || '未标注任务';
        const item = counts.get(label) || { label, value: 0, kind: 'task' };
        item.value += 1;
        counts.set(label, item);
      });
    });
    return mapToSortedRows(counts, 10);
  }

  function topVehicleProblems(rows) {
    const counts = new Map();
    rows.filter((item) => item.status === 'abnormal' || item.status === 'unknown').forEach((item) => {
      const label = String(item.status_reason || item.status_label || statusLabels[item.status] || '未标注问题').trim() || '未标注问题';
      const row = counts.get(label) || { label, value: 0, kind: 'problem' };
      row.value += 1;
      counts.set(label, row);
    });
    return mapToSortedRows(counts, 8);
  }

  function mapToSortedRows(map, limit) {
    return Array.from(map.values()).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, 'zh-CN')).slice(0, limit);
  }

  function visualBarRows(rows, cls, emptyText) {
    if (!rows.length) return `<div class="empty">${escapeHtml(emptyText)}</div>`;
    const maxValue = Math.max(...rows.map((item) => Number(item.value || 0)), 1);
    return rows.map((item) => {
      const width = Math.max(Number(item.value || 0) / maxValue * 100, 4);
      return `<button class="visual-bar-row" type="button" data-detail-kind="${escapeHtml(item.kind)}" data-detail-label="${escapeHtml(item.label)}"><span class="visual-bar-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</span><span class="visual-bar-track"><span class="visual-bar-fill ${cls}" style="width:${width}%"></span></span><span class="visual-bar-value">${escapeHtml(item.value)}</span></button>`;
    }).join('');
  }

  function renderVisualDetailPanel() {
    const panel = $('#visual-detail-panel');
    if (!panel) return;
    const detail = state.visualDetail;
    if (!detail || !detail.label) {
      panel.innerHTML = '';
      return;
    }
    const rows = visualDetailRows(detail);
    const title = detail.kind === 'problem' ? '问题车辆明细' : '出车任务车辆明细';
    panel.innerHTML = `<section class="visual-detail-panel"><div class="visual-detail-head"><div><div class="visual-detail-title">${escapeHtml(title)}：${escapeHtml(detail.label)}</div><div class="visual-detail-sub">共 ${rows.length} 台车，点击右侧关闭可返回总览</div></div><button class="link-button" type="button" data-action="clear-visual-detail">关闭</button></div><div class="table-wrap"><table><thead><tr><th>车号</th><th>状态</th><th>任务</th><th>司机</th><th>班次</th><th>原因</th></tr></thead><tbody>${rows.map((item) => `<tr><td>${escapeHtml(item.car_number || '-')}</td><td>${statusPill(item.status, item.status_label)}</td><td class="left">${escapeHtml(join(item.tasks))}</td><td>${escapeHtml(join(item.drivers))}</td><td>${escapeHtml(join(item.shift_tables))}</td><td class="left">${escapeHtml(item.status_reason || '-')}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">暂无匹配车辆</td></tr>'}</tbody></table></div></section>`;
  }

  function visualDetailRowsForDate(detail, date, sourceRows = data.vehicle_daily_status || []) {
    const rows = sourceRows.filter((item) => item.date === date);
    return visualDetailRowsInRows(detail, rows);
  }

  function visualDetailRowsInRows(detail, rows) {
    if (detail.kind === 'problem') {
      return rows.filter((item) => {
        const label = String(item.status_reason || item.status_label || statusLabels[item.status] || '未标注问题').trim() || '未标注问题';
        return (item.status === 'abnormal' || item.status === 'unknown') && label === detail.label;
      });
    }
    return rows.filter((item) => {
      if (item.status !== 'active') return false;
      const tasks = Array.isArray(item.tasks) && item.tasks.length ? item.tasks : ['未标注任务'];
      return tasks.some((task) => (String(task || '未标注任务').trim() || '未标注任务') === detail.label);
    });
  }

  function visualDetailRows(detail) {
    return visualDetailRowsForDate(detail, state.selectedDate, state.currentView?.vehicle_daily_status || []);
    const rows = (state.currentView?.vehicle_daily_status || []).filter((item) => item.date === state.selectedDate);
    if (detail.kind === 'problem') {
      return rows.filter((item) => {
        const label = String(item.status_reason || item.status_label || statusLabels[item.status] || '未标注问题').trim() || '未标注问题';
        return (item.status === 'abnormal' || item.status === 'unknown') && label === detail.label;
      });
    }
    return rows.filter((item) => {
      if (item.status !== 'active') return false;
      const tasks = Array.isArray(item.tasks) && item.tasks.length ? item.tasks : ['未标注任务'];
      return tasks.some((task) => (String(task || '未标注任务').trim() || '未标注任务') === detail.label);
    });
  }

  function initHumanDateRange() {
    const bounds = data.human_dispatch_date_bounds || data.date_bounds || {};
    const startInput = $('[data-control="human-start-date"]');
    const endInput = $('[data-control="human-end-date"]');
    state.humanStartDate = bounds.min || data.anchor_date || bounds.max || '';
    state.humanEndDate = bounds.max || state.humanStartDate;
    [startInput, endInput].forEach((input) => {
      if (!input) return;
      if (bounds.min) input.min = bounds.min;
      if (bounds.max) input.max = bounds.max;
    });
    if (startInput) startInput.value = state.humanStartDate;
    if (endInput) endInput.value = state.humanEndDate;
    applyHumanDateRange();
  }

  function applyHumanDateRange() {
    const bounds = data.human_dispatch_date_bounds || data.date_bounds || {};
    const startInput = $('[data-control="human-start-date"]');
    const endInput = $('[data-control="human-end-date"]');
    let startDate = startInput?.value || state.humanStartDate || bounds.min || bounds.max || '';
    let endDate = endInput?.value || state.humanEndDate || bounds.max || startDate;
    if (bounds.min && startDate < bounds.min) startDate = bounds.min;
    if (bounds.max && startDate > bounds.max) startDate = bounds.max;
    if (bounds.min && endDate < bounds.min) endDate = bounds.min;
    if (bounds.max && endDate > bounds.max) endDate = bounds.max;
    if (startDate > endDate) {
      [startDate, endDate] = [endDate, startDate];
    }
    state.humanStartDate = startDate;
    state.humanEndDate = endDate;
    if (startInput) startInput.value = startDate;
    if (endInput) endInput.value = endDate;
    state.humanView = buildHumanRangeView(startDate, endDate);
    renderHumanDispatchPage();
  }

  function shiftHumanDateRange(days) {
    const bounds = data.human_dispatch_date_bounds || data.date_bounds || {};
    const [startDate, endDate] = shiftDateRange(state.humanStartDate, state.humanEndDate, days, bounds);
    $('[data-control="human-start-date"]').value = startDate;
    $('[data-control="human-end-date"]').value = endDate;
    applyHumanDateRange();
  }

  function buildHumanRangeView(startDate, endDate) {
    const schedules = (data.human_dispatch_schedule_records || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const outputs = (data.human_dispatch_output_records || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const vehicles = (data.human_dispatch_vehicle_daily_status || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const risks = (data.human_dispatch_risks || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const summary = buildHumanSummary(schedules, outputs, vehicles, risks);
    return {
      current_period: { start_date: startDate, end_date: endDate },
      schedule_records: schedules,
      output_records: outputs,
      vehicle_daily_status: vehicles,
      risks,
      summary,
      daily_series: buildHumanDailySeries(schedules, outputs, vehicles),
      task_rankings: buildHumanTaskRankings(schedules),
      output_rankings: buildHumanOutputRankings(outputs),
    };
  }

  function buildHumanSummary(schedules, outputs, vehicles, risks) {
    const drivers = splitHumanPeople(schedules.map((item) => item.driver));
    const collectors = unique(outputs.map((item) => item.collector));
    const vehicleNumbers = unique([
      ...schedules.map((item) => item.car_number),
      ...outputs.map((item) => item.car_number),
      ...vehicles.map((item) => item.car_number),
    ]);
    const status = vehicles.reduce((acc, item) => {
      const key = item.status || 'unknown';
      acc[`${key}_count`] = (acc[`${key}_count`] || 0) + 1;
      return acc;
    }, { active_count: 0, idle_count: 0, abnormal_count: 0, unknown_count: 0 });
    const durationMinutes = outputs.reduce((sum, item) => sum + Number(item.duration_minutes || 0), 0);
    const mileage = outputs.reduce((sum, item) => sum + Number(item.mileage_km || 0), 0);
    return {
      schedule_count: schedules.length,
      output_count: outputs.length,
      vehicle_count: vehicleNumbers.length,
      driver_count: drivers.length,
      collector_count: collectors.length,
      people_count: unique([...drivers, ...collectors]).length,
      output_hours: Number((durationMinutes / 60).toFixed(2)),
      output_mileage_km: Number(mileage.toFixed(2)),
      risk_count: risks.length,
      date_min: state.humanStartDate || '',
      date_max: state.humanEndDate || '',
      ...status,
    };
  }

  function buildHumanDailySeries(schedules, outputs, vehicles) {
    const grouped = new Map();
    const itemFor = (date) => {
      if (!grouped.has(date)) {
        grouped.set(date, {
          date,
          schedule_count: 0,
          output_count: 0,
          output_hours: 0,
          output_mileage_km: 0,
          vehicle_count: 0,
          active_count: 0,
          idle_count: 0,
          abnormal_count: 0,
          unknown_count: 0,
          vehicles: new Set(),
        });
      }
      return grouped.get(date);
    };
    schedules.forEach((row) => {
      if (!row.date) return;
      const item = itemFor(row.date);
      item.schedule_count += 1;
      if (row.car_number) item.vehicles.add(String(row.car_number));
    });
    outputs.forEach((row) => {
      if (!row.date) return;
      const item = itemFor(row.date);
      item.output_count += 1;
      item.output_hours += Number(row.duration_minutes || 0) / 60;
      item.output_mileage_km += Number(row.mileage_km || 0);
      if (row.car_number) item.vehicles.add(String(row.car_number));
    });
    vehicles.forEach((row) => {
      if (!row.date) return;
      const item = itemFor(row.date);
      if (row.car_number) item.vehicles.add(String(row.car_number));
      const key = `${row.status || 'unknown'}_count`;
      if (key in item) item[key] += 1;
    });
    return Array.from(grouped.values()).map((item) => ({
      ...item,
      vehicle_count: item.vehicles.size,
      output_hours: Number(item.output_hours.toFixed(2)),
      output_mileage_km: Number(item.output_mileage_km.toFixed(2)),
      vehicles: undefined,
    })).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }

  function buildHumanTaskRankings(schedules) {
    const grouped = new Map();
    schedules.forEach((row) => {
      const task = String(row.task || '未标注任务').trim() || '未标注任务';
      if (!grouped.has(task)) grouped.set(task, { task, record_count: 0, vehicles: new Set(), drivers: new Set() });
      const item = grouped.get(task);
      item.record_count += 1;
      if (row.car_number) item.vehicles.add(String(row.car_number));
      splitHumanPeople([row.driver]).forEach((driver) => item.drivers.add(driver));
    });
    return Array.from(grouped.values()).map((item) => ({
      task: item.task,
      record_count: item.record_count,
      vehicle_count: item.vehicles.size,
      driver_count: item.drivers.size,
    })).sort((a, b) => b.driver_count - a.driver_count || b.vehicle_count - a.vehicle_count || b.record_count - a.record_count || a.task.localeCompare(b.task, 'zh-CN')).slice(0, 12);
  }

  function buildHumanOutputRankings(outputs) {
    const grouped = new Map();
    outputs.forEach((row) => {
      const label = String(row.route || row.scene || '未标注路线').trim() || '未标注路线';
      if (!grouped.has(label)) grouped.set(label, { label, record_count: 0, duration_minutes: 0, mileage_km: 0 });
      const item = grouped.get(label);
      item.record_count += 1;
      item.duration_minutes += Number(row.duration_minutes || 0);
      item.mileage_km += Number(row.mileage_km || 0);
    });
    return Array.from(grouped.values()).map((item) => ({
      label: item.label,
      record_count: item.record_count,
      output_hours: Number((item.duration_minutes / 60).toFixed(2)),
      mileage_km: Number(item.mileage_km.toFixed(2)),
    })).sort((a, b) => b.mileage_km - a.mileage_km || b.output_hours - a.output_hours || a.label.localeCompare(b.label, 'zh-CN')).slice(0, 12);
  }

  function splitHumanPeople(values) {
    return unique(values.flatMap((value) => String(value || '').split(/[、,，;；/\\s]+/).map((item) => item.trim()).filter(Boolean)));
  }

  function renderHumanDispatchPage() {
    const view = state.humanView || buildHumanRangeView(state.humanStartDate, state.humanEndDate);
    const summary = view.summary || {};
    const period = view.current_period?.start_date && view.current_period?.end_date ? `${view.current_period.start_date} 至 ${view.current_period.end_date}` : '暂无日期';
    $('#human-dispatch-meta').innerHTML = `<span>${escapeHtml(period)}</span><span>排班 ${escapeHtml(summary.schedule_count || 0)}</span><span>产出 ${escapeHtml(summary.output_count || 0)}</span>`;
    const note = $('#human-range-note');
    if (note) note.textContent = period;
    const cards = [
      ['排班记录', summary.schedule_count || 0, '青岛人驾排班', 'is-work'],
      ['车辆数', summary.vehicle_count || 0, `活跃 ${summary.active_count || 0} / 空闲 ${summary.idle_count || 0}`, 'is-good'],
      ['司机/采集员', summary.people_count || 0, `司机 ${summary.driver_count || 0} / 采集员 ${summary.collector_count || 0}`, ''],
      ['产出小时', `${formatNumber(summary.output_hours || 0)}h`, '盐城实际采集', 'is-idle'],
      ['产出里程', `${formatNumber(summary.output_mileage_km || 0)}km`, '盐城实际采集', 'is-good'],
      ['异常备注', summary.risk_count || 0, '排班与产出合并', 'is-risk'],
    ];
    $('#human-kpi-grid').innerHTML = cards.map(([label, value, sub, cls]) => `<div class="dispatch-kpi ${cls}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub)}</small></div>`).join('');
    $('#human-daily-trend').innerHTML = humanDailyTrendRows(view);
    $('#human-task-ranking').innerHTML = humanTaskRankingRows(view);
    $('#human-output-ranking').innerHTML = humanOutputRankingRows(view);
    $('#human-risk-list').innerHTML = humanRiskRows(view);
    renderHumanScheduleTable(view);
    renderHumanOutputTable(view);
  }

  function humanDailyTrendRows(view = state.humanView) {
    const rows = (view?.daily_series || []).slice(0, 14);
    if (!rows.length) return '<div class="dispatch-empty">暂无人驾趋势数据</div>';
    return rows.map((item) => {
      const total = Math.max(Number(item.vehicle_count || 0), Number(item.schedule_count || 0), 1);
      const pct = (value) => `${(Number(value || 0) / total * 100).toFixed(2)}%`;
      const meta = `${formatNumber(item.output_hours || 0)}h / ${formatNumber(item.output_mileage_km || 0)}km`;
      return `<div class="human-chart-row"><div class="human-chart-label">${escapeHtml(item.date)}</div><div class="human-track"><span class="human-seg-active" style="width:${pct(item.active_count)}"></span><span class="human-seg-idle" style="width:${pct(item.idle_count)}"></span><span class="human-seg-abnormal" style="width:${pct(item.abnormal_count)}"></span><span class="human-seg-unknown" style="width:${pct(item.unknown_count)}"></span></div><div class="human-chart-meta">${escapeHtml(meta)}</div></div>`;
    }).join('');
  }

  function humanTaskRankingRows(view = state.humanView) {
    const rows = view?.task_rankings || [];
    if (!rows.length) return '<div class="dispatch-empty">暂无人驾任务数据</div>';
    const maxValue = Math.max(...rows.map((item) => Number(item.record_count || 0)), 1);
    return rows.map((item) => {
      const width = Math.max(Number(item.record_count || 0) / maxValue * 100, 4);
      const meta = `${item.record_count} 条 / ${item.vehicle_count} 车 / ${item.driver_count} 人`;
      return `<div class="human-rank-row"><div class="human-chart-label" title="${escapeHtml(item.task)}">${escapeHtml(item.task)}</div><div class="human-rank-bar"><div class="human-rank-fill" style="width:${width}%"></div></div><div class="human-chart-meta">${escapeHtml(meta)}</div></div>`;
    }).join('');
  }

  function humanOutputRankingRows(view = state.humanView) {
    const rows = view?.output_rankings || [];
    if (!rows.length) return '<div class="dispatch-empty">暂无盐城产出数据</div>';
    const maxValue = Math.max(...rows.map((item) => Number(item.mileage_km || 0)), 1);
    return rows.map((item) => {
      const width = Math.max(Number(item.mileage_km || 0) / maxValue * 100, 4);
      const meta = `${formatNumber(item.mileage_km)}km / ${formatNumber(item.output_hours)}h`;
      return `<div class="human-rank-row"><div class="human-chart-label" title="${escapeHtml(item.label)}">${escapeHtml(item.label)}</div><div class="human-rank-bar"><div class="human-output-fill" style="width:${width}%"></div></div><div class="human-chart-meta">${escapeHtml(meta)}</div></div>`;
    }).join('');
  }

  function humanRiskRows(view = state.humanView) {
    const risks = (view?.risks || []).slice(0, 18);
    if (!risks.length) return '<div class="dispatch-empty">暂无人驾异常备注</div>';
    return risks.map((item) => `<div class="human-risk"><div class="human-risk-type">${escapeHtml(item.type)}</div><div><strong>${escapeHtml(item.target || '-')}</strong><small>${escapeHtml([item.date, item.site, `${item.source || '-'}:${item.source_line || ''}`].filter(Boolean).join(' / '))}</small><div>${escapeHtml(item.message || '-')}</div></div></div>`).join('');
  }

  function renderHumanScheduleTable(view = state.humanView) {
    const rows = view?.schedule_records || [];
    $('#human-schedule-body').innerHTML = rows.map((item) => `<tr><td>${escapeHtml(item.date || '-')}</td><td class="left">${escapeHtml(item.task || '-')}</td><td>${escapeHtml(item.shift || '-')}</td><td>${escapeHtml(item.car_number || '-')}</td><td>${escapeHtml(item.driver || '-')}</td><td>${escapeHtml(item.departure_time || '-')}</td><td class="left">${escapeHtml(item.exception_note || '-')}</td><td>${escapeHtml(item.source || '-')}：${escapeHtml(item.source_line || '')}</td></tr>`).join('') || '<tr><td colspan="8" class="empty">暂无青岛排班明细</td></tr>';
  }

  function renderHumanOutputTable(view = state.humanView) {
    const rows = view?.output_records || [];
    $('#human-output-body').innerHTML = rows.map((item) => `<tr><td>${escapeHtml(item.date || '-')}</td><td>${escapeHtml(item.car_number || '-')}</td><td>${escapeHtml(item.collector || '-')}</td><td class="left">${escapeHtml(item.scene || '-')}</td><td class="left">${escapeHtml(item.route || '-')}</td><td>${escapeHtml(item.start_time || '-')}</td><td>${escapeHtml(item.end_time || '-')}</td><td>${escapeHtml(formatNumber(item.duration_minutes || 0))}min</td><td>${escapeHtml(formatNumber(item.mileage_km || 0))}km</td><td>${escapeHtml(item.is_collected || '-')}</td><td class="left">${escapeHtml(item.exception_note || '-')}</td><td>${escapeHtml(item.source || '-')}：${escapeHtml(item.source_line || '')}</td></tr>`).join('') || '<tr><td colspan="12" class="empty">暂无盐城产出明细</td></tr>';
  }

  function initWeeklyControls() {
    const reports = data.weekly_reports || [];
    const currentSelect = $('[data-control="weekly-current"]');
    const compareSelect = $('[data-control="weekly-compare"]');
    const options = reports.map((item) => `<option value="${escapeHtml(item.week_id)}">${escapeHtml(item.week_id)} ${escapeHtml(item.period?.start_date || '')} ~ ${escapeHtml(item.period?.end_date || '')}</option>`).join('');
    currentSelect.innerHTML = options;
    compareSelect.innerHTML = options;
    state.weeklyCurrent = reports[0]?.week_id || null;
    state.weeklyCompare = reports[1]?.week_id || reports[0]?.week_id || null;
    if (state.weeklyCurrent) currentSelect.value = state.weeklyCurrent;
    if (state.weeklyCompare) compareSelect.value = state.weeklyCompare;
  }

  function applyWeeklyCompare() {
    state.weeklyCurrent = $('[data-control="weekly-current"]').value || state.weeklyCurrent;
    state.weeklyCompare = $('[data-control="weekly-compare"]').value || state.weeklyCompare;
    renderWeeklyPage();
  }

  function renderWeeklyPage() {
    const reports = data.weekly_reports || [];
    const empty = $('#weekly-empty');
    if (!reports.length) {
      empty.style.display = 'block';
      $('#weekly-meta').textContent = '暂无周报数据';
      $('#weekly-kpi-grid').innerHTML = '';
      $('#weekly-top-task-body').innerHTML = '<tr><td colspan="6" class="empty">暂无周报数据</td></tr>';
      $('#weekly-stability-body').innerHTML = '<tr><td colspan="4" class="empty">暂无周报数据</td></tr>';
      return;
    }
    empty.style.display = 'none';
    const current = findWeeklyReport(state.weeklyCurrent) || reports[0];
    const compare = findWeeklyReport(state.weeklyCompare) || reports[1] || current;
    const currentPeriod = current.period || {};
    const comparePeriod = compare.period || {};
    const kpis = current.kpis || {};
    const compareKpis = compare.kpis || {};
    $('#weekly-meta').innerHTML = `<span>${escapeHtml(current.week_id || '-')}</span><span>${escapeHtml(currentPeriod.start_date || '-')} 至 ${escapeHtml(currentPeriod.end_date || '-')}</span><span>可选 ${reports.length} 个周报</span>`;
    $('#weekly-compare-note').textContent = `${current.week_id} 对比 ${compare.week_id}`;
    const cards = [
      ['周出勤人次', kpis.total_attendance ?? 0, compareKpis.total_attendance ?? 0, '每日去重累计', 'blue'],
      ['出车人数', kpis.unique_drivers ?? 0, compareKpis.unique_drivers ?? 0, '周内唯一 SD', 'cyan'],
      ['SD 个数/天', kpis.avg_daily_sd ?? 0, compareKpis.avg_daily_sd ?? 0, '有数据天均值', 'green'],
      ['任务类型', kpis.task_types ?? 0, compareKpis.task_types ?? 0, '采集任务数', 'orange'],
      ['活跃车日', kpis.active_vehicle_days ?? 0, compareKpis.active_vehicle_days ?? 0, '按车辆日统计', 'purple'],
      ['异常车日', kpis.abnormal_vehicle_days ?? 0, compareKpis.abnormal_vehicle_days ?? 0, '按车辆日统计', 'red'],
    ];
    $('#weekly-kpi-grid').innerHTML = cards.map(([label, value, baseline, sub, tone]) => {
      const delta = Number(value || 0) - Number(baseline || 0);
      return `<div class="card kpi tone-${tone}"><div class="kpi-label">${escapeHtml(label)}</div><div class="kpi-value">${escapeHtml(formatNumber(value))}</div><div class="kpi-sub">${escapeHtml(sub)}；对比 ${escapeHtml(formatNumber(baseline))}；变化 <span class="${deltaClass(delta)}">${escapeHtml(formatSigned(delta))}</span></div></div>`;
    }).join('');
    $('#weekly-top-task-body').innerHTML = weeklyTopTaskRows(current, compare) || '<tr><td colspan="6" class="empty">暂无 Top5 任务</td></tr>';
    $('#weekly-stability-body').innerHTML = weeklyPersonnelRows(current, compare) || '<tr><td colspan="4" class="empty">暂无任务参与覆盖数据</td></tr>';
  }

  function findWeeklyReport(weekId) {
    return (data.weekly_reports || []).find((item) => item.week_id === weekId);
  }

  function weeklyTopTaskRows(current, compare) {
    const compareByTask = new Map((compare.top5_tasks || []).map((item) => [item.task, item]));
    return (current.top5_tasks || []).map((item, index) => {
      const baseline = compareByTask.get(item.task)?.current_total || 0;
      const delta = Number(item.current_total || 0) - Number(baseline || 0);
      return `<tr><td>${index + 1}</td><td class="left">${escapeHtml(item.task)}</td><td>${escapeHtml(item.current_total || 0)}</td><td>${escapeHtml(baseline)}</td><td class="${deltaClass(delta)}">${escapeHtml(formatSigned(delta))}</td><td>${escapeHtml(item.white || 0)}/${escapeHtml(item.night || 0)}</td></tr>`;
    }).join('');
  }

  function weeklyPersonnelRows(current, compare) {
    const compareByTask = new Map((compare.personnel_stability || []).map((item) => [item.task, item]));
    return (current.personnel_stability || []).map((item) => {
      const currentCount = Number(item.driver_count || item.continued_driver_count || 0);
      const baseline = Number(compareByTask.get(item.task)?.driver_count || compareByTask.get(item.task)?.continued_driver_count || 0);
      const delta = currentCount - baseline;
      return `<tr><td class="left">${escapeHtml(item.task)}</td><td>${escapeHtml(currentCount)}</td><td>${escapeHtml(baseline)}</td><td class="${deltaClass(delta)}">${escapeHtml(formatSigned(delta))}</td></tr>`;
    }).join('');
  }

  function deltaClass(value) {
    if (Number(value) > 0) return 'delta-up';
    if (Number(value) < 0) return 'delta-down';
    return 'delta-flat';
  }

  function formatSigned(value) {
    const number = Number(value || 0);
    return `${number > 0 ? '+' : ''}${formatNumber(number)}`;
  }

  function clampDateRange(startDate, endDate, bounds = {}) {
    let start = startDate || bounds.min || bounds.max || '';
    let end = endDate || start;
    if (start > end) [start, end] = [end, start];
    if (bounds.min && start < bounds.min) start = bounds.min;
    if (bounds.max && end > bounds.max) end = bounds.max;
    if (bounds.min && end < bounds.min) end = bounds.min;
    if (bounds.max && start > bounds.max) start = bounds.max;
    if (start > end) [start, end] = [end, start];
    return [start, end];
  }

  function shiftDateRange(startDate, endDate, days, bounds = {}) {
    const start = parseDate(startDate);
    const end = parseDate(endDate || startDate);
    if (!start || !end) return clampDateRange(startDate, endDate, bounds);
    const spanDays = Math.max(Math.round((end - start) / 86400000), 0);
    let nextStart = addDays(start, days);
    let nextEnd = addDays(end, days);
    const minDate = parseDate(bounds.min);
    const maxDate = parseDate(bounds.max);
    if (minDate && nextStart < minDate) {
      nextStart = minDate;
      nextEnd = addDays(nextStart, spanDays);
    }
    if (maxDate && nextEnd > maxDate) {
      nextEnd = maxDate;
      nextStart = addDays(nextEnd, -spanDays);
    }
    return clampDateRange(formatDate(nextStart), formatDate(nextEnd), bounds);
  }

  function previousRangeBounds(startDate, endDate) {
    const start = parseDate(startDate);
    const end = parseDate(endDate);
    if (!start || !end) return { start: startDate, end: endDate };
    const dayCount = Math.max(Math.round((end - start) / 86400000) + 1, 1);
    const previousEnd = addDays(start, -1);
    const previousStart = addDays(previousEnd, 1 - dayCount);
    return { start: formatDate(previousStart), end: formatDate(previousEnd) };
  }
  function parseDate(value) {
    const match = String(value || '').match(/^(\\d{4})-(\\d{2})-(\\d{2})$/);
    if (!match) return null;
    return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  }
  function addDays(date, days) {
    const next = new Date(date.getTime());
    next.setUTCDate(next.getUTCDate() + days);
    return next;
  }
  function formatDate(date) {
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
  }
  boot();
})();
</script>
</body>
</html>
"""
