"""Configurable resource-management metrics for weekly SD reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass(frozen=True)
class MetricGroupConfig:
    id: str
    name: str
    enabled: bool
    order: int


@dataclass(frozen=True)
class MetricConfig:
    id: str
    group: str
    name: str
    enabled: bool
    compute: str
    display: str
    order: int
    thresholds: dict[str, float]


@dataclass(frozen=True)
class ResourceMetricConfig:
    groups: list[MetricGroupConfig]
    metrics: list[MetricConfig]


ComputeFn = Callable[[dict[str, Any], MetricConfig], dict[str, Any]]


def load_resource_metric_config(path: str | Path) -> ResourceMetricConfig:
    """Load the maintainable YAML metric registry."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Resource metric config not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    groups_raw = raw.get("metric_groups")
    metrics_raw = raw.get("metrics")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise ValueError("resource metric config must define metric_groups")
    if not isinstance(metrics_raw, list):
        raise ValueError("resource metric config must define metrics")

    groups = [_parse_group(item, index) for index, item in enumerate(groups_raw)]
    group_ids = {group.id for group in groups}
    metrics = [_parse_metric(item, index, group_ids) for index, item in enumerate(metrics_raw)]
    return ResourceMetricConfig(groups=groups, metrics=metrics)


def attach_resource_metrics(report: dict[str, Any], config: ResourceMetricConfig) -> dict[str, Any]:
    """Attach configurable resource metrics and risk items to a weekly report."""
    diagnostics: list[dict[str, Any]] = list(report.get("metric_diagnostics") or [])
    risk_items: list[dict[str, Any]] = list(report.get("risk_items") or [])
    group_by_id = {group.id: group for group in config.groups if group.enabled}
    resource_metrics: dict[str, list[dict[str, Any]]] = {group.id: [] for group in sorted(group_by_id.values(), key=lambda item: item.order)}

    for metric in sorted(config.metrics, key=lambda item: item.order):
        if not metric.enabled:
            continue
        group = group_by_id.get(metric.group)
        if not group:
            continue
        compute_fn = COMPUTE_REGISTRY.get(metric.compute)
        if compute_fn is None:
            raise ValueError(f"Unknown resource metric compute function: {metric.compute}")
        try:
            row = compute_fn(report, metric)
            row = {
                "id": metric.id,
                "name": metric.name,
                "group": metric.group,
                "group_name": group.name,
                "display": metric.display,
                **row,
            }
            row.setdefault("display_value", _format_value(row.get("value"), metric.display))
            resource_metrics.setdefault(metric.group, []).append(row)
        except Exception as exc:
            diagnostics.append(
                {
                    "metric_id": metric.id,
                    "compute": metric.compute,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )

    risk_items.extend(
        _task_continuity_risks(
            report,
            medium_threshold=_threshold(config, "task_continuity_risk_count", "medium", 0.45),
            high_threshold=_threshold(config, "task_continuity_risk_count", "high", 0.70),
        )
    )
    risk_items.extend(_vehicle_low_storage_risks(report, _threshold(config, "low_storage_vehicle_count", "storage_rate", 0.9)))
    risk_items.extend(_vehicle_high_clip_failure_risks(report, _threshold(config, "high_clip_failure_vehicle_count", "failure_rate", 0.5)))
    risk_items.extend(
        _high_output_low_quality_risks(
            report,
            min_collection_count=_threshold(config, "high_output_low_quality_vehicle_count", "min_collection_count", 100),
            failure_rate=_threshold(config, "high_output_low_quality_vehicle_count", "failure_rate", 0.5),
        )
    )
    report["resource_metrics"] = {key: value for key, value in resource_metrics.items() if value}
    report["risk_items"] = _dedupe_risk_items(risk_items)
    report["metric_diagnostics"] = diagnostics
    return report


def _parse_group(item: Any, index: int) -> MetricGroupConfig:
    if not isinstance(item, dict):
        raise ValueError(f"metric_groups[{index}] must be a mapping")
    return MetricGroupConfig(
        id=_required_string(item, "id"),
        name=_required_string(item, "name"),
        enabled=bool(item.get("enabled", True)),
        order=int(item.get("order", index + 1)),
    )


def _parse_metric(item: Any, index: int, group_ids: set[str]) -> MetricConfig:
    if not isinstance(item, dict):
        raise ValueError(f"metrics[{index}] must be a mapping")
    group = _required_string(item, "group")
    if group not in group_ids:
        raise ValueError(f"metrics[{index}] references unknown group: {group}")
    thresholds_raw = item.get("thresholds") or {}
    if not isinstance(thresholds_raw, dict):
        raise ValueError(f"metrics[{index}].thresholds must be a mapping")
    return MetricConfig(
        id=_required_string(item, "id"),
        group=group,
        name=_required_string(item, "name"),
        enabled=bool(item.get("enabled", True)),
        compute=_required_string(item, "compute"),
        display=_required_string(item, "display"),
        order=int(item.get("order", index + 1)),
        thresholds={str(key): float(value) for key, value in thresholds_raw.items()},
    )


def _required_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing required metric config value: {key}")
    return str(value).strip()


def _compute_count_unique_people(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    people = {item.get("driver") for item in report.get("person_attendance_summary") or [] if item.get("driver")}
    if people:
        return {"value": len(people)}
    return {"value": int((report.get("kpis") or {}).get("unique_drivers") or 0)}


def _compute_weekly_attendance_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    total = sum(int(item.get("total_attendance", item.get("total", 0)) or 0) for item in report.get("person_attendance_summary") or [])
    if total:
        return {"value": total}
    return {"value": int((report.get("kpis") or {}).get("total_attendance") or 0)}


def _compute_weekly_white_attendance_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": int((report.get("kpis") or {}).get("white_attendance") or 0)}


def _compute_weekly_night_attendance_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": int((report.get("kpis") or {}).get("night_attendance") or 0)}


def _compute_avg_tasks_per_person(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    rows = _person_rows(report)
    if not rows:
        return {"value": 0}
    total_tasks = sum(_parse_number(item.get("task_count", len(item.get("tasks") or []))) for item in rows)
    return {"value": round(total_tasks / len(rows), 2)}


def _compute_top_attendance_people(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    top_n = int(metric.thresholds.get("top_n", 5))
    rows = sorted(
        _person_rows(report),
        key=lambda item: _parse_number(item.get("total_attendance", item.get("total", 0))),
        reverse=True,
    )[:top_n]
    details = [
        {
            "person": item.get("driver") or "-",
            "attendance_count": int(_parse_number(item.get("total_attendance", item.get("total", 0)))),
            "white": int(_parse_number(item.get("white"))),
            "night": int(_parse_number(item.get("night"))),
            "task_count": int(_parse_number(item.get("task_count", len(item.get("tasks") or [])))),
            "primary_task": item.get("primary_task") or "-",
        }
        for item in rows
    ]
    return {"value": len(details), "display_value": _join_ranked(details, "person", "attendance_count"), "details": details}


def _compute_task_personnel_churn(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    rows = _stability_rows(report)
    values = [float(item.get("daily_turnover_rate") or 0) for item in rows]
    value = max(values) if values else 0
    return {
        "value": value,
        "risk_level": _metric_risk(value, metric.thresholds),
        "details": [
            {
                "task": item.get("task"),
                "daily_turnover_rate": item.get("daily_turnover_rate"),
                "risk_level": item.get("risk_level"),
            }
            for item in rows
        ],
    }


def _compute_top_task_participant_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return _max_stability_metric(report, "current_driver_count", "task", "current_driver_count")


def _compute_top_task_continued_people(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return _max_stability_metric(report, "continued_driver_count", "task", "continued_driver_count")


def _compute_top_task_new_people(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return _max_stability_metric(report, "new_driver_count", "task", "new_driver_count")


def _compute_task_new_attendance_share(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    rows = _stability_rows(report)
    values = [float(item.get("new_attendance_share") or 0) for item in rows]
    value = max(values) if values else 0
    return {
        "value": value,
        "risk_level": _metric_risk(value, metric.thresholds),
        "details": [
            {
                "task": item.get("task"),
                "new_attendance_share": item.get("new_attendance_share"),
                "new_attendance_count": item.get("new_attendance_count"),
                "current_total": item.get("current_total"),
            }
            for item in rows
        ],
    }


def _compute_max_consecutive_task_days(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return _max_stability_metric(report, "max_consecutive_days", "task", "max_consecutive_days")


def _compute_task_continuity_risk_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    medium = metric.thresholds.get("medium", 0.45)
    high = metric.thresholds.get("high", 0.70)
    risks = _task_continuity_risks(report, medium_threshold=medium, high_threshold=high)
    high_count = sum(1 for item in risks if item.get("severity") == "high")
    risk_level = "high" if high_count else ("medium" if risks else "low")
    return {"value": len(risks), "risk_level": risk_level, "details": risks}


def _compute_dashboard_collection_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": _kpi_number(report, "采集总次数")}


def _compute_dashboard_storage_rate(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": _kpi_rate(report, "入库率")}


def _compute_dashboard_records(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": _kpi_number(report, "Record 文件")}


def _compute_dashboard_mileage(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": _kpi_number(report, "总里程")}


def _compute_collection_count_per_person(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": round(_safe_divide(_kpi_number(report, "采集总次数"), _active_people_count(report)), 2)}


def _compute_records_per_person(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": round(_safe_divide(_kpi_number(report, "Record 文件"), _active_people_count(report)), 2)}


def _compute_mileage_per_person(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    return {"value": round(_safe_divide(_kpi_number(report, "总里程"), _active_people_count(report)), 2)}


def _compute_low_storage_vehicle_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    threshold = metric.thresholds.get("storage_rate", 0.9)
    rows = _vehicle_low_storage_risks(report, threshold)
    return {"value": len(rows), "details": rows}


def _compute_high_clip_failure_vehicle_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    threshold = metric.thresholds.get("failure_rate", 0.5)
    rows = _vehicle_high_clip_failure_risks(report, threshold)
    return {"value": len(rows), "details": rows}


def _compute_top_anomaly_vehicles(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    top_n = int(metric.thresholds.get("top_n", 5))
    rows = _vehicle_quality_rows(report)
    details = sorted(
        (
            {
                "type": "vehicle_top_anomaly",
                "name": _row_value(row, "车辆"),
                "severity": "medium",
                "reason": f"不通过数 {_row_value(row, '不通过数') or '0'}，不通过率 {_row_value(row, '不通过率') or '0%'}",
                "data": row,
            }
            for row in rows
        ),
        key=lambda item: _parse_number(item["data"].get("不通过数")),
        reverse=True,
    )[:top_n]
    return {"value": len(details), "display_value": _join_ranked(details, "name", "reason"), "details": details}


def _compute_high_output_low_quality_vehicle_count(report: dict[str, Any], metric: MetricConfig) -> dict[str, Any]:
    min_collection_count = metric.thresholds.get("min_collection_count", 100)
    failure_rate = metric.thresholds.get("failure_rate", 0.5)
    rows = _high_output_low_quality_risks(report, min_collection_count=min_collection_count, failure_rate=failure_rate)
    return {"value": len(rows), "details": rows}


def _metric_risk(value: float, thresholds: dict[str, float]) -> str:
    if value >= thresholds.get("high", 1.0):
        return "high"
    if value >= thresholds.get("medium", 1.0):
        return "medium"
    return "low"


def _kpi_number(report: dict[str, Any], label: str) -> float:
    kpi = ((report.get("dashboard_overview") or {}).get("kpis") or {}).get(label) or {}
    return _parse_number(kpi.get("value"))


def _kpi_rate(report: dict[str, Any], label: str) -> float:
    kpi = ((report.get("dashboard_overview") or {}).get("kpis") or {}).get(label) or {}
    return _parse_rate(kpi.get("value"))


def _vehicle_low_storage_risks(report: dict[str, Any], threshold: float) -> list[dict[str, Any]]:
    risks = []
    for row in _vehicle_collection_rows(report):
        rate = _parse_rate(_row_value(row, "入库率"))
        if rate and rate < threshold:
            vehicle = _row_value(row, "车辆") or "-"
            risks.append(
                {
                    "type": "vehicle_low_storage_rate",
                    "name": vehicle,
                    "severity": "medium",
                    "reason": f"入库率 {_format_value(rate, 'percent')}",
                    "data": row,
                }
            )
    return risks


def _vehicle_high_clip_failure_risks(report: dict[str, Any], threshold: float) -> list[dict[str, Any]]:
    risks = []
    for row in _vehicle_quality_rows(report):
        rate = _parse_rate(_row_value(row, "不通过率"))
        if rate and rate >= threshold:
            vehicle = _row_value(row, "车辆") or "-"
            risks.append(
                {
                    "type": "vehicle_high_clip_failure_rate",
                    "name": vehicle,
                    "severity": "high",
                    "reason": f"Clips 不通过率 {_format_value(rate, 'percent')}",
                    "data": row,
                }
            )
    return risks


def _threshold(config: ResourceMetricConfig, metric_id: str, key: str, default: float) -> float:
    for metric in config.metrics:
        if metric.id == metric_id:
            return metric.thresholds.get(key, default)
    return default


def _person_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return list(report.get("person_attendance_summary") or report.get("driver_summary") or [])


def _stability_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return list((report.get("focus_summary") or {}).get("top_task_personnel_stability") or [])


def _active_people_count(report: dict[str, Any]) -> float:
    rows = _person_rows(report)
    people = {item.get("driver") for item in rows if item.get("driver")}
    if people:
        return float(len(people))
    return float((report.get("kpis") or {}).get("unique_drivers") or 0)


def _max_stability_metric(report: dict[str, Any], value_key: str, name_key: str, detail_value_key: str) -> dict[str, Any]:
    rows = _stability_rows(report)
    if not rows:
        return {"value": 0, "details": []}
    max_row = max(rows, key=lambda item: _parse_number(item.get(value_key)))
    return {
        "value": _parse_number(max_row.get(value_key)),
        "details": [
            {
                "task": item.get(name_key),
                detail_value_key: item.get(value_key),
                "current_total": item.get("current_total"),
                "risk_level": item.get("risk_level"),
            }
            for item in rows
        ],
    }


def _vehicle_collection_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return list((report.get("dashboard_overview") or {}).get("vehicle_collection_summary") or [])


def _vehicle_quality_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return list((report.get("dashboard_overview") or {}).get("vehicle_quality_summary") or [])


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _join_ranked(items: list[dict[str, Any]], name_key: str, value_key: str, limit: int = 5) -> str:
    parts = []
    for item in items[:limit]:
        name = item.get(name_key) or "-"
        value = item.get(value_key)
        parts.append(f"{name} {value}" if value not in (None, "") else str(name))
    return "；".join(parts) if parts else "-"


def _task_continuity_risks(report: dict[str, Any], *, medium_threshold: float, high_threshold: float) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for row in _stability_rows(report):
        turnover = float(row.get("daily_turnover_rate") or 0)
        new_share = float(row.get("new_attendance_share") or 0)
        reasons = []
        severity = "medium"
        if turnover >= high_threshold:
            severity = "high"
            reasons.append(f"每日人员换手率 {_format_value(turnover, 'percent')}")
        elif turnover >= medium_threshold:
            reasons.append(f"每日人员换手率 {_format_value(turnover, 'percent')}")
        if new_share >= high_threshold:
            severity = "high"
            reasons.append(f"新进人次占比 {_format_value(new_share, 'percent')}")
        elif new_share >= medium_threshold:
            reasons.append(f"新进人次占比 {_format_value(new_share, 'percent')}")
        if not reasons:
            continue
        risks.append(
            {
                "type": "task_continuity",
                "name": row.get("task") or "-",
                "severity": severity,
                "reason": "；".join(reasons),
                "data": row,
            }
        )
    return risks


def _high_output_low_quality_risks(
    report: dict[str, Any],
    *,
    min_collection_count: float,
    failure_rate: float,
) -> list[dict[str, Any]]:
    quality_by_vehicle = {_row_value(row, "车辆"): row for row in _vehicle_quality_rows(report)}
    risks: list[dict[str, Any]] = []
    for row in _vehicle_collection_rows(report):
        vehicle = _row_value(row, "车辆")
        quality = quality_by_vehicle.get(vehicle)
        if not quality:
            continue
        collection_count = _parse_number(_row_value(row, "采集", "采集 ▼", "采集 ▲"))
        fail_rate = _parse_rate(_row_value(quality, "不通过率"))
        if collection_count >= min_collection_count and fail_rate >= failure_rate:
            risks.append(
                {
                    "type": "vehicle_high_output_low_quality",
                    "name": vehicle or "-",
                    "severity": "high",
                    "reason": f"采集 {_format_value(collection_count, 'number')}，Clips 不通过率 {_format_value(fail_rate, 'percent')}",
                    "data": {"collection": row, "quality": quality},
                }
            )
    return risks


def _dedupe_risk_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("type") or ""), str(item.get("name") or ""), str(item.get("reason") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0


def _parse_number(value: Any) -> float:
    text = str(value or "")
    match = re.search(r"-?[\d,]+(?:\.\d+)?", text)
    if not match:
        return 0
    return float(match.group(0).replace(",", ""))


def _parse_rate(value: Any) -> float:
    number = _parse_number(value)
    if "%" in str(value or ""):
        return round(number / 100, 4)
    return number


def _format_value(value: Any, display: str) -> str:
    if display == "list":
        if isinstance(value, list):
            return "；".join(str(item) for item in value[:5]) if value else "-"
        return str(value or "-")
    if display == "percent":
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return "0.0%"
    if display == "number":
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "0"
        if numeric.is_integer():
            return f"{int(numeric):,}"
        return f"{numeric:,.2f}"
    return str(value or "")


COMPUTE_REGISTRY: dict[str, ComputeFn] = {
    "count_unique_people": _compute_count_unique_people,
    "weekly_attendance_count": _compute_weekly_attendance_count,
    "weekly_white_attendance_count": _compute_weekly_white_attendance_count,
    "weekly_night_attendance_count": _compute_weekly_night_attendance_count,
    "avg_tasks_per_person": _compute_avg_tasks_per_person,
    "top_attendance_people": _compute_top_attendance_people,
    "top_task_participant_count": _compute_top_task_participant_count,
    "top_task_continued_people": _compute_top_task_continued_people,
    "top_task_new_people": _compute_top_task_new_people,
    "task_new_attendance_share": _compute_task_new_attendance_share,
    "task_personnel_churn": _compute_task_personnel_churn,
    "max_consecutive_task_days": _compute_max_consecutive_task_days,
    "task_continuity_risk_count": _compute_task_continuity_risk_count,
    "dashboard_collection_count": _compute_dashboard_collection_count,
    "dashboard_storage_rate": _compute_dashboard_storage_rate,
    "dashboard_records": _compute_dashboard_records,
    "dashboard_mileage": _compute_dashboard_mileage,
    "collection_count_per_person": _compute_collection_count_per_person,
    "records_per_person": _compute_records_per_person,
    "mileage_per_person": _compute_mileage_per_person,
    "low_storage_vehicle_count": _compute_low_storage_vehicle_count,
    "high_clip_failure_vehicle_count": _compute_high_clip_failure_vehicle_count,
    "top_anomaly_vehicles": _compute_top_anomaly_vehicles,
    "high_output_low_quality_vehicle_count": _compute_high_output_low_quality_vehicle_count,
}
