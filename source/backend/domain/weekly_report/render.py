"""Renderers for the weekly SD scheduling-control report."""

from __future__ import annotations

from html import escape
from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    focus = report.get("focus_summary") or {}
    resource = focus.get("resource_collection_status") or {}
    index = focus.get("scheduling_control_index") or {}
    overview = focus.get("scheduling_control_overview") or {}
    period = report.get("period") or {}
    previous_period = focus.get("previous_period") or {}
    kpis = report.get("kpis") or {}
    stability_rows = focus.get("top_task_personnel_stability") or []
    person_rows = report.get("person_attendance_summary") or report.get("driver_summary") or []

    lines = [
        f"# SD资源采集周报｜{report.get('week_id') or ''}".strip(),
        "",
        f"本周周期：{period.get('start_date') or '-'} 至 {period.get('end_date') or '-'}",
        f"对比周期：{previous_period.get('start_date') or '-'} 至 {previous_period.get('end_date') or '-'}",
        "",
        "## 1. 资源采集状态",
        f"- 本周 SD个数/天：**{_fmt_number(resource.get('current_value'))}**",
        f"- 上周 SD个数/天：**{_fmt_number(resource.get('previous_value'))}**",
        f"- 环比变化：**{_fmt_delta(resource.get('delta'), resource.get('delta_pct'))}**",
        f"- 口径：飞书汇总表实出人数优先；缺失日期使用明细去重人数替代。",
        "",
        "## 2. 排班可控指数",
        f"- 重点任务池排班可控指数：**{index.get('score', 0)} / 100**",
        f"- 当前状态：**{index.get('status') or '-'}**",
        f"- 重点任务池：{overview.get('focus_task_count', 0)} 个任务，{overview.get('focus_pool_total', 0)} 人次。",
        f"- 稳定参与者覆盖率：{_fmt_pct(overview.get('stable_candidate_coverage'))}；临时参与者占比：{_fmt_pct(overview.get('temporary_participant_share'))}。",
        "",
        "## 3. Top 任务量级",
        "",
        "| 排名 | 采集任务 | 本周人次 | 上周同任务 | 环比 | 本周白/夜班 |",
        "|---:|---|---:|---:|---:|---|",
    ]

    for item in focus.get("top5_tasks") or []:
        lines.append(
            "| {rank} | {task} | {current} | {previous} | {delta} | {white}/{night} |".format(
                rank=item.get("rank", "-"),
                task=item.get("task") or "-",
                current=item.get("current_total", 0),
                previous=item.get("previous_total", 0),
                delta=_fmt_delta(item.get("delta"), item.get("delta_pct")),
                white=item.get("white", 0),
                night=item.get("night", 0),
            )
        )
    if not focus.get("top5_tasks"):
        lines.append("| - | 暂无数据 | 0 | 0 | - | - |")

    lines.extend(
        [
            "",
            "## 4. Top 任务人员稳定性",
            "",
            "| 采集任务 | 延续人数 | 新进人数 | 新进人次占比 | 每日换手率 | 最大连续承接天数 | 风险等级 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in stability_rows:
        lines.append(
            "| {task} | {continued} | {new} | {new_share} | {turnover} | {max_days} | {risk} |".format(
                task=item.get("task") or "-",
                continued=item.get("continued_driver_count", 0),
                new=item.get("new_driver_count", 0),
                new_share=_fmt_pct(item.get("new_attendance_share")),
                turnover=_fmt_pct(item.get("daily_turnover_rate")),
                max_days=item.get("max_consecutive_days", 0),
                risk=item.get("risk_level") or "-",
            )
        )
    if not stability_rows:
        lines.append("| - | 0 | 0 | 0.0% | 0.0% | 0 | 暂无数据 |")

    lines.extend(
        [
            "",
            "## 5. 个人出勤投入（Top 10）",
            "",
            "| 人员 | 出勤天数 | 人次 | 白/夜班 | 参与任务数 | Top任务人次 | 主要任务 | 有效采集时间 |",
            "|---|---:|---:|---|---:|---:|---|---:|",
        ]
    )
    for item in person_rows[:10]:
        lines.append(
            "| {driver} | {days} | {total} | {white}/{night} | {task_count} | {top_count} | {primary_task} | {effective_time} |".format(
                driver=item.get("driver") or "-",
                days=item.get("attendance_days", 0),
                total=item.get("total_attendance", item.get("total", 0)),
                white=item.get("white", 0),
                night=item.get("night", 0),
                task_count=item.get("task_count", len(item.get("tasks") or [])),
                top_count=item.get("top_task_attendance", 0),
                primary_task=item.get("primary_task") or "-",
                effective_time=_fmt_number(item.get("effective_collection_time", 0)),
            )
        )
    if not person_rows:
        lines.append("| - | 0 | 0 | - | 0 | 0 | - | 0 |")

    notes = focus.get("robust_metric_notes") or []
    lines.extend(
        [
            "",
            "## 6. 资源管理补充指标",
            "",
            *_resource_metrics_markdown(report),
            "",
            "## 7. 数据说明",
            f"- 本周总出勤人次：{kpis.get('total_attendance', 0)}；白班：{kpis.get('white_attendance', 0)}；夜班：{kpis.get('night_attendance', 0)}。",
            f"- 本周出车人数：{kpis.get('unique_drivers', 0)}；任务类型：{kpis.get('task_types', 0)}。",
            f"- 诊断记录数：{report.get('diagnostics_count', 0)}，完整解析明细见 `report.json`，任务 drilldown 见 `details.html`。",
        ]
    )
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def render_html(report: dict[str, Any]) -> str:
    focus = report.get("focus_summary") or {}
    resource = focus.get("resource_collection_status") or {}
    index = focus.get("scheduling_control_index") or {}
    overview = focus.get("scheduling_control_overview") or {}
    period = report.get("period") or {}
    previous_period = focus.get("previous_period") or {}
    kpis = report.get("kpis") or {}
    history = report.get("available_reports") or []

    top_rows = "".join(_top_task_row(item) for item in focus.get("top5_tasks") or [])
    if not top_rows:
        top_rows = "<tr><td colspan='7' class='empty'>暂无数据</td></tr>"
    stability_rows = "".join(_stability_row(item) for item in focus.get("top_task_personnel_stability") or [])
    if not stability_rows:
        stability_rows = "<tr><td colspan='7' class='empty'>暂无人员稳定性数据</td></tr>"
    matrix_rows = "".join(_matrix_task_rows(item) for item in focus.get("top_task_daily_personnel_matrix") or [])
    if not matrix_rows:
        matrix_rows = "<tr><td colspan='8' class='empty'>暂无每日人员矩阵</td></tr>"
    person_rows = "".join(_person_row(item) for item in (report.get("person_attendance_summary") or report.get("driver_summary") or [])[:20])
    if not person_rows:
        person_rows = "<tr><td colspan='8' class='empty'>暂无个人投入数据</td></tr>"
    component_rows = "".join(_component_row(item) for item in (index.get("components") or {}).values())
    tier_rows = "".join(_tier_row(label, focus.get("task_volume_tiers", {}).get(key) or []) for key, label in (("high", "高量级"), ("medium", "中量级"), ("low", "低量级")))
    resource_metric_sections = _resource_metrics_html(report)
    dashboard_collection_rows = _dashboard_collection_rows(report)
    dashboard_quality_rows = _dashboard_quality_rows(report)
    risk_rows = _risk_item_rows(report.get("risk_items") or [])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>SD资源采集周报</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',sans-serif;background:#f4f6f8;color:#20242c;line-height:1.55}}.hero{{background:#102033;color:#fff;padding:28px 34px;border-bottom:4px solid #227950}}.hero-grid{{max-width:1260px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:22px;align-items:end}}h1{{font-size:26px;margin:0 0 10px;font-weight:800}}.hero-meta{{display:flex;flex-wrap:wrap;gap:6px 14px;color:#d8e0ea;font-size:13px}}.history label{{display:block;font-size:12px;color:#b7c2d0;margin-bottom:6px}}.history select{{width:100%;border:1px solid #3c5067;background:#0b1725;color:#fff;border-radius:6px;padding:9px 10px}}.wrap{{max-width:1260px;margin:0 auto;padding:22px 26px 36px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px}}.card{{background:#fff;border:1px solid #dde5ee;border-radius:8px;padding:15px}}.label{{font-size:12px;color:#667085;margin-bottom:7px}}.value{{font-size:30px;line-height:1;font-weight:850;color:#16477e}}.sub{{font-size:12px;color:#667085;margin-top:9px}}.status{{display:inline-flex;border-radius:999px;padding:5px 10px;font-weight:800;font-size:12px;background:#e8f5ee;color:#17663d}}.status-watch{{background:#fff3d6;color:#9a5b00}}.status-risk,.risk-high{{background:#ffe4e0;color:#a53120}}.risk-medium{{background:#fff3d6;color:#9a5b00}}.risk-low{{background:#e8f5ee;color:#17663d}}.risk{{display:inline-flex;border-radius:999px;padding:4px 9px;font-weight:800;font-size:12px}}.section{{background:#fff;border:1px solid #dde5ee;border-radius:8px;margin-top:14px;overflow:hidden}}.section-head{{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:14px 16px;border-bottom:1px solid #e8edf3;background:#fbfcfd}}.section-title{{font-size:15px;font-weight:800}}.section-sub{{font-size:12px;color:#667085}}.detail-link{{color:#175cd3;text-decoration:none;font-weight:800}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;min-width:760px}}th{{background:#f2f5f8;color:#344054;text-align:center;font-weight:750;padding:10px 12px;border-bottom:1px solid #d7e0ea}}td{{padding:10px 12px;border-bottom:1px solid #edf1f5;text-align:center;vertical-align:top}}td.left{{text-align:left;font-weight:650}}.empty{{color:#98a2b3;padding:20px}}.bar{{height:8px;background:#e8edf3;border-radius:999px;overflow:hidden;min-width:100px}}.bar span{{display:block;height:100%;background:#227950}}.note{{padding:12px 16px;color:#667085;font-size:12px;border-top:1px solid #eef2f6;background:#fbfcfd}}.delta-up{{color:#b42318;font-weight:800}}.delta-down{{color:#067647;font-weight:800}}.delta-flat{{color:#475467;font-weight:800}}@media(max-width:900px){{.hero-grid{{grid-template-columns:1fr}}.grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.wrap,.hero{{padding-left:16px;padding-right:16px}}}}@media(max-width:560px){{.grid{{grid-template-columns:1fr}}h1{{font-size:22px}}}}
</style>
</head>
<body>
<header class="hero">
  <div class="hero-grid">
    <div>
      <h1>SD资源采集周报｜{_e(report.get('week_id') or '')}</h1>
      <div class="hero-meta"><span>本周：{_e(period.get('start_date'))} 至 {_e(period.get('end_date'))}</span><span>对比：{_e(previous_period.get('start_date'))} 至 {_e(previous_period.get('end_date'))}</span><span>生成：{_e(_fmt_generated_at(report.get('generated_at')))}</span></div>
    </div>
    <div class="history" data-section="weekly-history">
      <label for="week-select">查看历史周报</label>
      {_history_select(history)}
    </div>
  </div>
</header>
<main class="wrap">
  <section class="grid" data-section="scheduling-control-index">
    <div class="card"><div class="label">排班可控指数</div><div class="value">{_e(index.get('score', 0))}</div><div class="sub"><span class="{_status_class(index.get('status'))}">{_e(index.get('status') or '-')}</span></div></div>
    <div class="card"><div class="label">重点任务池</div><div class="value">{_e(overview.get('focus_task_count', 0))}</div><div class="sub">{_e(overview.get('focus_pool_total', 0))} 人次纳入宏观判断</div></div>
    <div class="card"><div class="label">稳定参与者覆盖率</div><div class="value">{_e(_fmt_pct(overview.get('stable_candidate_coverage')))}</div><div class="sub">历史候选口径，不代表负责人</div></div>
    <div class="card"><div class="label">临时参与者占比</div><div class="value">{_e(_fmt_pct(overview.get('temporary_participant_share')))}</div><div class="sub"><a class="detail-link" href="details.html">查看任务详情</a></div></div>
  </section>

  <section class="grid">
    <div class="card"><div class="label">本周 SD个数/天</div><div class="value">{_e(_fmt_number(resource.get('current_value')))}</div><div class="sub">{_e(resource.get('current_total_attendance', 0))} 实出 / {_e(resource.get('current_attendance_days', 0))} 天</div></div>
    <div class="card"><div class="label">上周 SD个数/天</div><div class="value">{_e(_fmt_number(resource.get('previous_value')))}</div><div class="sub">{_e(resource.get('previous_total_attendance', 0))} 实出 / {_e(resource.get('previous_attendance_days', 0))} 天</div></div>
    <div class="card"><div class="label">环比变化</div><div class="value {_delta_class(resource.get('delta'))}">{_e(_fmt_delta(resource.get('delta'), resource.get('delta_pct')))}</div><div class="sub">资源采集状态</div></div>
    <div class="card"><div class="label">本周任务/人员</div><div class="value">{_e(kpis.get('task_types', 0))}</div><div class="sub">出车人数 {_e(kpis.get('unique_drivers', 0))}</div></div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="section-title">指数构成</div><div class="section-sub">使用滚动窗口、中位数和缓冲区降低单条任务归属误差影响</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>指标</th><th>数值</th><th>权重</th><th>贡献</th></tr></thead><tbody>{component_rows}</tbody></table></div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="section-title">任务量级分层</div><div class="section-sub">首页不做单任务精确评级，只看高/中/低量级结构</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>层级</th><th>任务</th><th>本周人次</th><th>占比</th><th>白/夜班</th></tr></thead><tbody>{tier_rows}</tbody></table></div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="section-title">Top 任务人次概览</div><div class="section-sub">用于说明任务量级，不作为首页人员稳定性评级</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>排名</th><th>采集任务</th><th>本周人次</th><th>上周同任务</th><th>环比</th><th>上周排名</th><th>本周白/夜班</th></tr></thead><tbody>{top_rows}</tbody></table></div>
  </section>

  <section class="section" data-section="personnel-stability">
    <div class="section-head"><div><div class="section-title">Top 任务人员稳定性</div><div class="section-sub">同任务本周/上周延续、新进和连续承接风险</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>采集任务</th><th>延续人数</th><th>新进人数</th><th>新进人次占比</th><th>每日换手率</th><th>最大连续承接天数</th><th>风险等级</th></tr></thead><tbody>{stability_rows}</tbody></table></div>
  </section>

  <section class="section" data-section="personnel-matrix">
    <div class="section-head"><div><div class="section-title">每日任务人员矩阵</div><div class="section-sub">判断同一任务是否由稳定人员持续承接</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>任务</th><th>日期</th><th>白班</th><th>夜班</th><th>延续</th><th>新进</th><th>离开</th><th>换手率</th></tr></thead><tbody>{matrix_rows}</tbody></table></div>
  </section>

  <section class="section" data-section="person-attendance-summary">
    <div class="section-head"><div><div class="section-title">个人出勤投入</div><div class="section-sub">有效采集时间是采集投入指标，不等同于出勤时长</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>人员</th><th>出勤天数</th><th>人次</th><th>白/夜班</th><th>参与任务数</th><th>Top任务人次</th><th>主要任务</th><th>有效采集时间</th></tr></thead><tbody>{person_rows}</tbody></table></div>
  </section>

  <section class="section" data-section="resource-metrics">
    <div class="section-head"><div><div class="section-title">资源管理补充指标</div><div class="section-sub">由配置文件控制展示顺序和启用状态</div></div></div>
    {resource_metric_sections}
  </section>

  <section class="section" data-section="dashboard-production-quality">
    <div class="section-head"><div><div class="section-title">产出与质量</div><div class="section-sub">来自 Neolix 采集总览看板 HTML 快照</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>车辆</th><th>城市</th><th>场景</th><th>采集</th><th>入库</th><th>Records</th><th>入库率</th><th>里程</th></tr></thead><tbody>{dashboard_collection_rows}</tbody></table></div>
    <div class="table-wrap"><table><thead><tr><th>车辆</th><th>总 Clips</th><th>不通过率</th><th>不通过数</th><th>主要异常项</th></tr></thead><tbody>{dashboard_quality_rows}</tbody></table></div>
  </section>

  <section class="section" data-section="resource-risk-items">
    <div class="section-head"><div><div class="section-title">风险清单</div><div class="section-sub">配置阈值触发，描述资源和质量风险，不做个人评价</div></div></div>
    <div class="table-wrap"><table><thead><tr><th>类型</th><th>对象</th><th>原因</th><th>等级</th></tr></thead><tbody>{risk_rows}</tbody></table></div>
  </section>

  <section class="section">
    <div class="section-head"><div><div class="section-title">数据说明</div><div class="section-sub">抗噪口径和限制</div></div><a class="detail-link" href="details.html">打开详情页</a></div>
    <div class="note">{_notes_html(focus.get('robust_metric_notes') or [])}完整解析明细见 report.json；任务 drilldown 见 details.html。诊断记录数：{_e(report.get('diagnostics_count', 0))}。</div>
  </section>
</main>
</body>
</html>
"""


def render_embed_html(report: dict[str, Any]) -> str:
    """Render an iframe-friendly resource weekly report with Neolix dashboard styling."""
    focus = report.get("focus_summary") or {}
    period = report.get("period") or {}
    previous_period = focus.get("previous_period") or {}
    kpis = report.get("kpis") or {}
    risks = report.get("risk_items") or []

    person_rows = "".join(_person_row(item) for item in (report.get("person_attendance_summary") or report.get("driver_summary") or [])[:12])
    if not person_rows:
        person_rows = "<tr><td colspan='8' class='empty'>暂无个人投入数据</td></tr>"

    stability_rows = "".join(_stability_row(item) for item in focus.get("top_task_personnel_stability") or [])
    if not stability_rows:
        stability_rows = "<tr><td colspan='7' class='empty'>暂无任务连续性数据</td></tr>"

    matrix_rows = "".join(_matrix_task_rows(item) for item in focus.get("top_task_daily_personnel_matrix") or [])
    if not matrix_rows:
        matrix_rows = "<tr><td colspan='8' class='empty'>暂无每日人员矩阵</td></tr>"

    dashboard_collection_rows = _dashboard_collection_rows(report)
    dashboard_quality_rows = _dashboard_quality_rows(report)
    risk_rows = _risk_item_rows(risks)
    resource_metric_sections = _resource_metrics_html(report)

    summary_cards = [
        ("本周参与人数", _metric_display(report, "weekly_active_people", kpis.get("unique_drivers", 0)), "人员去重", "blue"),
        ("出勤人次", _metric_display(report, "weekly_attendance_count", kpis.get("total_attendance", 0)), "白班/夜班合计", "cyan"),
        ("采集总次数", _metric_display(report, "dashboard_collection_count", _dashboard_kpi_value(report, "采集总次数")), "看板周周期口径", "green"),
        ("入库率", _metric_display(report, "dashboard_storage_rate", _dashboard_kpi_value(report, "入库率")), "采集至 BOS", "red"),
        ("Record 文件", _metric_display(report, "dashboard_records", _dashboard_kpi_value(report, "Record 文件")), "产出文件量", "orange"),
        ("主要风险数", str(len(risks)), "阈值触发项", "purple"),
    ]
    summary_html = "".join(_embed_kpi_card(label, value, sub, tone) for label, value, sub, tone in summary_cards)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>资源管理周报</title>
<link rel="icon" href="data:," />
<style>
*{{box-sizing:border-box}}html{{background:#f4f6fb}}body{{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',Arial,sans-serif;background:#f4f6fb;color:#1f2329;font-size:14px;line-height:1.55}}.resource-embed-shell{{min-height:100vh;padding:16px 20px 28px}}.embed-tabs{{height:42px;display:flex;align-items:flex-end;gap:26px;border-bottom:1px solid #e5e8ef;background:#fff;padding:0 16px;margin:-16px -20px 16px}}.embed-tab{{height:42px;display:inline-flex;align-items:center;color:#4e5969;font-weight:600;white-space:nowrap}}.embed-tab.active{{color:#1677ff;border-bottom:2px solid #1677ff}}.embed-toolbar{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:14px}}.page-title{{font-size:20px;font-weight:700;color:#1d2129;margin:0}}.page-meta{{display:flex;gap:8px;flex-wrap:wrap;color:#86909c;font-size:12px;margin-top:4px}}.toolbar-actions{{display:flex;gap:8px;align-items:center}}.ghost-button{{height:32px;border:1px solid #d9dee8;border-radius:6px;background:#fff;color:#4e5969;padding:0 12px;text-decoration:none;display:inline-flex;align-items:center;font-weight:600}}.filter-strip{{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid #e5e8ef;border-radius:8px;padding:10px 12px;margin-bottom:12px;overflow-x:auto}}.filter-label{{color:#86909c;font-size:12px;white-space:nowrap}}.filter-pill{{min-height:30px;border:1px solid #d9dee8;border-radius:6px;background:#fff;color:#1f2329;padding:5px 10px;white-space:nowrap}}.kpi-grid{{display:grid;grid-template-columns:repeat(6,minmax(128px,1fr));gap:12px;margin-bottom:12px}}.dashboard-card{{background:#fff;border:1px solid #e5e8ef;border-radius:8px;box-shadow:0 1px 2px rgba(31,35,41,.04)}}.kpi-card{{min-height:132px;padding:16px}}.kpi-label{{font-size:12px;color:#86909c;margin-bottom:10px}}.kpi-value{{font-size:28px;line-height:1.08;font-weight:800;color:#1f2329;word-break:break-word}}.kpi-sub{{font-size:12px;color:#86909c;margin-top:8px}}.tone-blue .kpi-value{{color:#1677ff}}.tone-cyan .kpi-value{{color:#13c2c2}}.tone-green .kpi-value{{color:#00a870}}.tone-red .kpi-value{{color:#ff4d4f}}.tone-orange .kpi-value{{color:#fa8c16}}.tone-purple .kpi-value{{color:#722ed1}}.content-grid{{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}}.section{{overflow:hidden}}.section-head{{height:auto;min-height:48px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid #eef1f6;background:#fff}}.section-title{{font-size:15px;font-weight:700;color:#1f2329}}.section-sub{{font-size:12px;color:#86909c;margin-top:2px}}.detail-link{{color:#1677ff;text-decoration:none;font-weight:700}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;min-width:760px}}th{{background:#f7f8fa;color:#4e5969;text-align:center;font-weight:700;padding:10px 12px;border-bottom:1px solid #e5e8ef;white-space:nowrap}}td{{padding:10px 12px;border-bottom:1px solid #eef1f6;text-align:center;vertical-align:top;color:#1f2329}}td.left{{text-align:left;font-weight:600}}caption{{color:#1f2329}}.empty{{padding:24px;color:#a8abb2;text-align:center}}.note{{padding:12px 16px;color:#86909c;font-size:12px;border-top:1px solid #eef1f6;background:#fbfcff}}.risk{{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:700;background:#f2f3f5;color:#4e5969}}.risk-high{{background:#fff1f0;color:#cf1322}}.risk-medium{{background:#fff7e6;color:#d46b08}}.risk-low{{background:#f6ffed;color:#389e0d}}.chips{{display:flex;flex-wrap:wrap;gap:4px;justify-content:center}}.chip{{display:inline-flex;border:1px solid #d9dee8;border-radius:999px;padding:2px 7px;background:#fff;white-space:nowrap}}.chip.temp{{border-color:#faad14;background:#fffbe6;color:#ad6800}}.bar{{height:7px;background:#edf0f5;border-radius:999px;overflow:hidden;min-width:96px;margin-top:6px}}.bar span{{display:block;height:100%;background:#1677ff}}.delta-up{{color:#cf1322;font-weight:800}}.delta-down{{color:#389e0d;font-weight:800}}.delta-flat{{color:#4e5969;font-weight:800}}@media(max-width:1180px){{.kpi-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}@media(max-width:760px){{.resource-embed-shell{{padding:12px}}.embed-tabs{{margin:-12px -12px 12px;padding:0 12px;gap:18px}}.embed-toolbar{{align-items:flex-start;flex-direction:column}}.kpi-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.kpi-value{{font-size:24px}}}}@media(max-width:460px){{.kpi-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<main class="resource-embed-shell" data-embed="resource-weekly-report">
  <nav class="embed-tabs" aria-label="dashboard tabs">
    <span class="embed-tab active">资源周报</span>
    <span class="embed-tab">资源概览</span>
    <span class="embed-tab">质量风险</span>
  </nav>
  <div class="embed-toolbar">
    <div>
      <h1 class="page-title">资源管理周报</h1>
      <div class="page-meta"><span>{_e(report.get('week_id') or '-')}</span><span>{_e(period.get('start_date'))} ~ {_e(period.get('end_date'))}</span><span>生成 {_e(_fmt_generated_at(report.get('generated_at')))}</span></div>
    </div>
    <div class="toolbar-actions"><a class="ghost-button" href="details.html">任务明细</a></div>
  </div>
  <div class="filter-strip">
    <span class="filter-label">数据周期</span><span class="filter-pill">{_e(period.get('start_date'))} 至 {_e(period.get('end_date'))}</span>
    <span class="filter-label">对比周期</span><span class="filter-pill">{_e(previous_period.get('start_date'))} 至 {_e(previous_period.get('end_date'))}</span>
    <span class="filter-label">数据源</span><span class="filter-pill">Feishu 明细 + collection overview</span>
  </div>
  <section class="kpi-grid" data-section="dashboard-style-kpis">{summary_html}</section>
  <div class="content-grid">
    <section class="dashboard-card section" data-section="resource-input">
      <div class="section-head"><div><div class="section-title">资源投入</div><div class="section-sub">有效采集时间用于投入观察，不等同于出勤时长</div></div></div>
      <div class="table-wrap"><table><thead><tr><th>人员</th><th>出勤天数</th><th>人次</th><th>白/夜班</th><th>参与任务数</th><th>Top任务人次</th><th>主要任务</th><th>有效采集时间</th></tr></thead><tbody>{person_rows}</tbody></table></div>
    </section>
    <section class="dashboard-card section" data-section="task-continuity">
      <div class="section-head"><div><div class="section-title">任务连续性</div><div class="section-sub">按 Top 任务观察延续、新进和每日换手情况</div></div><a class="detail-link" href="details.html">查看 drilldown</a></div>
      <div class="table-wrap"><table><thead><tr><th>采集任务</th><th>延续人数</th><th>新进人数</th><th>新进人次占比</th><th>每日换手率</th><th>最大连续承接天数</th><th>风险等级</th></tr></thead><tbody>{stability_rows}</tbody></table></div>
      <div class="table-wrap"><table><thead><tr><th>任务</th><th>日期</th><th>白班</th><th>夜班</th><th>延续</th><th>新进</th><th>离开</th><th>换手率</th></tr></thead><tbody>{matrix_rows}</tbody></table></div>
    </section>
    <section class="dashboard-card section" data-section="resource-metrics">
      <div class="section-head"><div><div class="section-title">指标配置输出</div><div class="section-sub">展示内容由 resource_weekly_metrics.yaml 控制</div></div></div>
      {resource_metric_sections}
    </section>
    <section class="dashboard-card section" data-section="dashboard-production-quality">
      <div class="section-head"><div><div class="section-title">产出与质量</div><div class="section-sub">车辆、入库、Records、里程和质检异常来自看板快照</div></div></div>
      <div class="table-wrap"><table><thead><tr><th>车辆</th><th>城市</th><th>场景</th><th>采集</th><th>入库</th><th>Records</th><th>入库率</th><th>里程</th></tr></thead><tbody>{dashboard_collection_rows}</tbody></table></div>
      <div class="table-wrap"><table><thead><tr><th>车辆</th><th>总 Clips</th><th>不通过率</th><th>不通过数</th><th>主要异常项</th></tr></thead><tbody>{dashboard_quality_rows}</tbody></table></div>
    </section>
    <section class="dashboard-card section" data-section="resource-risk-items">
      <div class="section-head"><div><div class="section-title">风险清单</div><div class="section-sub">按配置阈值聚合任务连续性和车辆质量风险</div></div></div>
      <div class="table-wrap"><table><thead><tr><th>类型</th><th>对象</th><th>原因</th><th>等级</th></tr></thead><tbody>{risk_rows}</tbody></table></div>
    </section>
  </div>
</main>
</body>
</html>
"""


def render_iframe_preview_html(embed_src: str = "resource_weekly_report_embed.html") -> str:
    """Render a local dashboard-like iframe container for visual verification."""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>资源周报 iframe 预览</title>
<link rel="icon" href="data:," />
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',Arial,sans-serif;background:#f4f6fb;color:#1f2329}}.preview-app{{min-height:100vh;display:grid;grid-template-columns:236px minmax(0,1fr);grid-template-rows:56px minmax(0,1fr)}}.preview-topbar{{grid-column:1 / 3;height:56px;background:#fff;border-bottom:1px solid #eef1f6;display:flex;align-items:center;justify-content:space-between;padding:0 20px}}.brand{{display:flex;align-items:center;gap:10px;font-weight:800;font-size:16px}}.brand-mark{{width:32px;height:32px;border-radius:5px;background:linear-gradient(135deg,#0a5cff 0 48%,#fff 48% 58%,#0a5cff 58%);display:inline-block}}.topnav{{display:flex;gap:34px;color:#4e5969;font-size:14px;margin-left:28px;flex:1}}.topnav span.active{{color:#1677ff;font-weight:700}}.user{{color:#86909c;font-size:13px}}.preview-sidebar{{background:#fff;border-right:1px solid #eef1f6;padding:12px 10px}}.side-item{{height:40px;display:flex;align-items:center;border-radius:6px;padding:0 16px;color:#4e5969;margin-bottom:4px}}.side-item.active{{background:#f2f3f5;color:#1f2329;font-weight:700}}.preview-main{{min-width:0;padding:0 20px 20px;overflow:hidden}}.preview-tabs{{height:48px;background:#fff;border-bottom:1px solid #eef1f6;display:flex;align-items:flex-end;gap:26px;padding:0 18px;margin:0 -20px 16px}}.preview-tab{{height:48px;display:flex;align-items:center;color:#4e5969;font-weight:600}}.preview-tab.active{{color:#1677ff;border-bottom:2px solid #1677ff}}.frame-wrap{{height:calc(100vh - 120px);min-height:620px;background:#fff;border:1px solid #e5e8ef;border-radius:8px;overflow:hidden}}.resource-weekly-frame{{width:100%;height:100%;border:0;display:block;background:#f4f6fb}}@media(max-width:900px){{.preview-app{{grid-template-columns:1fr}}.preview-topbar{{grid-column:1}}.preview-sidebar{{display:none}}.topnav{{display:none}}.preview-main{{padding:0 12px 12px}}.preview-tabs{{margin:0 -12px 12px}}.frame-wrap{{height:calc(100vh - 116px);min-height:520px}}}}
</style>
</head>
<body>
<div class="preview-app" data-preview="resource-weekly-report-iframe">
  <header class="preview-topbar">
    <div class="brand"><span class="brand-mark"></span><span>Neolix DriveStack</span></div>
    <nav class="topnav"><span class="active">AD大盘</span><span>数据闭环</span><span>模型训练</span><span>构建发布</span><span>仿真路测</span><span>资源管理</span></nav>
    <div class="user">本地预览</div>
  </header>
  <aside class="preview-sidebar">
    <div class="side-item active">数据大盘</div>
    <div class="side-item">资源大盘</div>
    <div class="side-item">发版大盘</div>
    <div class="side-item">测试大盘</div>
    <div class="side-item">运营大盘</div>
    <div class="side-item">大盘配置</div>
  </aside>
  <main class="preview-main">
    <nav class="preview-tabs"><span class="preview-tab">采集总览</span><span class="preview-tab">本周看板</span><span class="preview-tab active">资源周报</span></nav>
    <div class="frame-wrap"><iframe class="resource-weekly-frame" title="资源管理周报" src="{_e(embed_src)}"></iframe></div>
  </main>
</div>
</body>
</html>
"""


def render_detail_html(report: dict[str, Any]) -> str:
    focus = report.get("focus_summary") or {}
    details = focus.get("scheduling_control_details") or []
    period = report.get("period") or {}
    rows = "".join(_detail_task_section(item) for item in details)
    if not rows:
        rows = "<section class='section'><div class='empty'>暂无任务详情</div></section>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>SD周报任务详情</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',sans-serif;background:#f5f7fa;color:#20242c;line-height:1.55}}.hero{{background:#102033;color:#fff;padding:24px 32px}}.hero a{{color:#c8e6ff;font-weight:800;text-decoration:none}}.wrap{{max-width:1240px;margin:0 auto;padding:22px 26px 36px}}h1{{margin:0 0 8px;font-size:24px}}.meta{{color:#d8e0ea;font-size:13px}}.section{{background:#fff;border:1px solid #dde5ee;border-radius:8px;margin-top:14px;overflow:hidden}}.section-head{{padding:14px 16px;border-bottom:1px solid #e8edf3;background:#fbfcfd}}.title{{font-weight:850}}.sub{{font-size:12px;color:#667085;margin-top:4px}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;min-width:860px}}th{{background:#f2f5f8;color:#344054;text-align:center;font-weight:750;padding:10px 12px;border-bottom:1px solid #d7e0ea}}td{{padding:10px 12px;border-bottom:1px solid #edf1f5;text-align:center;vertical-align:top}}td.left{{text-align:left}}.chips{{display:flex;flex-wrap:wrap;gap:4px}}.chip{{display:inline-flex;border:1px solid #d0d5dd;border-radius:999px;padding:2px 7px;background:#fff;white-space:nowrap}}.chip.temp{{border-color:#f79009;background:#fffaeb;color:#93370d}}.empty{{padding:20px;color:#98a2b3}}@media(max-width:760px){{.hero,.wrap{{padding-left:16px;padding-right:16px}}}}
</style>
</head>
<body>
<header class="hero"><h1>任务排班详情｜{_e(report.get('week_id') or '')}</h1><div class="meta">{_e(period.get('start_date'))} 至 {_e(period.get('end_date'))} · <a href="report.html">返回首页</a></div></header>
<main class="wrap">{rows}</main>
</body>
</html>
"""


def _embed_kpi_card(label: str, value: Any, sub: str, tone: str) -> str:
    display_value = value if value is not None and value != "" else "-"
    return (
        f"<div class='dashboard-card kpi-card tone-{_e(tone)}'>"
        f"<div class='kpi-label'>{_e(label)}</div>"
        f"<div class='kpi-value'>{_e(display_value)}</div>"
        f"<div class='kpi-sub'>{_e(sub)}</div>"
        "</div>"
    )


def _metric_display(report: dict[str, Any], metric_id: str, fallback: Any = "-") -> str:
    metric = _metric_by_id(report, metric_id)
    if metric:
        display_value = metric.get("display_value")
        if display_value is not None and display_value != "":
            return str(display_value)
        if metric.get("value") is not None and metric.get("value") != "":
            return _fmt_number(metric.get("value"))
    if fallback is not None and fallback != "":
        return str(fallback)
    return "-"


def _metric_by_id(report: dict[str, Any], metric_id: str) -> dict[str, Any] | None:
    for metrics in (report.get("resource_metrics") or {}).values():
        for metric in metrics or []:
            if metric.get("id") == metric_id:
                return metric
    return None


def _dashboard_kpi_value(report: dict[str, Any], *labels: str) -> str:
    kpis = (report.get("dashboard_overview") or {}).get("kpis") or {}
    for label in labels:
        item = kpis.get(label)
        if isinstance(item, dict) and item.get("value") is not None and item.get("value") != "":
            return str(item.get("value"))
    return "-"


def _resource_metrics_markdown(report: dict[str, Any]) -> list[str]:
    groups = report.get("resource_metrics") or {}
    if not groups:
        return ["- 看板数据未接入或资源指标未启用。"]

    lines: list[str] = []
    for group_metrics in groups.values():
        if not group_metrics:
            continue
        group_name = group_metrics[0].get("group_name") or group_metrics[0].get("group") or "指标"
        lines.extend([f"### {group_name}", "", "| 指标 | 数值 |", "|---|---:|"])
        for metric in group_metrics:
            lines.append(f"| {metric.get('name') or '-'} | {metric.get('display_value') or _fmt_number(metric.get('value'))} |")
        lines.append("")

    risks = report.get("risk_items") or []
    if risks:
        lines.extend(["### 重点风险", "", "| 类型 | 对象 | 原因 | 等级 |", "|---|---|---|---|"])
        for item in risks[:10]:
            lines.append(
                "| {type} | {name} | {reason} | {severity} |".format(
                    type=item.get("type") or "-",
                    name=item.get("name") or "-",
                    reason=item.get("reason") or "-",
                    severity=item.get("severity") or "-",
                )
            )
    return lines


def _resource_metrics_html(report: dict[str, Any]) -> str:
    groups = report.get("resource_metrics") or {}
    if not groups:
        return "<div class='empty'>看板数据未接入或资源指标未启用</div>"

    sections = []
    for group_metrics in groups.values():
        if not group_metrics:
            continue
        group_name = group_metrics[0].get("group_name") or group_metrics[0].get("group") or "指标"
        rows = "".join(
            "<tr>"
            f"<td class='left'>{_e(metric.get('name') or '-')}</td>"
            f"<td><strong>{_e(metric.get('display_value') or _fmt_number(metric.get('value')))}</strong></td>"
            f"<td>{_e(_risk_label(metric.get('risk_level')))}</td>"
            "</tr>"
            for metric in group_metrics
        )
        sections.append(
            f"<div class='table-wrap'><table><caption style='text-align:left;padding:10px 12px;font-weight:800'>{_e(group_name)}</caption>"
            f"<thead><tr><th>指标</th><th>数值</th><th>状态</th></tr></thead><tbody>{rows}</tbody></table></div>"
        )
    return "".join(sections)


def _dashboard_collection_rows(report: dict[str, Any]) -> str:
    rows = []
    for item in ((report.get("dashboard_overview") or {}).get("vehicle_collection_summary") or [])[:20]:
        rows.append(
            "<tr>"
            f"<td>{_e(item.get('车辆') or '-')}</td>"
            f"<td>{_e(item.get('城市') or '-')}</td>"
            f"<td class='left'>{_e(item.get('场景') or '-')}</td>"
            f"<td>{_e(item.get('采集 ▼') or item.get('采集') or '-')}</td>"
            f"<td>{_e(item.get('入库') or '-')}</td>"
            f"<td>{_e(item.get('Records') or '-')}</td>"
            f"<td>{_e(item.get('入库率') or '-')}</td>"
            f"<td>{_e(item.get('里程') or '-')}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='8' class='empty'>暂无车辆采集明细</td></tr>"


def _dashboard_quality_rows(report: dict[str, Any]) -> str:
    rows = []
    for item in ((report.get("dashboard_overview") or {}).get("vehicle_quality_summary") or [])[:20]:
        anomaly = _first_non_empty(item, exclude={"车辆", "总 Clips", "不通过率", "不通过数"})
        rows.append(
            "<tr>"
            f"<td>{_e(item.get('车辆') or '-')}</td>"
            f"<td>{_e(item.get('总 Clips') or '-')}</td>"
            f"<td>{_e(item.get('不通过率') or '-')}</td>"
            f"<td>{_e(item.get('不通过数') or '-')}</td>"
            f"<td class='left'>{_e(anomaly or '-')}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='5' class='empty'>暂无车辆质检明细</td></tr>"


def _risk_item_rows(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<tr><td colspan='4' class='empty'>暂无配置阈值触发的风险项</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{_e(item.get('type') or '-')}</td>"
        f"<td class='left'>{_e(item.get('name') or '-')}</td>"
        f"<td class='left'>{_e(item.get('reason') or '-')}</td>"
        f"<td>{_e(item.get('severity') or '-')}</td>"
        "</tr>"
        for item in items[:30]
    )


def _first_non_empty(item: dict[str, Any], *, exclude: set[str]) -> str:
    for key, value in item.items():
        if key in exclude:
            continue
        if str(value or "").strip():
            return f"{key}: {value}"
    return ""


def _risk_label(value: Any) -> str:
    if value == "high":
        return "高"
    if value == "medium":
        return "中"
    if value == "low":
        return "低"
    return "-"


def _top_task_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_e(item.get('rank', '-'))}</td>"
        f"<td class='left'>{_e(item.get('task') or '-')}</td>"
        f"<td><strong>{_e(item.get('current_total', 0))}</strong></td>"
        f"<td>{_e(item.get('previous_total', 0))}</td>"
        f"<td class='{_delta_class(item.get('delta'))}'>{_e(_fmt_delta(item.get('delta'), item.get('delta_pct')))}</td>"
        f"<td>{_e(item.get('previous_rank') or '未进榜/无数据')}</td>"
        f"<td>{_e(item.get('white', 0))}/{_e(item.get('night', 0))}</td>"
        "</tr>"
    )


def _stability_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td class='left'>{_e(item.get('task') or '-')}</td>"
        f"<td>{_e(item.get('continued_driver_count', 0))}</td>"
        f"<td>{_e(item.get('new_driver_count', 0))}</td>"
        f"<td>{_e(_fmt_pct(item.get('new_attendance_share')))}</td>"
        f"<td>{_e(_fmt_pct(item.get('daily_turnover_rate')))}</td>"
        f"<td>{_e(item.get('max_consecutive_days', 0))}</td>"
        f"<td><span class='{_risk_class(item.get('risk_level'))}'>{_e(item.get('risk_level') or '-')}</span></td>"
        "</tr>"
    )


def _matrix_task_rows(item: dict[str, Any]) -> str:
    rows = []
    task = item.get("task") or "-"
    for day in item.get("dates") or []:
        rows.append(
            "<tr>"
            f"<td class='left'>{_e(task)}</td>"
            f"<td>{_e(day.get('date') or '-')} {_e(day.get('weekday') or '')}</td>"
            f"<td>{_chips(day.get('white_drivers') or [], temporary=False)}</td>"
            f"<td>{_chips(day.get('night_drivers') or [], temporary=False)}</td>"
            f"<td>{_chips(day.get('continued_from_previous_day') or [], temporary=False)}</td>"
            f"<td>{_chips(day.get('new_from_previous_day') or [], temporary=True)}</td>"
            f"<td>{_chips(day.get('left_from_previous_day') or [], temporary=True)}</td>"
            f"<td>{_e(_fmt_pct(day.get('turnover_rate')))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _person_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td class='left'>{_e(item.get('driver') or '-')}</td>"
        f"<td>{_e(item.get('attendance_days', 0))}</td>"
        f"<td>{_e(item.get('total_attendance', item.get('total', 0)))}</td>"
        f"<td>{_e(item.get('white', 0))}/{_e(item.get('night', 0))}</td>"
        f"<td>{_e(item.get('task_count', len(item.get('tasks') or [])))}</td>"
        f"<td>{_e(item.get('top_task_attendance', 0))}</td>"
        f"<td class='left'>{_e(item.get('primary_task') or '-')}</td>"
        f"<td>{_e(_fmt_number(item.get('effective_collection_time', 0)))}</td>"
        "</tr>"
    )


def _component_row(item: dict[str, Any]) -> str:
    value = float(item.get("value") or 0)
    weight = float(item.get("weight") or 0)
    return (
        "<tr>"
        f"<td class='left'>{_e(item.get('label') or '-')}</td>"
        f"<td>{_e(_fmt_pct(value))}<div class='bar'><span style='width:{_e(value * 100)}%'></span></div></td>"
        f"<td>{_e(_fmt_pct(weight))}</td>"
        f"<td>{_e(round(value * weight * 100, 1))}</td>"
        "</tr>"
    )


def _tier_row(label: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"<tr><td>{_e(label)}</td><td class='empty' colspan='4'>暂无</td></tr>"
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{_e(label)}</td>"
            f"<td class='left'>{_e(item.get('task') or '-')}</td>"
            f"<td>{_e(item.get('total', 0))}</td>"
            f"<td>{_e(_fmt_pct(item.get('share')))}</td>"
            f"<td>{_e(item.get('white', 0))}/{_e(item.get('night', 0))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _detail_task_section(item: dict[str, Any]) -> str:
    candidate_rows = "".join(_candidate_row(row) for row in item.get("stable_candidates") or [])
    if not candidate_rows:
        candidate_rows = "<tr><td colspan='4' class='empty'>暂无历史稳定参与者候选</td></tr>"
    daily_rows = "".join(_daily_detail_row(row) for row in item.get("daily_details") or [])
    if not daily_rows:
        daily_rows = "<tr><td colspan='6' class='empty'>暂无日期明细</td></tr>"
    return f"""
<section class="section">
  <div class="section-head"><div class="title">{_e(item.get('task') or '-')}</div><div class="sub">本周 {_e(item.get('current_total', 0))} 人次 · 候选 {_e(item.get('stable_candidate_count', 0))} 人 · 稳定覆盖 {_e(_fmt_pct(item.get('stable_candidate_coverage')))} · 临时占比 {_e(_fmt_pct(item.get('temporary_participant_share')))}</div></div>
  <div class="table-wrap"><table><thead><tr><th>历史稳定参与者候选</th><th>历史人次</th><th>历史活跃天</th><th>本周人次</th></tr></thead><tbody>{candidate_rows}</tbody></table></div>
  <div class="table-wrap"><table><thead><tr><th>日期</th><th>稳定参与者</th><th>临时参与者</th><th>白班稳定/临时</th><th>夜班稳定/临时</th><th>稳定覆盖</th></tr></thead><tbody>{daily_rows}</tbody></table></div>
</section>
"""


def _candidate_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td class='left'>{_e(item.get('driver') or '-')}</td>"
        f"<td>{_e(item.get('history_attendance_count', 0))}</td>"
        f"<td>{_e(item.get('history_active_days', 0))}</td>"
        f"<td>{_e(item.get('current_attendance_count', 0))}</td>"
        "</tr>"
    )


def _daily_detail_row(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{_e(item.get('date') or '-')} {_e(item.get('weekday') or '')}</td>"
        f"<td>{_chips(item.get('stable_drivers') or [], temporary=False)}</td>"
        f"<td>{_chips(item.get('temporary_drivers') or [], temporary=True)}</td>"
        f"<td>{_chips(item.get('white_stable_drivers') or [], temporary=False)} / {_chips(item.get('white_temporary_drivers') or [], temporary=True)}</td>"
        f"<td>{_chips(item.get('night_stable_drivers') or [], temporary=False)} / {_chips(item.get('night_temporary_drivers') or [], temporary=True)}</td>"
        f"<td>{_e(_fmt_pct(item.get('stable_coverage')))}</td>"
        "</tr>"
    )


def _chips(values: list[str], *, temporary: bool) -> str:
    if not values:
        return "<span class='chip'>-</span>"
    class_name = "chip temp" if temporary else "chip"
    return "<div class='chips'>" + "".join(f"<span class='{class_name}'>{_e(value)}</span>" for value in values) + "</div>"


def _history_select(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<select id='week-select' disabled><option>暂无历史周报</option></select>"
    options = []
    for item in items:
        selected = " selected" if item.get("current") else ""
        options.append(f"<option value='{_e(item.get('href'))}'{selected}>{_e(item.get('week_id'))}</option>")
    return "<select id='week-select' onchange=\"if(this.value) window.location.href=this.value\">" + "".join(options) + "</select>"


def _notes_html(notes: list[str]) -> str:
    if not notes:
        return ""
    return "".join(f"<p>{_e(note)}</p>" for note in notes)


def _fmt_generated_at(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value).replace("T", " ")
    return text[:16] if len(text) >= 16 else text


def _fmt_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"


def _fmt_delta(delta: Any, delta_pct: Any) -> str:
    try:
        delta_num = float(delta or 0)
    except (TypeError, ValueError):
        delta_num = 0.0
    sign = "+" if delta_num > 0 else ""
    delta_text = f"{sign}{delta_num:.2f}" if not delta_num.is_integer() else f"{sign}{int(delta_num)}"
    if delta_pct is None:
        return f"{delta_text}（上周无基数）"
    try:
        pct_num = float(delta_pct)
    except (TypeError, ValueError):
        return delta_text
    pct_sign = "+" if pct_num > 0 else ""
    return f"{delta_text}（{pct_sign}{pct_num:.2f}%）"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _delta_class(delta: Any) -> str:
    try:
        value = float(delta or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return "delta-up"
    if value < 0:
        return "delta-down"
    return "delta-flat"


def _status_class(status: Any) -> str:
    if status == "需关注":
        return "status status-risk"
    if status == "观察":
        return "status status-watch"
    return "status"


def _risk_class(risk: Any) -> str:
    if risk == "高风险":
        return "risk risk-high"
    if risk == "中风险":
        return "risk risk-medium"
    if risk == "低风险":
        return "risk risk-low"
    return "risk"


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))
