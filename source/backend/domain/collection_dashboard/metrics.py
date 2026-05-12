"""Config-driven metric registry for the collection data dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml


MetricCompute = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def load_collection_metric_config(path: str | Path) -> dict[str, Any]:
    """Load and validate the collection dashboard metric config."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Collection dashboard metric config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    groups = raw.get("metric_groups")
    metrics = raw.get("metrics")
    if not isinstance(groups, list) or not groups:
        raise ValueError("collection dashboard metric config must define metric_groups")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("collection dashboard metric config must define metrics")

    group_ids: set[str] = set()
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"metric_groups[{index}] must be a mapping")
        group_id = _required_string(group, "id", f"metric_groups[{index}]")
        _required_string(group, "name", f"metric_groups[{index}]")
        group_ids.add(group_id)

    seen_metric_ids: set[str] = set()
    for index, metric in enumerate(metrics):
        if not isinstance(metric, dict):
            raise ValueError(f"metrics[{index}] must be a mapping")
        context = f"metrics[{index}]"
        metric_id = _required_string(metric, "id", context)
        if metric_id in seen_metric_ids:
            raise ValueError(f"Duplicate metric id: {metric_id}")
        seen_metric_ids.add(metric_id)
        group_id = _required_string(metric, "group", context)
        if group_id not in group_ids:
            raise ValueError(f"{metric_id} references unknown group: {group_id}")
        _required_string(metric, "name", context)
        _required_string(metric, "compute", context)
        _required_string(metric, "display", context)
        if "order" not in metric:
            raise ValueError(f"{metric_id} must define order")

    return {
        "metric_groups": sorted(groups, key=lambda item: int(item.get("order") or 0)),
        "metrics": sorted(metrics, key=lambda item: int(item.get("order") or 0)),
    }


def attach_configured_metrics(dashboard: dict[str, Any], metric_config: dict[str, Any]) -> dict[str, Any]:
    """Attach configured metric groups to each period view.

    The raw period metrics remain in ``period_views[*].metrics``. This function
    adds a config-shaped layer so later indicator changes can be made by YAML
    first, with code changes only when a new compute function is required.
    """
    enabled_groups = [
        group
        for group in metric_config.get("metric_groups", [])
        if bool(group.get("enabled", True))
    ]
    groups_by_id = {str(group["id"]): group for group in enabled_groups}
    enabled_metrics = [
        metric
        for metric in metric_config.get("metrics", [])
        if bool(metric.get("enabled", True)) and str(metric.get("group")) in groups_by_id
    ]

    missing_compute = [
        str(metric.get("compute"))
        for metric in enabled_metrics
        if str(metric.get("compute")) not in METRIC_COMPUTE_REGISTRY
    ]
    if missing_compute:
        missing_text = ", ".join(sorted(set(missing_compute)))
        raise ValueError(f"Unknown collection dashboard metric compute function: {missing_text}")

    for view in (dashboard.get("period_views") or {}).values():
        view["configured_metric_groups"] = _compute_groups_for_period(
            view,
            dashboard,
            groups_by_id,
            enabled_metrics,
        )

    active_grain = str(dashboard.get("active_grain") or "day")
    active_view = (dashboard.get("period_views") or {}).get(active_grain) or {}
    dashboard["metric_registry"] = {
        "groups": enabled_groups,
        "metrics": enabled_metrics,
        "compute_functions": sorted(METRIC_COMPUTE_REGISTRY),
    }
    dashboard["configured_metric_groups"] = active_view.get("configured_metric_groups") or []
    dashboard["metric_diagnostics"] = [
        *list(dashboard.get("metric_diagnostics") or []),
        {
            "code": "metric_config_loaded",
            "level": "info",
            "enabled_group_count": len(enabled_groups),
            "enabled_metric_count": len(enabled_metrics),
        },
    ]
    return dashboard


