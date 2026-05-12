import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from domain.collection_dashboard.local_app import (
    build_collection_frontend_payload,
    render_collection_dashboard_local_app,
)
from domain.collection_dashboard.render import render_collection_dashboard_embed, render_collection_dashboard_iframe_preview
from domain.collection_dashboard.metrics import attach_configured_metrics, load_collection_metric_config
from domain.collection_dashboard.rules import (
    build_collection_dashboard,
    dedupe_vehicle_daily_status,
    parse_human_driving_output_records,
    parse_vehicle_status_rows,
    summarize_vehicle_daily_status,
)
from domain.weekly_report.rules import parse_single_file
from jobs.generate_collection_dashboard import (
    generate_collection_dashboard,
    load_collection_dashboard_config,
)
from jobs.openclaw_collection_dashboard import build_openclaw_cron_args


def _csv_text(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    return buffer.getvalue()


def _sample_collection_csv() -> str:
    headers = [
        "时间",
        "区域/停车场",
        "计划\n出车数量",
        "实际可\n出车数量",
        "采集任务",
        "班次",
        "传感器",
        "序号",
        "车号",
        "出车人SD",
        "出车时间",
        "出车\n硬盘容量",
        "出车\n电量",
        "收车\n硬盘容量",
        "收车\n电量",
        "要换盘\n(<800G)",
        "要换电\n(X3<80%/X6<60% )",
        "出车异常记录",
        "数采问题记录",
        "采集总容量/G",
        "寄出容量/G",
        "有效采集时间/h",
    ]
    return _csv_text(
        [
            ["daily title"],
            headers,
            ["2026/5/11", "城阳", "3", "2", "任务A", "白班", "MID360", "1", "X3S1060", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["", "", "", "", "任务B", "白班", "MID360", "2", "X3S1061", "张三", "9:05", "1.3T", "99%", "", "", "", "", "一直在换车", "掉接管", "100", "", "0.42"],
            ["", "", "", "", "任务C", "白班", "MID360", "3", "X3S1062", "5.7扣车", "", "", "", "", "", "", "", "扣车", "", "", "", ""],
            ["2026/5/10", "城阳", "1", "1", "任务A", "白班", "MID360", "1", "X3S1061", "李四", "9:10", "1.1T", "98%", "", "", "", "", "", "", "200", "", "0.83"],
        ]
    )


def _sample_split_task_csv() -> str:
    headers = [
        "时间",
        "区域/停车场",
        "计划出车数量",
        "实际可出车数量",
        "白班_采集任务",
        "夜班_采集任务",
        "班次",
        "传感器",
        "序号",
        "车号",
        "出车人SD",
        "出车时间",
        "出车硬盘容量",
        "出车电量",
        "收车硬盘容量",
        "收车电量",
        "要换盘(<800G)",
        "要换电(X3<80%/X6<60% )",
        "出车异常记录",
        "数采问题记录",
        "采集总容量/G",
        "寄出容量/G",
        "有效采集时间/h",
    ]
    return _csv_text(
        [
            ["daily title"],
            headers,
            ["2026/5/12", "城阳", "2", "2", "白班 TLD 数据回灌", "夜班 TLD 数据回灌", "白班", "MID360", "1", "X3S1061", "张三", "09:05", "1.3T", "99%", "", "", "", "", "", "", "100", "", "0.42"],
            ["", "", "", "", "", "", "夜班", "MID360", "2", "X3S1062", "李四", "19:10", "1.1T", "96%", "", "", "", "", "", "", "120", "", "0.50"],
            ["", "", "", "", "白班 停车场场景", "夜班 停车场场景", "白班", "MID360", "3", "X3S1063", "", "", "", "", "", "", "", "", "", "", "", "", ""],
        ]
    )


def _sample_duplicate_attendance_csv() -> str:
    headers = [
        "时间",
        "区域/停车场",
        "计划出车数量",
        "实际可出车数量",
        "采集任务",
        "班次",
        "传感器",
        "序号",
        "车号",
        "出车人SD",
        "出车时间",
        "采集总容量/G",
        "有效采集时间/h",
    ]
    return _csv_text(
        [
            ["daily title"],
            headers,
            ["2026/5/11", "城阳", "3", "3", "任务A", "白班", "MID360", "1", "X3S1001", "张三", "09:05", "100", "0.5"],
            ["", "", "", "", "任务A", "白班", "MID360", "2", "X3S1002", "张三", "09:30", "100", "0.5"],
            ["", "", "", "", "任务B", "夜班", "MID360", "3", "X3S1003", "李四", "19:30", "100", "0.5"],
            ["2026/5/10", "城阳", "1", "1", "任务A", "白班", "MID360", "1", "X3S1001", "张三", "09:10", "100", "0.5"],
        ]
    )


def _sample_human_schedule_csv() -> str:
    return _csv_text(
        [
            [
                "时间",
                "计划\n出车数量",
                "实际可\n出车数量",
                "采集任务",
                "班次",
                "序号",
                "车号",
                "出车人",
                "出车时间",
                "出车异常记录",
                "数采问题记录",
            ],
            ["2026/5/11", "2", "1", "青岛城区采集", "白班", "1", "QDRJ-001", "", "", "", ""],
            ["", "", "", "青岛园区采集", "白班", "2", "QDRJ-002", "王五", "09:20", "临时换车", ""],
        ]
    )


def _sample_human_output_csv() -> str:
    return _csv_text(
        [
            [
                "是否已取数（SD不填）",
                "车号2",
                "车号",
                "采集开始时间",
                "采集结束时间",
                "采集场景",
                "时长min & clips",
                "采集场景",
                "起点名称",
                "里程数/km",
                "采集员",
                "异常情况备注",
                "日期",
            ],
            ["是", "", "YCRJ-001", "46153.375", "46153.479166666664", "城区道路", "", "人民路", "A点", "12.8km", "赵六", "雨天待复核", "46153"],
        ]
    )


class CollectionDataDashboardTests(unittest.TestCase):
    def test_vehicle_status_uses_driver_assignment_and_ignores_exception_columns(self):
        rows = parse_vehicle_status_rows(_sample_collection_csv(), "source_001")
        daily = dedupe_vehicle_daily_status(rows)
        by_key = {(item["date"], item["car_number"]): item for item in daily}

        self.assertEqual(by_key[("2026-05-11", "X3S1060")]["status"], "idle")
        self.assertEqual(by_key[("2026-05-11", "X3S1061")]["status"], "active")
        self.assertEqual(by_key[("2026-05-11", "X3S1061")]["drivers"], ["张三"])
        self.assertIn("出车异常记录", by_key[("2026-05-11", "X3S1061")]["ignored_note_columns"])
        self.assertIn("数采问题记录", by_key[("2026-05-11", "X3S1061")]["ignored_note_columns"])
        self.assertEqual(by_key[("2026-05-11", "X3S1062")]["status"], "abnormal")
        self.assertIn("5.7扣车", by_key[("2026-05-11", "X3S1062")]["status_reason"])

        summary = summarize_vehicle_daily_status(daily)
        current = {item["date"]: item for item in summary}["2026-05-11"]
        self.assertEqual(current["vehicle_count"], 3)
        self.assertEqual(current["active_count"], 1)
        self.assertEqual(current["idle_count"], 1)
        self.assertEqual(current["abnormal_count"], 1)

    def test_split_day_night_task_columns_are_bound_by_shift(self):
        records, diagnostics = parse_single_file(_sample_split_task_csv(), "source_001")
        by_driver = {record.driver: record for record in records}

        self.assertEqual(by_driver["张三"].task, "白班 TLD 数据回灌")
        self.assertEqual(by_driver["李四"].task, "夜班 TLD 数据回灌")
        self.assertEqual(diagnostics, [])

        rows = parse_vehicle_status_rows(_sample_split_task_csv(), "source_001")
        by_car = {row["car_number"]: row for row in rows}
        self.assertEqual(by_car["X3S1061"]["task"], "白班 TLD 数据回灌")
        self.assertEqual(by_car["X3S1062"]["task"], "夜班 TLD 数据回灌")
        self.assertEqual(by_car["X3S1063"]["task"], "白班 停车场场景")

    def test_build_collection_dashboard_returns_period_views_and_vehicle_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "source_001.csv"
            raw_path.write_text(_sample_collection_csv(), encoding="utf-8")

            dashboard = build_collection_dashboard([raw_path], anchor_date=date(2026, 5, 11))

        self.assertEqual(dashboard["dashboard_id"], "collection_data_dashboard")
        self.assertEqual(dashboard["anchor_date"], "2026-05-11")
        self.assertEqual(dashboard["record_count"], 2)
        self.assertEqual(dashboard["vehicle_status_summary_by_date"]["2026-05-11"]["active_count"], 1)
        self.assertEqual(dashboard["vehicle_status_summary_by_date"]["2026-05-11"]["idle_count"], 1)
        self.assertEqual(dashboard["vehicle_status_summary_by_date"]["2026-05-11"]["abnormal_count"], 1)
        for grain in ("day", "week", "month", "year"):
            self.assertIn(grain, dashboard["period_views"])
            self.assertIn("stable_participant_coverage", dashboard["period_views"][grain]["metrics"])
            self.assertIn("sd_per_day", dashboard["period_views"][grain]["metrics"])
            self.assertIn("top5_tasks", dashboard["period_views"][grain])
            self.assertIn("comparison", dashboard["period_views"][grain])

    def test_frontend_payload_uses_daily_deduped_sd_units(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "source_001.csv"
            raw_path.write_text(_sample_duplicate_attendance_csv(), encoding="utf-8")
            dashboard = build_collection_dashboard([raw_path], anchor_date=date(2026, 5, 11))

        payload = build_collection_frontend_payload(dashboard)
        units = payload["task_attendance_units"]
        by_date = {}
        for item in units:
            by_date.setdefault(item["date"], set()).add(item["driver"])

        self.assertEqual(len(by_date["2026-05-11"]), 2)
        self.assertEqual(len(by_date["2026-05-10"]), 1)
        self.assertEqual(len(units), 3)
        self.assertEqual(payload["date_bounds"], {"min": "2026-05-10", "max": "2026-05-11"})

    def test_human_schedule_source_supports_first_row_headers_and_empty_driver(self):
        metadata = {
            "department": "人驾",
            "site": "青岛",
            "source_role": "resource_schedule",
            "parser": "human_driving_schedule",
        }
        rows = parse_vehicle_status_rows(_sample_human_schedule_csv(), "human_qingdao_schedule", metadata=metadata)
        by_car = {row["car_number"]: row for row in rows}

        self.assertEqual(by_car["QDRJ-001"]["department"], "人驾")
        self.assertEqual(by_car["QDRJ-001"]["site"], "青岛")
        self.assertEqual(by_car["QDRJ-001"]["status"], "idle")
        self.assertEqual(by_car["QDRJ-002"]["status"], "active")
        self.assertEqual(by_car["QDRJ-002"]["drivers"], ["王五"])
        self.assertEqual(by_car["QDRJ-002"]["task"], "青岛园区采集")
        self.assertIn("出车异常记录", by_car["QDRJ-002"]["ignored_note_columns"])

    def test_human_output_source_parses_lark_serial_times_and_fallback_car_column(self):
        metadata = {
            "department": "人驾",
            "site": "盐城",
            "source_role": "collection_output",
            "parser": "human_driving_output",
        }
        rows = parse_human_driving_output_records(_sample_human_output_csv(), "human_yancheng_trial", metadata=metadata)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["date"], "2026-05-11")
        self.assertEqual(row["department"], "人驾")
        self.assertEqual(row["site"], "盐城")
        self.assertEqual(row["car_number"], "YCRJ-001")
        self.assertEqual(row["collector"], "赵六")
        self.assertEqual(row["start_time"], "2026-05-11 09:00")
        self.assertEqual(row["end_time"], "2026-05-11 11:30")
        self.assertEqual(row["duration_minutes"], 150.0)
        self.assertEqual(row["mileage_km"], 12.8)
        self.assertEqual(row["exception_note"], "雨天待复核")

    def test_local_app_renderer_is_self_contained_and_uses_neutral_resource_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "source_001.csv"
            schedule_path = Path(temp_dir) / "human_qingdao_schedule.csv"
            output_path = Path(temp_dir) / "human_yancheng_trial.csv"
            raw_path.write_text(_sample_collection_csv(), encoding="utf-8")
            schedule_path.write_text(_sample_human_schedule_csv(), encoding="utf-8")
            output_path.write_text(_sample_human_output_csv(), encoding="utf-8")
            dashboard = build_collection_dashboard(
                [raw_path, schedule_path, output_path],
                anchor_date=date(2026, 5, 11),
                source_metadata={
                    "source_001": {
                        "department": "数采",
                        "site": "数采",
                        "source_role": "resource_schedule",
                        "parser": "collection_detail",
                    },
                    "human_qingdao_schedule": {
                        "department": "人驾",
                        "site": "青岛",
                        "source_role": "resource_schedule",
                        "parser": "human_driving_schedule",
                    },
                    "human_yancheng_trial": {
                        "department": "人驾",
                        "site": "盐城",
                        "source_role": "collection_output",
                        "parser": "human_driving_output",
                    },
                },
            )

        weekly_report = {
            "week_id": "2026-W19",
            "period": {"start_date": "2026-05-04", "end_date": "2026-05-10"},
            "kpis": {"total_attendance": 12, "unique_drivers": 4, "avg_daily_sd": 2.4},
            "focus_summary": {
                "top5_tasks": [{"rank": 1, "task": "任务A", "current_total": 8, "previous_total": 6, "delta": 2, "white": 5, "night": 3}],
                "top_task_personnel_stability": [{"task": "任务A", "continued_driver_count": 2, "new_driver_count": 1, "risk_level": "low"}],
            },
            "risk_items": [{"type": "vehicle_quality", "target": "X3S1001", "reason": "异常", "level": "high"}],
        }
        html = render_collection_dashboard_local_app(dashboard, weekly_report=weekly_report)

        self.assertIn('data-app="collection-dashboard-local"', html)
        self.assertIn('id="collection-dashboard-data"', html)
        self.assertIn('type="application/json"', html)
        self.assertIn("资源总览", html)
        self.assertIn("数采调度", html)
        self.assertIn("人驾调度", html)
        self.assertIn("周报", html)
        self.assertIn("人驾 KPI", html)
        self.assertIn('data-section="overview-controls"', html)
        self.assertIn('data-action="overview-prev-day"', html)
        self.assertIn('data-action="overview-next-day"', html)
        self.assertIn('data-control="start-date"', html)
        self.assertIn('data-control="end-date"', html)
        self.assertIn('data-page="dispatch"', html)
        self.assertIn('data-page-panel="dispatch"', html)
        self.assertIn('data-section="dispatch-controls"', html)
        self.assertIn('data-control="dispatch-start-date"', html)
        self.assertIn('data-control="dispatch-end-date"', html)
        self.assertIn('data-action="dispatch-prev-day"', html)
        self.assertIn('data-action="dispatch-next-day"', html)
        self.assertIn('data-page="human-dispatch"', html)
        self.assertIn('data-page-panel="human-dispatch"', html)
        self.assertIn('data-section="human-dispatch-controls"', html)
        self.assertIn('data-control="human-start-date"', html)
        self.assertIn('data-control="human-end-date"', html)
        self.assertIn('data-action="human-prev-day"', html)
        self.assertIn('data-action="human-next-day"', html)
        self.assertIn('data-action="apply-human-date-range"', html)
        self.assertIn("buildHumanRangeView", html)
        self.assertIn("applyHumanDateRange", html)
        self.assertIn("applyDispatchDateRange", html)
        self.assertIn("buildDispatchRangeView", html)
        self.assertIn("shiftDateRange", html)
        self.assertIn('data-page="weekly"', html)
        self.assertIn("2026-W19", html)
        self.assertNotIn("fetch('collection_dashboard.json'", html)
        self.assertNotIn('data-section="metric-registry"', html)
        self.assertNotIn("可配置指标", html)
        self.assertNotIn("数采 vs 人驾", html)
        self.assertNotIn("对比矩阵", html)
        self.assertNotIn("优劣", html)

    def test_local_app_payload_separates_collection_and_human_dispatch_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "source_001.csv"
            schedule_path = Path(temp_dir) / "human_qingdao_schedule.csv"
            output_path = Path(temp_dir) / "human_yancheng_trial.csv"
            raw_path.write_text(_sample_collection_csv(), encoding="utf-8")
            schedule_path.write_text(_sample_human_schedule_csv(), encoding="utf-8")
            output_path.write_text(_sample_human_output_csv(), encoding="utf-8")
            dashboard = build_collection_dashboard(
                [raw_path, schedule_path, output_path],
                anchor_date=date(2026, 5, 11),
                source_metadata={
                    "source_001": {
                        "department": "数采",
                        "site": "数采",
                        "source_role": "resource_schedule",
                        "parser": "collection_detail",
                    },
                    "human_qingdao_schedule": {
                        "department": "人驾",
                        "site": "青岛",
                        "source_role": "resource_schedule",
                        "parser": "human_driving_schedule",
                    },
                    "human_yancheng_trial": {
                        "department": "人驾",
                        "site": "盐城",
                        "source_role": "collection_output",
                        "parser": "human_driving_output",
                    },
                },
            )

        payload = build_collection_frontend_payload(dashboard)

        self.assertTrue(payload["dispatch_vehicle_daily_status"])
        self.assertTrue(payload["human_dispatch_vehicle_daily_status"])
        self.assertTrue(all(row["parser"] == "collection_detail" for row in payload["dispatch_vehicle_daily_status"]))
        self.assertTrue(all(row["parser"] == "human_driving_schedule" for row in payload["human_dispatch_vehicle_daily_status"]))
        self.assertEqual(payload["human_dispatch_summary"]["schedule_count"], 2)
        self.assertEqual(payload["human_dispatch_summary"]["output_count"], 1)
        self.assertEqual(payload["human_dispatch_summary"]["output_mileage_km"], 12.8)
        self.assertEqual(payload["human_dispatch_task_rankings"][0]["task"], "青岛园区采集")
        self.assertEqual(payload["human_dispatch_output_rankings"][0]["label"], "A点")
        self.assertEqual(len(payload["human_dispatch_risks"]), 2)

    def test_collection_dashboard_renderers_are_iframe_ready_and_dashboard_styled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "source_001.csv"
            raw_path.write_text(_sample_collection_csv(), encoding="utf-8")
            dashboard = build_collection_dashboard([raw_path], anchor_date=date(2026, 5, 11))

        html = render_collection_dashboard_embed(dashboard)
        preview = render_collection_dashboard_iframe_preview()

        self.assertIn('data-dashboard="collection-data-dashboard"', html)
        self.assertIn('data-section="period-tabs"', html)
        self.assertIn('data-section="vehicle-status"', html)
        self.assertIn('data-section="task-top5"', html)
        self.assertIn("Neolix DriveStack", preview)
        self.assertIn("<iframe", preview)
        self.assertIn('src="collection_data_dashboard_embed.html"', preview)
        self.assertNotIn('<header class="hero"', html)
        self.assertIn('data-control="date-range"', html)
        self.assertIn('data-control="start-date"', html)
        self.assertIn('data-control="end-date"', html)
        self.assertIn('data-action="apply-date-range"', html)
        self.assertNotIn('data-control="period-grain"', html)
        self.assertIn('data-action="open-vehicle-day"', html)
        self.assertIn('id="vehicle-drawer"', html)
        self.assertIn("function applyDateRange", html)
        self.assertIn("function buildRangeView", html)
        self.assertIn("collection_dashboard.json", html)

    def test_metric_config_controls_enabled_metrics_and_unknown_compute_errors(self):
        metric_config = load_collection_metric_config(REPO_ROOT / "config" / "collection_dashboard_metrics.yaml")
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "source_001.csv"
            raw_path.write_text(_sample_collection_csv(), encoding="utf-8")
            dashboard = build_collection_dashboard([raw_path], anchor_date=date(2026, 5, 11))

        attach_configured_metrics(dashboard, metric_config)

        day_groups = dashboard["period_views"]["day"]["configured_metric_groups"]
        metric_ids = [
            metric["id"]
            for group in day_groups
            for metric in group["metrics"]
        ]
        self.assertIn("active_people", metric_ids)
        self.assertIn("vehicle_abnormal_count", metric_ids)
        self.assertIn("dashboard_total_collections", metric_ids)
        self.assertIn("metric_config_loaded", [item["code"] for item in dashboard["metric_diagnostics"]])

        bad_config = {
            "metric_groups": [{"id": "bad", "name": "Bad", "enabled": True, "order": 1}],
            "metrics": [
                {
                    "id": "bad_metric",
                    "group": "bad",
                    "name": "Bad Metric",
                    "enabled": True,
                    "compute": "not_registered",
                    "display": "number",
                    "order": 1,
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "Unknown collection dashboard metric compute function"):
            attach_configured_metrics(dashboard, bad_config)

    def test_collection_dashboard_config_and_openclaw_daily_entrypoint(self):
        config = load_collection_dashboard_config(REPO_ROOT / "config" / "collection_dashboard.yaml")
        self.assertEqual(config.cron, "0 */2 * * *")
        self.assertEqual(config.timezone, "Asia/Shanghai")
        self.assertEqual(config.output_base_dir, "data/collection-dashboard")
        self.assertEqual(Path(config.weekly_sources_config).name, "weekly_sources.yaml")
        self.assertEqual(Path(config.metric_config).name, "collection_dashboard_metrics.yaml")
        self.assertEqual(len(config.sources), 8)

        args = build_openclaw_cron_args(config)
        self.assertIn("--name", args)
        self.assertEqual(args[args.index("--name") + 1], "collection-data-dashboard-refresh")
        self.assertEqual(args[args.index("--cron") + 1], "0 */2 * * *")
        message = args[args.index("--message") + 1]
        self.assertIn("generate_collection_dashboard.py", message)
        self.assertIn("data/collection-dashboard/latest", message)
        self.assertIn("出车异常记录与数采问题记录不参与判定", message)

    def test_generate_collection_dashboard_from_raw_snapshot_writes_latest_and_warehouse(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_raw_dir = root / "input_raw"
            input_raw_dir.mkdir()
            (input_raw_dir / "source_001.csv").write_text(_sample_collection_csv(), encoding="utf-8")
            (input_raw_dir / "human_qingdao_schedule.csv").write_text(_sample_human_schedule_csv(), encoding="utf-8")
            (input_raw_dir / "human_yancheng_trial.csv").write_text(_sample_human_output_csv(), encoding="utf-8")
            (input_raw_dir / "dashboard_overview.json").write_text(
                json.dumps(
                    {
                        "kpis": {
                            "采集总次数": {"label": "采集总次数", "value": "12", "sub": "2026-05-11"},
                            "入库率": {"label": "入库率", "value": "75%", "sub": "采集 -> BOS"},
                            "Record 文件": {"label": "Record 文件", "value": "100", "sub": "Records"},
                        },
                        "scene_summary": [],
                        "vehicle_collection_summary": [],
                        "vehicle_quality_summary": [],
                        "diagnostics": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path = root / "collection_dashboard.yaml"
            output_base_dir = root / "collection-dashboard"
            config_path.write_text(
                "\n".join(
                    [
                        "schedule:",
                        '  cron: "0 9 * * *"',
                        '  timezone: "Asia/Shanghai"',
                        '  refresh_mode: "daily_snapshot"',
                        "output:",
                        '  mode: "local"',
                        f'  base_dir: "{output_base_dir.as_posix()}"',
                        "  update_latest: true",
                        "sources:",
                        f'  include: "{(REPO_ROOT / "config" / "weekly_sources.yaml").as_posix()}"',
                        f'metric_config: "{(REPO_ROOT / "config" / "collection_dashboard_metrics.yaml").as_posix()}"',
                    ]
                ),
                encoding="utf-8",
            )

            result = generate_collection_dashboard(
                config_path,
                from_raw_dir=input_raw_dir,
                anchor_date=date(2026, 5, 11),
                run_id="2026-05-11T09-00-00",
            )

            latest_dir = output_base_dir / "latest"
            self.assertEqual(result["status"], "collection_dashboard_generated")
            self.assertTrue((latest_dir / "collection_dashboard.json").exists())
            self.assertTrue((latest_dir / "collection_data_dashboard.html").exists())
            self.assertTrue((latest_dir / "collection_data_dashboard_embed.html").exists())
            self.assertTrue((latest_dir / "collection_data_dashboard_iframe_preview.html").exists())
            self.assertTrue((latest_dir / "raw" / "source_001.csv").exists())
            self.assertTrue((latest_dir / "raw" / "human_qingdao_schedule.csv").exists())
            self.assertTrue((latest_dir / "raw" / "human_yancheng_trial.csv").exists())
            self.assertTrue((output_base_dir / "warehouse" / "collection_records.jsonl").exists())
            self.assertTrue((output_base_dir / "warehouse" / "vehicle_daily_status.jsonl").exists())
            self.assertTrue((output_base_dir / "warehouse" / "resource_schedule_records.jsonl").exists())
            self.assertTrue((output_base_dir / "warehouse" / "collection_output_records.jsonl").exists())

            payload = json.loads((latest_dir / "collection_dashboard.json").read_text(encoding="utf-8"))
            manifest = json.loads((latest_dir / "sources_manifest.json").read_text(encoding="utf-8"))
            manifest_by_id = {item["source_id"]: item for item in manifest}
            self.assertEqual(manifest_by_id["human_qingdao_schedule"]["source_type"], "human_driving_schedule")
            self.assertEqual(manifest_by_id["human_qingdao_schedule"]["parser"], "human_driving_schedule")
            self.assertEqual(manifest_by_id["human_yancheng_trial"]["source_type"], "human_driving_output")
            self.assertEqual(manifest_by_id["human_yancheng_trial"]["parser"], "human_driving_output")
            self.assertEqual(payload["vehicle_status_summary_by_date"]["2026-05-11"]["abnormal_count"], 1)
            self.assertEqual(len(payload["collection_output_records"]), 1)
            self.assertEqual(
                len([row for row in payload["resource_schedule_records"] if row["source"] == "human_qingdao_schedule"]),
                2,
            )
            self.assertIn("configured_metric_groups", payload)
            local_html = (latest_dir / "collection_data_dashboard.html").read_text(encoding="utf-8")
            self.assertIn('data-app="collection-dashboard-local"', local_html)
            self.assertIn('id="collection-dashboard-data"', local_html)
            self.assertIn("暂无周报数据", local_html)
            self.assertIn("资源总览", local_html)
            self.assertIn("人驾调度", local_html)
            self.assertNotIn("fetch('collection_dashboard.json'", local_html)
            self.assertNotIn('data-section="metric-registry"', local_html)
            html = (latest_dir / "collection_data_dashboard_embed.html").read_text(encoding="utf-8")
            self.assertIn('data-section="metric-registry"', html)
            self.assertIn('data-section="production-quality"', html)

    def test_collection_dashboard_entrypoints_dry_run_by_file_path(self):
        cron = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "backend" / "jobs" / "openclaw_collection_dashboard.py"),
                "--config",
                str(REPO_ROOT / "config" / "collection_dashboard.yaml"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(cron.returncode, 0, cron.stderr)
        self.assertIn("collection-data-dashboard-refresh", cron.stdout)

        dry_run = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "backend" / "jobs" / "generate_collection_dashboard.py"),
                "--config",
                str(REPO_ROOT / "config" / "collection_dashboard.yaml"),
                "--run-id",
                "2026-05-11T09-00-00",
                "--dry-run",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn('"source_count": 8', dry_run.stdout)
        self.assertIn('"latest_dir": "data/collection-dashboard/latest"', dry_run.stdout)


if __name__ == "__main__":
    unittest.main()
