"""Collection data dashboard rules and renderers."""

from .metrics import attach_configured_metrics, load_collection_metric_config
from .rules import (
    build_collection_dashboard,
    dedupe_vehicle_daily_status,
    parse_vehicle_status_rows,
    summarize_vehicle_daily_status,
)

__all__ = [
    "attach_configured_metrics",
    "build_collection_dashboard",
    "dedupe_vehicle_daily_status",
    "load_collection_metric_config",
    "parse_vehicle_status_rows",
    "summarize_vehicle_daily_status",
]