def _compute_groups_for_period(
    view: dict[str, Any],
    dashboard: dict[str, Any],
    groups_by_id: dict[str, dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id in groups_by_id}
    for metric in metrics:
        compute_name = str(metric.get("compute"))
        payload = METRIC_COMPUTE_REGISTRY[compute_name](view, dashboard)
        value = payload.get("value")
        display = str(metric.get("display") or payload.get("display") or "number")
        row = {
            "id": metric["id"],
            "group": metric["group"],
            "group_name": groups_by_id[str(metric["group"])]["name"],
            "name": metric["name"],
            "compute": compute_name,
            "display": display,
            "value": value,
            "display_value": payload.get("display_value") or _format_metric_value(value, display),
            "order": int(metric.get("order") or 0),
            "risk_level": _risk_level(value, metric.get("thresholds"), str(metric.get("threshold_direction") or "higher_is_risk")),
        }
        grouped[str(metric["group"])].append(row)

    result: list[dict[str, Any]] = []
    for group_id, group in sorted(groups_by_id.items(), key=lambda item: int(item[1].get("order") or 0)):
        rows = sorted(grouped.get(group_id) or [], key=lambda item: item["order"])
        if not rows:
            continue
        result.append(
            {
                "id": group_id,
                "name": group["name"],
                "order": int(group.get("order") or 0),
                "metrics": rows,
            }
        )
    return result


def _period_metric(metric_id: str) -> MetricCompute:
    def compute(view: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
        metric = (view.get("metrics") or {}).get(metric_id) or {}
        return {"value": metric.get("value"), "display_value": metric.get("display_value")}

    return compute


def _dashboard_overview_kpi(*labels: str) -> MetricCompute:
    def compute(view: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
        kpis = (dashboard.get("dashboard_overview") or {}).get("kpis") or {}
        for label in labels:
            item = kpis.get(label)
            if isinstance(item, dict) and item.get("value") not in {None, ""}:
                return {"value": _number(item.get("value")), "display_value": str(item.get("value"))}
        return {"value": None, "display_value": "-"}

    return compute


def _vehicle_day_count(view: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
    vehicle = view.get("vehicle_status") or {}
    return {"value": vehicle.get("vehicle_day_count"), "display_value": str(vehicle.get("vehicle_day_count") or 0)}


METRIC_COMPUTE_REGISTRY: dict[str, MetricCompute] = {
    "active_people": _period_metric("active_people"),
    "attendance_count": _period_metric("attendance_count"),
    "white_attendance": _period_metric("white_attendance"),
    "night_attendance": _period_metric("night_attendance"),
    "sd_per_day": _period_metric("sd_per_day"),
    "stable_participant_coverage": _period_metric("stable_participant_coverage"),
    "top_task_count": _period_metric("top_task_count"),
    "vehicle_count": _period_metric("vehicle_count"),
    "vehicle_day_count": _vehicle_day_count,
    "vehicle_active_count": _period_metric("vehicle_active_count"),
    "vehicle_idle_count": _period_metric("vehicle_idle_count"),
    "vehicle_abnormal_count": _period_metric("vehicle_abnormal_count"),
    "vehicle_unknown_count": _period_metric("vehicle_unknown_count"),
    "dashboard_total_collections": _dashboard_overview_kpi("采集总次数"),
    "dashboard_bos_rate": _dashboard_overview_kpi("入库率"),
    "dashboard_records": _dashboard_overview_kpi("Record 文件", "Records"),
    "dashboard_mileage": _dashboard_overview_kpi("总里程"),
    "dashboard_quality_pass_rate": _dashboard_overview_kpi("质检通过率"),
}


def _required_string(raw: dict[str, Any], key: str, context: str) -> str:
    value = raw.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"{context} must define {key}")
    return str(value).strip()


def _format_metric_value(value: Any, display: str) -> str:
    if value is None:
        return "-"
    if display == "percent":
        try:
            return f"{float(value) * 100:.1f}%"
        except (TypeError, ValueError):
            return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def _risk_level(value: Any, thresholds: Any, threshold_direction: str) -> str | None:
    if not isinstance(thresholds, dict) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    medium = thresholds.get("medium")
    high = thresholds.get("high")
    if medium is None and high is None:
        return None

    if threshold_direction == "lower_is_risk":
        if high is not None and number <= float(high):
            return "high"
        if medium is not None and number <= float(medium):
            return "medium"
        return "low"

    if high is not None and number >= float(high):
        return "high"
    if medium is not None and number >= float(medium):
        return "medium"
    return "low"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "")
    suffix_multiplier = 1.0
    if "km" in text.lower():
        text = text.lower().replace("km", "")
    if "%" in text:
        text = text.replace("%", "")
        suffix_multiplier = 0.01
    try:
        return float(text.strip()) * suffix_multiplier
    except ValueError:
        return None
