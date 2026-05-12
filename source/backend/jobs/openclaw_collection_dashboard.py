"""OpenClaw cron registration for the collection data dashboard refresh."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs.generate_collection_dashboard import CollectionDashboardConfig, load_collection_dashboard_config


CRON_NAME = "collection-data-dashboard-refresh"
SESSION_KEY = "agent:collection-data-dashboard"
TIMEOUT_SECONDS = "1800"
DESCRIPTION = "每天拉取飞书采集明细并生成本地采集数据看板"
CRON_MESSAGE = (
    "运行 data-analyst-agent 的 collection_data_dashboard workflow；"
    "执行 backend/jobs/generate_collection_dashboard.py --config config/collection_dashboard.yaml；"
    "复用 config/weekly_sources.yaml 中的 6 个飞书采集明细源，生成 data/collection-dashboard/latest；"
    "车辆状态只按有效司机和司机位置状态文本判定，出车异常记录与数采问题记录不参与判定；"
    "指标必须由确定性规则计算，LLM 只允许用于摘要解释。"
)


def build_openclaw_cron_args(config: CollectionDashboardConfig, openclaw_command: str = "openclaw.cmd") -> list[str]:
    """Build the OpenClaw cron command for the collection dashboard refresh."""
    return [
        openclaw_command,
        "cron",
        "add",
        "--name",
        CRON_NAME,
        "--description",
        DESCRIPTION,
        "--cron",
        config.cron,
        "--tz",
        config.timezone,
        "--session-key",
        SESSION_KEY,
        "--timeout-seconds",
        TIMEOUT_SECONDS,
        "--message",
        CRON_MESSAGE,
    ]


def format_command(args: list[str]) -> str:
    """Format command arguments for copyable Windows shell output."""
    return subprocess.list2cmdline(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Register the collection data dashboard OpenClaw cron job.")
    parser.add_argument("--config", default="config/collection_dashboard.yaml")
    parser.add_argument("--register", action="store_true", help="Actually register the cron job. Without this flag, print the command only.")
    parser.add_argument("--openclaw-command", default="openclaw.cmd")
    args = parser.parse_args()

    config = load_collection_dashboard_config(Path(args.config))
    cron_args = build_openclaw_cron_args(config, args.openclaw_command)
    if not args.register:
        print(format_command(cron_args))
        return 0

    completed = subprocess.run(cron_args, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
