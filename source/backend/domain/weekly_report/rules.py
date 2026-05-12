"""Deterministic rules for the weekly SD collection report.

The implementation mirrors the legacy ``report_web.html`` parser:
- row 2 is the header row, row 3+ are data rows;
- date and collection task are inherited downward;
- driver candidates are scanned around the 出车人SD column;
- departure times are bound to driver names by order;
- white/night shift is inferred from departure time.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable

TIME_RE = re.compile(r"(\d{1,2})[：:](\d{2})")
DATE_RE = re.compile(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})")
UNKNOWN_TASK = "未知任务"


@dataclass(frozen=True)
class WeeklyRecord:
    date: str
    location: str
    task: str
    shift_table: str
    sensor: str
    car_number: str
    driver: str
    raw_driver: str
    departure_time: str
    all_departure_times: str
    shift: str
    raw_departure_time: str
    total_collection: float
    effective_time: float
    source: str
    source_line: int
    row_index: int
    candidate_index: int
    driver_col: int
    time_col: int


def build_weekly_report(
    raw_paths: Iterable[str | Path],
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    manifest: list[dict[str, Any]] | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Parse raw CSV files and return the complete structured report payload."""
    raw_path_list = [Path(path) for path in raw_paths]
    records, diagnostics = parse_weekly_records(raw_path_list)
    summary = summarize_weekly_records(records, start_date=start_date, end_date=end_date)
    summary["diagnostics"] = diagnostics
    summary["diagnostics_count"] = len(diagnostics)
    summary["source_files"] = [_source_file_info(path) for path in raw_path_list]
    summary["sources_manifest"] = manifest or []
    summary["week_id"] = week_id
    summary["period"] = {
        "start_date": _date_to_text(start_date),
        "end_date": _date_to_text(end_date),
    }
    summary["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return summary


def attach_week_over_week_comparison(
    report: dict[str, Any],
    previous_report: dict[str, Any] | None,
    *,
    authority_summary: dict[str, Any] | None = None,
    previous_authority_summary: dict[str, Any] | None = None,
    history_report: dict[str, Any] | None = None,
    rolling_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach the concise week-over-week metrics the weekly push should focus on."""
    previous_report = previous_report or {}
    report["person_attendance_summary"] = _build_person_attendance_summary(report.get("records", []) or [])
    resource = _resource_status_from_authority(
        report,
        previous_report,
        authority_summary=authority_summary,
        previous_authority_summary=previous_authority_summary,
    )

    previous_task_by_name = {item.get("task"): {**item, "rank": index + 1} for index, item in enumerate(previous_report.get("task_summary", []))}
    top_tasks = []
    for index, item in enumerate((report.get("task_summary") or [])[:5], 1):
        task_name = item.get("task")
        previous_item = previous_task_by_name.get(task_name, {})
        current_value = int(item.get("total") or 0)
        previous_value = int(previous_item.get("total") or 0)
        top_tasks.append(
            {
                "rank": index,
                "task": task_name,
                "current_total": current_value,
                "previous_total": previous_value,
                "delta": current_value - previous_value,
                "delta_pct": _pct_delta(current_value, previous_value),
                "previous_rank": previous_item.get("rank"),
                "white": item.get("white", 0),
                "night": item.get("night", 0),
                "driver_count": item.get("driver_count", 0),
                "attendance_days": item.get("attendance_days", 0),
            }
        )

    scheduling_control = _build_scheduling_control(
        report,
        top_tasks,
        previous_report=previous_report,
        history_report=history_report or previous_report,
        rolling_report=rolling_report or report,
    )

    report["focus_summary"] = {
        "resource_collection_status": resource,
        "top5_tasks": top_tasks,
        "top3_tasks": top_tasks[:3],
        **scheduling_control,
        "previous_period": previous_report.get("period", {}),
        "previous_week_id": previous_report.get("week_id"),
    }
    return report


def _build_scheduling_control(
    report: dict[str, Any],
    top_tasks: list[dict[str, Any]],
    *,
    previous_report: dict[str, Any],
    history_report: dict[str, Any],
    rolling_report: dict[str, Any],
) -> dict[str, Any]:
    current_records = report.get("records", []) or []
    previous_records = previous_report.get("records", []) or []
    history_records = history_report.get("records", []) or []
    rolling_records = rolling_report.get("records", []) or []
    task_volume_tiers = _build_task_volume_tiers(top_tasks)
    focus_task_names = _focus_task_names(task_volume_tiers, top_tasks)
    candidates_by_task = _stable_candidates_by_task(history_records)

    details = [
        _build_task_scheduling_detail(
            task,
            [record for record in current_records if record.get("task") == task],
            candidates_by_task.get(task, {}),
        )
        for task in focus_task_names
    ]
    focus_records = [record for record in current_records if record.get("task") in focus_task_names]
    rolling_focus_records = [record for record in rolling_records if record.get("task") in focus_task_names]
    top_task_personnel_stability = [
        _build_task_personnel_stability(
            task,
            [record for record in current_records if record.get("task") == task],
            [record for record in previous_records if record.get("task") == task],
        )
        for task in focus_task_names
    ]
    top_task_daily_personnel_matrix = [
        _build_task_daily_personnel_matrix(
            task,
            [record for record in current_records if record.get("task") == task],
        )
        for task in focus_task_names
    ]

    stable_coverage = _stable_record_share(focus_records, candidates_by_task)
    temporary_share = _round_rate(1 - stable_coverage if focus_records else 0)
    daily_median = _median_rate([day["stable_coverage"] for detail in details for day in detail["daily_details"]])
    continuity = _median_rate([detail["adjacent_active_day_continuity"] for detail in details if detail["adjacent_active_day_continuity"] is not None])
    rolling_stable_coverage = _stable_record_share(rolling_focus_records, candidates_by_task) if rolling_focus_records else stable_coverage

    components = {
        "rolling_stable_coverage": {
            "label": "近4周稳定参与者覆盖率",
            "value": rolling_stable_coverage,
            "weight": 0.4,
        },
        "daily_stable_coverage_median": {
            "label": "本周每日稳定覆盖率中位数",
            "value": daily_median,
            "weight": 0.25,
        },
        "low_temporary_share": {
            "label": "低临时参与者占比",
            "value": _round_rate(1 - temporary_share if focus_records else 0),
            "weight": 0.2,
        },
        "adjacent_active_day_continuity": {
            "label": "相邻活跃日延续率",
            "value": continuity,
            "weight": 0.15,
        },
    }
    score = int(round(sum(item["value"] * item["weight"] * 100 for item in components.values())))
    status = _scheduling_status(score)

    return {
        "scheduling_control_overview": {
            "status": status,
            "score": score,
            "focus_task_count": len(focus_task_names),
            "focus_pool_total": len(focus_records),
            "stable_candidate_coverage": stable_coverage,
            "temporary_participant_share": temporary_share,
            "daily_stable_coverage_median": daily_median,
            "adjacent_active_day_continuity": continuity,
        },
        "task_volume_tiers": task_volume_tiers,
        "scheduling_control_index": {
            "score": score,
            "status": status,
            "components": components,
        },
        "scheduling_control_details": details,
        "top_task_personnel_stability": top_task_personnel_stability,
        "top_task_daily_personnel_matrix": top_task_daily_personnel_matrix,
        "robust_metric_notes": [
            "首页使用重点任务池聚合，降低单条任务归属误差对宏观结论的影响。",
            "历史稳定参与者候选来自报告周前28天，不代表真实负责人或组织角色。",
            "首页使用中位数、区间状态和任务量级分层，不按单任务细微排名做精确判断。",
        ],
    }


def _build_task_volume_tiers(top_tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    total = sum(int(item.get("current_total") or 0) for item in top_tasks)
    tiers: dict[str, list[dict[str, Any]]] = {"high": [], "medium": [], "low": []}
    for item in top_tasks:
        current_total = int(item.get("current_total") or 0)
        share = _round_rate(current_total / total) if total else 0
        row = {
            "rank": item.get("rank"),
            "task": item.get("task"),
            "total": current_total,
            "share": share,
            "white": item.get("white", 0),
            "night": item.get("night", 0),
        }
        if share >= 0.15:
            tiers["high"].append(row)
        elif share >= 0.05:
            tiers["medium"].append(row)
        else:
            tiers["low"].append(row)
    return tiers


def _focus_task_names(task_volume_tiers: dict[str, list[dict[str, Any]]], top_tasks: list[dict[str, Any]]) -> list[str]:
    names = [
        str(item.get("task"))
        for item in task_volume_tiers.get("high", []) + task_volume_tiers.get("medium", [])
        if item.get("task")
    ]
    if names:
        return names
    return [str(item.get("task")) for item in top_tasks[:3] if item.get("task")]


def _stable_candidates_by_task(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    stats: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        task = str(record.get("task") or "").strip()
        driver = str(record.get("driver") or "").strip()
        date_text = str(record.get("date") or "").strip()
        if not task or not driver or not date_text:
            continue
        driver_stats = stats.setdefault(task, {}).setdefault(
            driver,
            {"driver": driver, "history_attendance_count": 0, "history_active_dates": set()},
        )
        driver_stats["history_attendance_count"] += 1
        driver_stats["history_active_dates"].add(date_text)

    candidates: dict[str, dict[str, dict[str, Any]]] = {}
    for task, drivers in stats.items():
        for driver, item in drivers.items():
            active_days = len(item["history_active_dates"])
            attendance_count = int(item["history_attendance_count"])
            if active_days >= 2 or attendance_count >= 5:
                candidates.setdefault(task, {})[driver] = {
                    "driver": driver,
                    "history_attendance_count": attendance_count,
                    "history_active_days": active_days,
                }
    return candidates


def _build_task_scheduling_detail(
    task: str,
    records: list[dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stable_drivers = set(candidates)
    daily_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_by_driver: dict[str, int] = defaultdict(int)
    for record in records:
        date_text = str(record.get("date") or "")
        driver = str(record.get("driver") or "")
        if not date_text or not driver:
            continue
        daily_records[date_text].append(record)
        current_by_driver[driver] += 1

    stable_count = sum(1 for record in records if str(record.get("driver") or "") in stable_drivers)
    total = len(records)
    daily_details = []
    for date_text in sorted(daily_records):
        rows = daily_records[date_text]
        stable = sorted({str(row.get("driver")) for row in rows if str(row.get("driver") or "") in stable_drivers})
        temporary = sorted({str(row.get("driver")) for row in rows if str(row.get("driver") or "") not in stable_drivers and row.get("driver")})
        daily_total = len(rows)
        daily_details.append(
            {
                "date": date_text,
                "weekday": _weekday_label(date_text),
                "total": daily_total,
                "stable_coverage": _round_rate(sum(1 for row in rows if str(row.get("driver") or "") in stable_drivers) / daily_total) if daily_total else 0,
                "stable_drivers": stable,
                "temporary_drivers": temporary,
                "white_stable_drivers": _drivers_by_shift(rows, stable_drivers, "白班", stable=True),
                "night_stable_drivers": _drivers_by_shift(rows, stable_drivers, "夜班", stable=True),
                "white_temporary_drivers": _drivers_by_shift(rows, stable_drivers, "白班", stable=False),
                "night_temporary_drivers": _drivers_by_shift(rows, stable_drivers, "夜班", stable=False),
            }
        )

    candidate_rows = []
    for driver, item in candidates.items():
        candidate_rows.append(
            {
                **item,
                "current_attendance_count": current_by_driver.get(driver, 0),
            }
        )
    candidate_rows.sort(key=lambda item: (-item["current_attendance_count"], -item["history_attendance_count"], item["driver"]))

    stable_coverage = _round_rate(stable_count / total) if total else 0
    return {
        "task": task,
        "current_total": total,
        "stable_candidate_count": len(candidates),
        "stable_candidate_drivers": sorted(stable_drivers),
        "stable_candidate_coverage": stable_coverage,
        "temporary_participant_share": _round_rate(1 - stable_coverage) if total else 0,
        "adjacent_active_day_continuity": _adjacent_active_day_continuity(daily_records),
        "stable_candidates": candidate_rows,
        "daily_details": daily_details,
    }


def _build_task_personnel_stability(
    task: str,
    current_records: list[dict[str, Any]],
    previous_records: list[dict[str, Any]],
) -> dict[str, Any]:
    current_drivers = _record_drivers(current_records)
    previous_drivers = _record_drivers(previous_records)
    continued_drivers = sorted(current_drivers & previous_drivers)
    new_drivers = sorted(current_drivers - previous_drivers)
    new_attendance = sum(1 for record in current_records if str(record.get("driver") or "") in new_drivers)
    total = len(current_records)
    new_attendance_share = _round_rate(new_attendance / total) if total else 0
    daily_turnover_rate = _daily_turnover_rate(current_records)
    max_consecutive_days = _max_consecutive_task_days(current_records)
    risk_level, risk_factors = _personnel_risk_level(
        new_attendance_share=new_attendance_share,
        daily_turnover_rate=daily_turnover_rate,
        max_consecutive_days=max_consecutive_days,
        current_total=total,
    )
    return {
        "task": task,
        "current_total": total,
        "current_driver_count": len(current_drivers),
        "previous_driver_count": len(previous_drivers),
        "continued_driver_count": len(continued_drivers),
        "continued_drivers": continued_drivers,
        "new_driver_count": len(new_drivers),
        "new_drivers": new_drivers,
        "new_attendance_count": new_attendance,
        "new_attendance_share": new_attendance_share,
        "daily_turnover_rate": daily_turnover_rate,
        "max_consecutive_days": max_consecutive_days,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
    }


def _build_task_daily_personnel_matrix(task: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    daily_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        date_text = str(record.get("date") or "")
        if date_text:
            daily_records[date_text].append(record)

    rows = []
    previous_drivers: set[str] = set()
    for date_text in sorted(daily_records):
        day_records = daily_records[date_text]
        drivers = _record_drivers(day_records)
        white_drivers = _drivers_for_shift(day_records, "白班")
        night_drivers = _drivers_for_shift(day_records, "夜班")
        union = drivers | previous_drivers
        turnover_rate = _round_rate(1 - (len(drivers & previous_drivers) / len(union))) if union else 0
        rows.append(
            {
                "date": date_text,
                "weekday": _weekday_label(date_text),
                "drivers": sorted(drivers),
                "white_drivers": sorted(white_drivers),
                "night_drivers": sorted(night_drivers),
                "continued_from_previous_day": sorted(drivers & previous_drivers),
                "new_from_previous_day": sorted(drivers - previous_drivers),
                "left_from_previous_day": sorted(previous_drivers - drivers),
                "turnover_rate": turnover_rate,
            }
        )
        previous_drivers = drivers
    return {"task": task, "dates": rows}


def _drivers_by_shift(rows: list[dict[str, Any]], stable_drivers: set[str], shift: str, *, stable: bool) -> list[str]:
    drivers = {
        str(row.get("driver"))
        for row in rows
        if row.get("driver")
        and _is_white_shift(row.get("shift")) == (shift == "白班")
        and ((str(row.get("driver")) in stable_drivers) == stable)
    }
    return sorted(drivers)


def _drivers_for_shift(rows: list[dict[str, Any]], shift: str) -> set[str]:
    return {
        str(row.get("driver"))
        for row in rows
        if row.get("driver") and _is_white_shift(row.get("shift")) == (shift == "白班")
    }


def _record_drivers(records: list[dict[str, Any]]) -> set[str]:
    return {str(record.get("driver")) for record in records if record.get("driver")}


def _daily_turnover_rate(records: list[dict[str, Any]]) -> float:
    daily_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        date_text = str(record.get("date") or "")
        if date_text:
            daily_records[date_text].append(record)
    active_dates = sorted(daily_records)
    if len(active_dates) < 2:
        return 0
    rates = []
    for previous_date, current_date in zip(active_dates, active_dates[1:]):
        previous_drivers = _record_drivers(daily_records[previous_date])
        current_drivers = _record_drivers(daily_records[current_date])
        union = previous_drivers | current_drivers
        if union:
            rates.append(1 - (len(previous_drivers & current_drivers) / len(union)))
    return _round_rate(sum(rates) / len(rates)) if rates else 0


def _max_consecutive_task_days(records: list[dict[str, Any]]) -> int:
    dates_by_driver: dict[str, set[date]] = defaultdict(set)
    for record in records:
        driver = str(record.get("driver") or "")
        date_text = str(record.get("date") or "")
        if not driver or not date_text:
            continue
        try:
            dates_by_driver[driver].add(date.fromisoformat(date_text))
        except ValueError:
            continue

    max_days = 0
    for dates in dates_by_driver.values():
        previous_day: date | None = None
        current_run = 0
        for day in sorted(dates):
            if previous_day is not None and day == previous_day + timedelta(days=1):
                current_run += 1
            else:
                current_run = 1
            max_days = max(max_days, current_run)
            previous_day = day
    return max_days


def _personnel_risk_level(
    *,
    new_attendance_share: float,
    daily_turnover_rate: float,
    max_consecutive_days: int,
    current_total: int,
) -> tuple[str, list[str]]:
    if current_total == 0:
        return "无数据", []

    risk_factors = []
    if new_attendance_share >= 0.5:
        risk_factors.append("新进人次占比高")
    elif new_attendance_share >= 0.3:
        risk_factors.append("新进人次占比偏高")

    if daily_turnover_rate >= 0.7:
        risk_factors.append("每日人员换手率高")
    elif daily_turnover_rate >= 0.45:
        risk_factors.append("每日人员换手率偏高")

    if max_consecutive_days <= 1:
        risk_factors.append("缺少连续承接")
    elif max_consecutive_days <= 2:
        risk_factors.append("连续承接天数偏低")

    if new_attendance_share >= 0.5 or daily_turnover_rate >= 0.7 or max_consecutive_days <= 1:
        return "高风险", risk_factors
    if new_attendance_share >= 0.3 or daily_turnover_rate >= 0.45 or max_consecutive_days <= 2:
        return "中风险", risk_factors
    return "低风险", risk_factors


def _build_person_attendance_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    driver_summary: dict[str, dict[str, Any]] = {}
    for record in records:
        driver = str(record.get("driver") or "").strip()
        if not driver:
            continue
        task = str(record.get("task") or "").strip()
        shift = str(record.get("shift") or "")
        item = driver_summary.setdefault(
            driver,
            {
                "driver": driver,
                "total": 0,
                "white": 0,
                "night": 0,
                "dates": set(),
                "tasks": set(),
                "task_counts": defaultdict(int),
                "locations": set(),
                "effective_time": 0.0,
            },
        )
        item["total"] += 1
        item["white" if _is_white_shift(shift) else "night"] += 1
        if record.get("date"):
            item["dates"].add(str(record.get("date")))
        if task:
            item["tasks"].add(task)
            item["task_counts"][task] += 1
        if record.get("location"):
            item["locations"].add(record.get("location") or "")
        item["effective_time"] += float(record.get("effective_time") or 0)

    rows = [_freeze_driver_summary(item) for item in driver_summary.values()]
    rows.sort(key=lambda item: (-item["total_attendance"], item["driver"]))
    return rows


def _stable_record_share(records: list[dict[str, Any]], candidates_by_task: dict[str, dict[str, dict[str, Any]]]) -> float:
    if not records:
        return 0
    stable_count = 0
    for record in records:
        task = str(record.get("task") or "")
        driver = str(record.get("driver") or "")
        if driver and driver in candidates_by_task.get(task, {}):
            stable_count += 1
    return _round_rate(stable_count / len(records))


def _adjacent_active_day_continuity(daily_records: dict[str, list[dict[str, Any]]]) -> float | None:
    active_dates = sorted(daily_records)
    if len(active_dates) < 2:
        return None
    continued = 0
    comparisons = 0
    for previous_date, current_date in zip(active_dates, active_dates[1:]):
        previous_drivers = {str(record.get("driver")) for record in daily_records[previous_date] if record.get("driver")}
        current_drivers = {str(record.get("driver")) for record in daily_records[current_date] if record.get("driver")}
        if not previous_drivers and not current_drivers:
            continue
        comparisons += 1
        if previous_drivers & current_drivers:
            continued += 1
    return _round_rate(continued / comparisons) if comparisons else None


def _median_rate(values: list[float | None]) -> float:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return 0
    return _round_rate(float(median(clean)))


def _round_rate(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 2)


def _scheduling_status(score: int) -> str:
    if score >= 70:
        return "排班可控"
    if score >= 50:
        return "观察"
    return "需关注"


def _weekday_label(date_text: str) -> str:
    labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    try:
        return labels[date.fromisoformat(date_text).weekday()]
    except ValueError:
        return ""


def _is_white_shift(value: Any) -> bool:
    text = str(value or "")
    return text in {"白班", "鐧界彮", "white"} or "白" in text


def _resource_status_from_authority(
    report: dict[str, Any],
    previous_report: dict[str, Any],
    *,
    authority_summary: dict[str, Any] | None,
    previous_authority_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prefer Feishu summary-table actual headcount for SD/day.

    If a specific day is missing from the Feishu summary text, substitute the
    de-duplicated detail parsing result for that date. If the authoritative
    summary is unavailable entirely, fall back to the legacy detail record count
    so the workflow still produces a report, but mark the source.
    """
    current_kpis = report.get("kpis", {})
    previous_kpis = previous_report.get("kpis", {})
    current_source = authority_summary if authority_summary and authority_summary.get("daily") else None
    previous_source = previous_authority_summary if previous_authority_summary and previous_authority_summary.get("daily") else None

    if current_source:
        current_resolved = _resolve_authority_with_detail_substitutes(report, current_source)
        current_avg = float(current_resolved.get("avg_daily_sd") or 0)
        current_total = int(current_resolved.get("total_actual") or 0)
        current_days = int(current_resolved.get("covered_days") or 0)
        current_expected_days = int(current_source.get("expected_days") or current_days)
        source_label = "feishu_authoritative_actual_headcount_with_detail_substitute" if current_resolved.get("substituted_dates") else "feishu_authoritative_actual_headcount"
    else:
        current_resolved = None
        current_avg = float(current_kpis.get("avg_daily_sd") or 0)
        current_total = int(current_kpis.get("total_attendance") or 0)
        current_days = int(current_kpis.get("attendance_days") or 0)
        current_expected_days = current_days
        source_label = "detail_records_fallback"

    if previous_source:
        previous_resolved = _resolve_authority_with_detail_substitutes(previous_report, previous_source)
        previous_avg = float(previous_resolved.get("avg_daily_sd") or 0)
        previous_total = int(previous_resolved.get("total_actual") or 0)
        previous_days = int(previous_resolved.get("covered_days") or 0)
        previous_expected_days = int(previous_source.get("expected_days") or previous_days)
    else:
        previous_resolved = None
        previous_avg = float(previous_kpis.get("avg_daily_sd") or 0)
        previous_total = int(previous_kpis.get("total_attendance") or 0)
        previous_days = int(previous_kpis.get("attendance_days") or 0)
        previous_expected_days = previous_days

    return {
        "metric": "SD个数/天",
        "source": source_label,
        "authority_source": authority_summary.get("source") if authority_summary else None,
        "current_value": current_avg,
        "previous_value": previous_avg,
        "delta": round(current_avg - previous_avg, 2),
        "delta_pct": _pct_delta(current_avg, previous_avg),
        "current_total_attendance": current_total,
        "previous_total_attendance": previous_total,
        "current_attendance_days": current_days,
        "previous_attendance_days": previous_days,
        "current_expected_days": current_expected_days,
        "previous_expected_days": previous_expected_days,
        "current_missing_dates": (authority_summary or {}).get("missing_dates", []),
        "previous_missing_dates": (previous_authority_summary or {}).get("missing_dates", []),
        "current_substituted_dates": (current_resolved or {}).get("substituted_dates", []),
        "previous_substituted_dates": (previous_resolved or {}).get("substituted_dates", []),
        "daily_authority": (authority_summary or {}).get("daily", []),
        "daily_resolved": (current_resolved or {}).get("daily", []),
        "daily_authority_comparison": _build_authority_detail_comparison(report, authority_summary),
    }


def _resolve_authority_with_detail_substitutes(report: dict[str, Any], authority_summary: dict[str, Any]) -> dict[str, Any]:
    authority_by_date = {item.get("date"): item for item in authority_summary.get("daily", [])}
    detail_by_date = {item.get("date"): item for item in report.get("daily_summary", [])}
    expected_dates = _expected_dates(authority_summary)
    if not expected_dates:
        expected_dates = sorted(set(authority_by_date) | set(detail_by_date))

    daily: list[dict[str, Any]] = []
    substituted_dates: list[str] = []
    total_actual = 0
    for date_text in expected_dates:
        authority_item = authority_by_date.get(date_text)
        if authority_item:
            white_actual = int(authority_item.get("white_actual") or 0)
            night_actual = int(authority_item.get("night_actual") or 0)
            total = int(authority_item.get("total_actual") or (white_actual + night_actual))
            source = "feishu_summary_text"
        else:
            detail_item = detail_by_date.get(date_text, {})
            white_actual = int(detail_item.get("white_count") or 0)
            night_actual = int(detail_item.get("night_count") or 0)
            total = int(detail_item.get("total_count") or (white_actual + night_actual))
            source = "detail_unique_driver_substitute"
            substituted_dates.append(date_text)
        total_actual += total
        daily.append(
            {
                "date": date_text,
                "white_actual": white_actual,
                "night_actual": night_actual,
                "total_actual": total,
                "source": source,
            }
        )

    covered_days = len(expected_dates)
    return {
        "daily": daily,
        "covered_days": covered_days,
        "expected_days": len(expected_dates),
        "missing_dates": authority_summary.get("missing_dates", []),
        "substituted_dates": substituted_dates,
        "total_actual": total_actual,
        "avg_daily_sd": round(total_actual / covered_days, 2) if covered_days else 0,
    }


def _expected_dates(authority_summary: dict[str, Any]) -> list[str]:
    period = authority_summary.get("period") or {}
    start_text = period.get("start_date")
    end_text = period.get("end_date")
    if not start_text or not end_text:
        return []
    try:
        start = date.fromisoformat(str(start_text))
        end = date.fromisoformat(str(end_text))
    except ValueError:
        return []
    if end < start:
        return []
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]


def _build_authority_detail_comparison(report: dict[str, Any], authority_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not authority_summary:
        return []
    detail_by_date = {item.get("date"): item for item in report.get("daily_summary", [])}
    comparison: list[dict[str, Any]] = []
    for item in authority_summary.get("daily", []):
        date_text = item.get("date")
        detail = detail_by_date.get(date_text, {})
        authority_white = int(item.get("white_actual") or 0)
        authority_night = int(item.get("night_actual") or 0)
        detail_white = int(detail.get("white_count") or 0)
        detail_night = int(detail.get("night_count") or 0)
        comparison.append(
            {
                "date": date_text,
                "authority_white_actual": authority_white,
                "detail_white_unique": detail_white,
                "white_diff": detail_white - authority_white,
                "authority_night_actual": authority_night,
                "detail_night_unique": detail_night,
                "night_diff": detail_night - authority_night,
            }
        )
    return comparison


def parse_weekly_records(raw_paths: Iterable[str | Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse multiple CSV files into normalized driver attendance records."""
    all_records: list[dict[str, Any]] = []
    all_diagnostics: list[dict[str, Any]] = []
    for path_like in raw_paths:
        path = Path(path_like)
        source_name = _infer_source_name(path)
        records, diagnostics = parse_single_file(path.read_text(encoding="utf-8-sig"), source_name)
        all_records.extend(asdict(record) for record in records)
        all_diagnostics.extend(diagnostics)
    return all_records, all_diagnostics


def parse_single_file(csv_text: str, source_name: str) -> tuple[list[WeeklyRecord], list[dict[str, Any]]]:
    rows = _parse_csv_text(csv_text)
    if len(rows) < 2:
        return [], []

    headers = rows[1]
    col_date = _find_col(headers, ["时间"])
    task_columns = _find_task_columns(headers)
    col_shift = _find_col(headers, ["班次"])
    col_car = _find_col(headers, ["车号"])
    col_driver = _find_col(headers, ["出车人SD"])
    col_time = _find_col(headers, ["出车时间"])
    col_total = _find_col(headers, ["采集总容量"])
    col_eff = _find_col(headers, ["有效采集时间"])
    col_sensor = _find_col(headers, ["传感器"])

    records: list[WeeklyRecord] = []
    diagnostics: list[dict[str, Any]] = []
    current_date: tuple[int, int, int] | None = None
    current_tasks: dict[str, str | None] = {"default": None, "white": None, "night": None}

    def add_diag(row_index: int, reason: str, data: dict[str, Any] | None = None) -> None:
        payload = {"source": source_name, "source_line": row_index + 1, "reason": reason}
        if data:
            payload.update(data)
        diagnostics.append(payload)

    for row_index in range(2, len(rows)):
        cells = rows[row_index]
        if not cells or all(str(cell).strip() == "" for cell in cells):
            continue

        parsed_date = _parse_date(_get_cell(cells, col_date))
        if parsed_date:
            current_date = parsed_date
            current_tasks = {"default": None, "white": None, "night": None}
        if not current_date:
            continue

        _update_current_tasks(cells, task_columns, current_tasks)

        date_text = _format_date_parts(current_date)
        task = _task_for_shift(current_tasks, _get_shift_table(cells, col_shift, 0)) or UNKNOWN_TASK
        driver_candidates = _find_driver_candidates(cells, col_driver)
        if not driver_candidates:
            expected_driver_raw = _get_cell(cells, col_driver)
            expected_time_raw = _get_cell(cells, col_time)
            expected_shift_table = _get_shift_table(cells, col_shift, 0)
            expected_meta = {
                "date": date_text,
                "task": _task_for_shift(current_tasks, expected_shift_table) or task,
                "raw_driver": expected_driver_raw,
                "raw_departure_time": expected_time_raw,
                "shift_table": expected_shift_table,
                "car_number": _get_shifted_cell(cells, col_car, 0),
                "sensor": _get_shifted_cell(cells, col_sensor, 0),
                "driver_col": col_driver,
                "time_col": col_time,
            }
            if expected_driver_raw:
                add_diag(row_index, "invalid_driver_candidate", expected_meta)
            elif expected_time_raw:
                add_diag(row_index, "time_without_driver", expected_meta)
            continue

        for candidate in driver_candidates:
            offset = candidate["offset"]
            time_binding = _find_time_for_driver(cells, col_time, candidate["col"], offset)
            shift_table = _get_shift_table(cells, col_shift, offset)
            row_meta = {
                "date": date_text,
                "task": _task_for_shift(current_tasks, shift_table) or task,
                "raw_driver": candidate["raw"],
                "raw_departure_time": time_binding["raw"],
                "shift_table": shift_table,
                "car_number": _get_shifted_cell(cells, col_car, offset),
                "sensor": _get_shifted_cell(cells, col_sensor, offset),
                "driver_col": candidate["col"],
                "time_col": time_binding["col"],
            }

            driver_names = candidate["names"]
            times = time_binding["times"]
            if not time_binding["raw"]:
                for driver in driver_names:
                    add_diag(row_index, "driver_without_time", {**row_meta, "driver": driver})
                continue
            if not times:
                for driver in driver_names:
                    add_diag(row_index, "unparseable_time", {**row_meta, "driver": driver})
                continue
            if len(driver_names) != len(times):
                add_diag(
                    row_index,
                    "driver_time_count_mismatch",
                    {**row_meta, "drivers": list(driver_names), "departure_times": list(times)},
                )
            if len(driver_names) == 1 and len(times) > 1 and not _has_name_separator(candidate["raw"]):
                add_diag(
                    row_index,
                    "single_driver_multiple_times",
                    {**row_meta, "driver": driver_names[0], "departure_times": list(times)},
                )

            total_collection = _parse_capacity(_get_shifted_cell(cells, col_total, offset)) if col_total >= 0 else 0.0
            effective_time = _parse_float(_get_shifted_cell(cells, col_eff, offset)) if col_eff >= 0 else 0.0

            for driver_index, driver in enumerate(driver_names):
                assigned_time = _bind_time_by_name_order(times, driver_index, len(driver_names))
                inferred_shift = _shift_by_departure_time(assigned_time)
                records.append(
                    WeeklyRecord(
                        date=date_text,
                        location=source_name,
                        task=_task_for_shift(current_tasks, inferred_shift) or row_meta["task"],
                        shift_table=row_meta["shift_table"],
                        sensor=row_meta["sensor"],
                        car_number=row_meta["car_number"],
                        driver=driver,
                        raw_driver=candidate["raw"],
                        departure_time=assigned_time,
                        all_departure_times="/".join(times),
                        shift=inferred_shift,
                        raw_departure_time=time_binding["raw"],
                        total_collection=total_collection,
                        effective_time=effective_time,
                        source=source_name,
                        source_line=row_index + 1,
                        row_index=row_index,
                        candidate_index=driver_index,
                        driver_col=candidate["col"],
                        time_col=time_binding["col"],
                    )
                )
    return records, diagnostics


def summarize_weekly_records(
    records: list[dict[str, Any]],
    *,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> dict[str, Any]:
    """Build deterministic KPIs and tables from normalized records."""
    start_text = _date_to_text(start_date)
    end_text = _date_to_text(end_date)
    filtered = [record for record in records if _within_date_range(record["date"], start_text, end_text)]

    task_by_date_shift: dict[tuple[str, str, str], dict[str, Any]] = {}
    driver_summary: dict[str, dict[str, Any]] = {}
    task_summary: dict[str, dict[str, Any]] = {}
    date_shift_summary: dict[str, dict[str, set[str]]] = {}

    for record in filtered:
        date_text = record["date"]
        task = record["task"]
        shift = record["shift"]
        driver = record["driver"]

        key = (date_text, task, shift)
        item = task_by_date_shift.setdefault(
            key,
            {
                "date": date_text,
                "task": task,
                "shift": shift,
                "drivers": set(),
                "white_drivers": set(),
                "night_drivers": set(),
                "total_collection": 0.0,
                "effective_time": 0.0,
                "locations": set(),
            },
        )
        item["drivers"].add(driver)
        item["white_drivers" if shift == "白班" else "night_drivers"].add(driver)
        item["total_collection"] += float(record.get("total_collection") or 0)
        item["effective_time"] += float(record.get("effective_time") or 0)
        item["locations"].add(record.get("location") or "")

        driver_item = driver_summary.setdefault(
            driver,
            {
                "driver": driver,
                "total": 0,
                "white": 0,
                "night": 0,
                "dates": set(),
                "tasks": set(),
                "task_counts": defaultdict(int),
                "locations": set(),
                "effective_time": 0.0,
            },
        )
        driver_item["total"] += 1
        driver_item["white" if shift == "白班" else "night"] += 1
        driver_item["dates"].add(date_text)
        driver_item["tasks"].add(task)
        driver_item["task_counts"][task] += 1
        driver_item["locations"].add(record.get("location") or "")
        driver_item["effective_time"] += float(record.get("effective_time") or 0)

        task_item = task_summary.setdefault(
            task,
            {"task": task, "total": 0, "white": 0, "night": 0, "drivers": set(), "dates": set()},
        )
        task_item["total"] += 1
        task_item["white" if shift == "白班" else "night"] += 1
        task_item["drivers"].add(driver)
        task_item["dates"].add(date_text)

        date_item = date_shift_summary.setdefault(date_text, {"white_drivers": set(), "night_drivers": set(), "drivers": set()})
        date_item["drivers"].add(driver)
        date_item["white_drivers" if shift == "白班" else "night_drivers"].add(driver)

    date_task_agg: dict[tuple[str, str], dict[str, Any]] = {}
    for item in task_by_date_shift.values():
        key = (item["date"], item["task"])
        agg = date_task_agg.setdefault(
            key,
            {"date": item["date"], "task": item["task"], "drivers": set(), "white_drivers": set(), "night_drivers": set()},
        )
        agg["drivers"].update(item["drivers"])
        agg["white_drivers"].update(item["white_drivers"])
        agg["night_drivers"].update(item["night_drivers"])

    daily_task_summary = [
        {
            "date": item["date"],
            "task": item["task"],
            "white_count": len(item["white_drivers"]),
            "night_count": len(item["night_drivers"]),
            "total_count": len(item["drivers"]),
            "drivers": sorted(item["drivers"]),
            "white_drivers": sorted(item["white_drivers"]),
            "night_drivers": sorted(item["night_drivers"]),
        }
        for item in date_task_agg.values()
    ]
    daily_task_summary.sort(key=lambda item: (item["date"], item["task"]), reverse=True)

    daily_summary = [
        {
            "date": date_text,
            "white_count": len(item["white_drivers"]),
            "night_count": len(item["night_drivers"]),
            "total_count": len(item["drivers"]),
            "drivers": sorted(item["drivers"]),
            "white_drivers": sorted(item["white_drivers"]),
            "night_drivers": sorted(item["night_drivers"]),
        }
        for date_text, item in date_shift_summary.items()
    ]
    daily_summary.sort(key=lambda item: item["date"], reverse=True)

    driver_rows = [_freeze_driver_summary(item) for item in driver_summary.values()]
    driver_rows.sort(key=lambda item: (-item["total"], item["driver"]))

    task_rows = [_freeze_task_summary(item) for item in task_summary.values()]
    task_rows.sort(key=lambda item: (-item["total"], item["task"]))

    dates = sorted({record["date"] for record in filtered})
    drivers = sorted({record["driver"] for record in filtered})
    tasks = sorted({record["task"] for record in filtered if record["task"] != UNKNOWN_TASK})
    total_count = len(filtered)
    white_count = sum(1 for record in filtered if record["shift"] == "白班")
    night_count = sum(1 for record in filtered if record["shift"] == "夜班")
    day_count = len(dates)

    return {
        "kpis": {
            "total_attendance": total_count,
            "white_attendance": white_count,
            "night_attendance": night_count,
            "unique_drivers": len(drivers),
            "attendance_days": day_count,
            "task_types": len(tasks),
            "avg_daily_sd": round(total_count / day_count, 2) if day_count else 0,
        },
        "date_bounds": {"min_date": dates[0] if dates else None, "max_date": dates[-1] if dates else None},
        "records": filtered,
        "record_count": total_count,
        "daily_summary": daily_summary,
        "daily_task_summary": daily_task_summary,
        "driver_summary": driver_rows,
        "person_attendance_summary": driver_rows,
        "task_summary": task_rows,
        "top_tasks": task_rows[:5],
        "queue_tasks": {"status": "no_data_source", "message": "暂无数据源"},
    }


def _parse_csv_text(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in csv.reader(text.splitlines()):
        if any(str(cell).strip() for cell in row):
            rows.append([str(cell).strip() for cell in row])
    return rows


def _find_col(headers: list[str], names: list[str]) -> int:
    for index, header in enumerate(headers):
        normalized = re.sub(r"\s{2,}", " ", str(header).replace("\n", " ")).strip()
        if any(name in normalized for name in names):
            return index
    return -1


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
    if not value:
        return None
    match = DATE_RE.match(str(value).strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _format_date_parts(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"


def _normalize_time_text(value: str) -> str:
    return str(value or "").replace("：", ":").replace("﹕", ":").replace("／", "/").strip()


def _extract_departure_times(value: str) -> list[str]:
    times: list[str] = []
    for match in TIME_RE.finditer(_normalize_time_text(value)):
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            times.append(f"{hour:02d}:{minute:02d}")
    return times


def _is_valid_driver(value: str) -> bool:
    if not value or not str(value).strip():
        return False
    text = str(value).strip()
    return re.fullmatch(r"[\d\.\s日号,，]+", text) is None


def _split_names_first(driver_raw: str) -> list[str]:
    return [name.strip() for name in str(driver_raw or "").replace("／", "/").split("/") if name.strip()]


def _has_name_separator(driver_raw: str) -> bool:
    return re.search(r"[/／]", str(driver_raw or "")) is not None


def _is_likely_driver_name_raw(driver_raw: str) -> bool:
    names = _split_names_first(driver_raw)
    return bool(names) and all(re.fullmatch(r"[\u4e00-\u9fff]{2,5}", name) for name in names)


def _find_driver_candidates(cells: list[str], col_driver: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    base_col = col_driver if col_driver >= 0 else 0
    start_col = max(0, base_col - 1)
    end_col = min(len(cells) - 1, base_col + 3)
    for col in range(start_col, end_col + 1):
        raw = _get_cell(cells, col)
        if not raw or not _is_valid_driver(raw) or not _is_likely_driver_name_raw(raw):
            continue
        key = (col, raw)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"raw": raw, "col": col, "offset": col - col_driver if col_driver >= 0 else 0, "names": _split_names_first(raw)})
    return candidates


def _get_shifted_cell(cells: list[str], col: int, offset: int) -> str:
    if col < 0:
        return ""
    return _get_cell(cells, col + max(0, offset))


def _find_time_for_driver(cells: list[str], col_time: int, driver_col: int, offset: int) -> dict[str, Any]:
    columns: list[int] = []

    def add_col(col: int) -> None:
        if 0 <= col < len(cells) and col not in columns:
            columns.append(col)

    add_col(col_time + offset)
    add_col(driver_col + 1)
    add_col(col_time)
    add_col(col_time + 1)

    fallback_raw = ""
    for col in columns:
        raw = _get_cell(cells, col)
        if raw and not fallback_raw:
            fallback_raw = raw
        times = _extract_departure_times(raw)
        if times:
            return {"raw": raw, "times": times, "col": col}
    return {"raw": fallback_raw, "times": [], "col": -1}


def _get_shift_table(cells: list[str], col_shift: int, offset: int) -> str:
    shifts: list[str] = []
    if col_shift < 0:
        return ""
    for col in range(col_shift, min(len(cells), col_shift + max(0, offset) + 1)):
        value = _get_cell(cells, col)
        if value in {"白班", "夜班"} and value not in shifts:
            shifts.append(value)
    return "+".join(shifts)


def _bind_time_by_name_order(times: list[str], driver_index: int, driver_count: int) -> str:
    if not times:
        return ""
    if driver_count == 1:
        return times[-1]
    if driver_count >= len(times):
        return times[min(driver_index, len(times) - 1)]
    if driver_index < driver_count - 1:
        return times[driver_index]
    return times[-1]


def _shift_by_departure_time(time_text: str) -> str:
    hour = int(time_text.split(":")[0])
    return "夜班" if hour >= 19 or hour < 5 else "白班"


def _parse_capacity(value: str) -> float:
    if not value or not str(value).strip():
        return 0.0
    raw = str(value).strip().upper()
    cleaned = re.sub(r"[GT％%]", "", raw).strip()
    parsed = _parse_float(cleaned)
    return parsed * 1000 if "T" in raw else parsed


def _parse_float(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _within_date_range(date_text: str, start_text: str | None, end_text: str | None) -> bool:
    if start_text and date_text < start_text:
        return False
    if end_text and date_text > end_text:
        return False
    return True


def _pct_delta(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _date_to_text(value: str | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _freeze_driver_summary(item: dict[str, Any]) -> dict[str, Any]:
    tasks = sorted(item["tasks"])
    task_counts = dict(item.get("task_counts") or {})
    primary_task = ""
    top_task_attendance = 0
    if task_counts:
        primary_task, top_task_attendance = sorted(task_counts.items(), key=lambda pair: (-pair[1], pair[0]))[0]
    return {
        "driver": item["driver"],
        "white": item["white"],
        "night": item["night"],
        "total": item["total"],
        "total_attendance": item["total"],
        "attendance_days": len(item["dates"]),
        "task_count": len(tasks),
        "primary_task": primary_task,
        "top_task_attendance": top_task_attendance,
        "task_attendance": task_counts,
        "effective_collection_time": round(float(item.get("effective_time") or 0), 2),
        "tasks": tasks,
        "locations": sorted(item["locations"]),
    }


def _freeze_task_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": item["task"],
        "total": item["total"],
        "white": item["white"],
        "night": item["night"],
        "driver_count": len(item["drivers"]),
        "attendance_days": len(item["dates"]),
        "drivers": sorted(item["drivers"]),
    }


def _infer_source_name(path: Path) -> str:
    name = path.stem.strip()
    if "青岛&临沂" in name:
        location = "青岛&临沂"
    elif "青岛黄岛" in name:
        location = "青岛_黄岛"
    elif "青岛" in name:
        location = "青岛_城阳"
    elif "临沂" in name:
        location = "临沂"
    else:
        location = name
    match = re.search(r"[（(]([^）)]+)[）)]", name)
    device = match.group(1).strip() if match else "未知设备"
    return f"{location}_{device}" if location != name or match else name


def _source_file_info(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"path": path.as_posix(), "name": path.name, "exists": path.exists()}
    if path.exists():
        info.update({"size": path.stat().st_size, "sha256": _sha256(path)})
    return info


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
