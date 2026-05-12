"""HTML renderers for the collection data dashboard."""

from __future__ import annotations

from html import escape
from typing import Any


def render_collection_dashboard_embed(dashboard: dict[str, Any]) -> str:
    period_views = dashboard.get("period_views") or {}
    day_view = period_views.get("day") or {}
    week_view = period_views.get("week") or day_view
    metrics = day_view.get("metrics") or {}
    vehicle = day_view.get("vehicle_status") or {}
    summaries = dashboard.get("vehicle_daily_summary") or []
    configured_groups = dashboard.get("configured_metric_groups") or day_view.get("configured_metric_groups") or []
    dashboard_overview = dashboard.get("dashboard_overview") or {}
    range_start, range_end, min_date, max_date = _date_range_defaults(dashboard, day_view)

    cards = [
        ("active_people", "参与人数", _metric_display(metrics, "active_people"), "当前日", "blue"),
        ("attendance_count", "出勤人次", _metric_display(metrics, "attendance_count"), "有效司机记录", "cyan"),
        ("sd_per_day", "SD 个数/天", _metric_display(metrics, "sd_per_day"), "当前粒度", "green"),
        ("stable_participant_coverage", "稳定覆盖率", _metric_display(metrics, "stable_participant_coverage"), "重点任务池", "orange"),
        ("vehicle_active_count", "活跃车辆", vehicle.get("active_count", 0), "有效司机优先", "purple"),
        ("vehicle_abnormal_count", "异常车辆", vehicle.get("abnormal_count", 0), "未安排司机状态", "red"),
    ]
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>采集数据看板</title>
<link rel="icon" href="data:," />
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',Arial,sans-serif;background:#f4f6fb;color:#1f2329;font-size:14px;line-height:1.55}}button,input{{font:inherit}}.dashboard-shell{{min-height:100vh;padding:16px 20px 28px}}.tabs{{height:42px;display:flex;gap:26px;align-items:flex-end;background:#fff;border-bottom:1px solid #e5e8ef;margin:-16px -20px 16px;padding:0 16px;overflow-x:auto}}.tab{{height:42px;display:inline-flex;align-items:center;color:#4e5969;font-weight:600;white-space:nowrap}}.tab.active{{color:#1677ff;border-bottom:2px solid #1677ff}}.toolbar{{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px}}h1{{font-size:20px;line-height:1.2;margin:0 0 4px;font-weight:800}}.meta{{display:flex;gap:8px;flex-wrap:wrap;color:#86909c;font-size:12px}}.filter-strip{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:#fff;border:1px solid #e5e8ef;border-radius:8px;padding:10px 12px;margin-bottom:12px}}.filter-label{{color:#86909c;font-size:12px;white-space:nowrap}}.filter-pill{{border:1px solid #d9dee8;border-radius:6px;background:#fff;min-height:30px;padding:5px 10px;white-space:nowrap}}.date-range{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}.date-input{{height:32px;min-width:142px;border:1px solid #d9dee8;border-radius:6px;background:#fff;color:#1f2329;padding:0 10px;font-size:13px}}.date-input:focus{{outline:0;border-color:#1677ff;box-shadow:0 0 0 2px rgba(22,119,255,.12)}}.date-separator{{color:#86909c;font-size:12px}}.primary-button{{height:32px;border:1px solid #1677ff;border-radius:6px;background:#1677ff;color:#fff;padding:0 14px;font-weight:700;cursor:pointer}}.primary-button:hover{{background:#0958d9;border-color:#0958d9}}.range-error{{color:#86909c;font-size:12px;min-height:18px}}.kpi-grid{{display:grid;grid-template-columns:repeat(6,minmax(128px,1fr));gap:12px;margin-bottom:12px}}.card{{background:#fff;border:1px solid #e5e8ef;border-radius:8px;box-shadow:0 1px 2px rgba(31,35,41,.04)}}.kpi{{min-height:132px;padding:16px}}.kpi-label{{font-size:12px;color:#86909c;margin-bottom:10px}}.kpi-value{{font-size:28px;line-height:1.08;font-weight:850;word-break:break-word}}.kpi-sub{{font-size:12px;color:#86909c;margin-top:8px}}.tone-blue .kpi-value{{color:#1677ff}}.tone-cyan .kpi-value{{color:#13c2c2}}.tone-green .kpi-value{{color:#00a870}}.tone-orange .kpi-value{{color:#fa8c16}}.tone-purple .kpi-value{{color:#722ed1}}.tone-red .kpi-value{{color:#ff4d4f}}.section{{margin-bottom:12px;overflow:hidden}}.section-head{{min-height:48px;display:flex;justify-content:space-between;gap:12px;align-items:center;padding:12px 16px;border-bottom:1px solid #eef1f6;background:#fff}}.section-title{{font-size:15px;font-weight:800}}.section-sub{{font-size:12px;color:#86909c;margin-top:2px}}.grain-grid{{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:10px;padding:12px}}.grain-card{{border:1px solid #eef1f6;border-radius:8px;padding:12px;background:#fbfcff}}.grain-card.active{{border-color:#1677ff;background:#f0f7ff}}.grain-title{{font-weight:800;margin-bottom:8px}}.grain-metrics{{display:grid;grid-template-columns:1fr 1fr;gap:8px;color:#4e5969;font-size:12px}}.grain-metrics strong{{display:block;color:#1f2329;font-size:18px}}.metric-grid{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:10px;padding:12px}}.metric-box{{border:1px solid #eef1f6;border-radius:8px;background:#fbfcff;padding:10px 12px;min-height:76px}}.metric-group-title{{font-weight:800;color:#1f2329;margin-bottom:2px}}.metric-name{{font-size:12px;color:#86909c}}.metric-value{{font-size:20px;font-weight:850;margin-top:4px}}.risk-high{{color:#cf1322}}.risk-medium{{color:#d46b08}}.risk-low{{color:#00a870}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;min-width:860px}}th{{background:#f7f8fa;color:#4e5969;text-align:center;font-weight:700;padding:10px 12px;border-bottom:1px solid #e5e8ef;white-space:nowrap}}td{{padding:10px 12px;border-bottom:1px solid #eef1f6;text-align:center;vertical-align:top}}td.left{{text-align:left;font-weight:600}}.status{{display:inline-flex;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:700;white-space:nowrap}}.active{{background:#e8fffb;color:#08979c}}.idle{{background:#f2f3f5;color:#4e5969}}.abnormal{{background:#fff1f0;color:#cf1322}}.unknown{{background:#fff7e6;color:#d46b08}}.bars{{padding:14px 16px}}.bar-row{{display:grid;grid-template-columns:104px minmax(0,1fr) 60px;gap:10px;align-items:center;margin:8px 0}}.bar-row button{{border:0;background:transparent;color:#1f2329;text-align:left;cursor:pointer;padding:0}}.bar-row button:hover{{color:#1677ff}}.bar-track{{height:12px;background:#edf0f5;border-radius:999px;overflow:hidden;display:flex}}.bar-active{{background:#13c2c2}}.bar-idle{{background:#c9cdd4}}.bar-abnormal{{background:#ff4d4f}}.bar-unknown{{background:#faad14}}.detail-chips{{display:flex;gap:5px;flex-wrap:wrap;justify-content:center}}.chip{{display:inline-flex;border-radius:999px;border:1px solid #d9dee8;background:#fff;padding:2px 7px;font-size:12px;white-space:nowrap}}.link-button{{border:1px solid #d9dee8;background:#fff;border-radius:6px;padding:4px 9px;color:#1677ff;cursor:pointer;white-space:nowrap}}.link-button:hover{{border-color:#1677ff;background:#f0f7ff}}.drawer-backdrop{{position:fixed;inset:0;background:rgba(31,35,41,.28);opacity:0;pointer-events:none;transition:.18s opacity;z-index:20}}.drawer-backdrop.open{{opacity:1;pointer-events:auto}}.drawer{{position:fixed;right:0;top:0;width:min(920px,92vw);height:100vh;background:#fff;box-shadow:-8px 0 24px rgba(31,35,41,.18);transform:translateX(100%);transition:.22s transform;z-index:21;display:flex;flex-direction:column}}.drawer.open{{transform:translateX(0)}}.drawer-head{{padding:16px 18px;border-bottom:1px solid #eef1f6;display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.drawer-title{{font-size:18px;font-weight:850}}.drawer-sub{{font-size:12px;color:#86909c;margin-top:3px}}.drawer-close{{width:32px;height:32px;border:1px solid #d9dee8;background:#fff;border-radius:6px;cursor:pointer;font-size:18px;line-height:1}}.drawer-body{{padding:14px 18px 20px;overflow:auto}}.summary-grid{{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));gap:10px;margin-bottom:12px}}.summary-item{{border:1px solid #eef1f6;border-radius:8px;background:#fbfcff;padding:10px}}.summary-item strong{{display:block;font-size:22px}}.status-filter{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}}.status-filter button{{border:1px solid #d9dee8;background:#fff;border-radius:6px;height:30px;padding:0 10px;cursor:pointer}}.status-filter button.active{{background:#1677ff;color:#fff;border-color:#1677ff}}.loading-note{{font-size:12px;color:#86909c}}@media(max-width:1180px){{.kpi-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}.grain-grid,.metric-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:680px){{.dashboard-shell{{padding:12px}}.tabs{{margin:-12px -12px 12px;padding:0 12px;gap:18px}}.toolbar{{align-items:flex-start;flex-direction:column}}.filter-strip{{align-items:flex-start}}.date-range{{width:100%}}.date-input{{flex:1 1 130px;min-width:0}}.kpi-grid,.grain-grid,.metric-grid,.summary-grid{{grid-template-columns:1fr}}.kpi-value{{font-size:24px}}.bar-row{{grid-template-columns:92px minmax(0,1fr) 42px}}.drawer{{width:100vw}}}}
</style>
</head>
<body>
<main class="dashboard-shell" data-dashboard="collection-data-dashboard" data-source="collection_dashboard.json">
  <nav class="tabs"><span class="tab active">采集总览</span><span class="tab">任务看板</span><span class="tab">人员稳定性</span><span class="tab">车辆状态</span><span class="tab">数据诊断</span></nav>
  <div class="toolbar">
    <div><h1>采集数据看板</h1><div class="meta"><span>锚点日期 <span data-bind="anchor-date">{_e(dashboard.get('anchor_date'))}</span></span><span>生成 <span data-bind="generated-at">{_e(_fmt_generated_at(dashboard.get('generated_at')))}</span></span><span>记录 <span data-bind="record-count">{_e(dashboard.get('record_count', 0))}</span></span><span class="loading-note" data-bind="load-state"></span></div></div>
  </div>
  <div class="filter-strip">
    <span class="filter-label">日期范围</span>
    <div class="date-range" data-control="date-range">
      <input class="date-input" type="date" data-control="start-date" value="{_e(range_start)}" min="{_e(min_date)}" max="{_e(max_date)}" aria-label="开始日期" />
      <span class="date-separator">至</span>
      <input class="date-input" type="date" data-control="end-date" value="{_e(range_end)}" min="{_e(min_date)}" max="{_e(max_date)}" aria-label="结束日期" />
      <button class="primary-button" type="button" data-action="apply-date-range">应用</button>
      <span class="range-error" data-bind="range-error"></span>
    </div>
    <span class="filter-label">车辆规则</span><span class="filter-pill">有效司机优先</span><span class="filter-label">忽略列</span><span class="filter-pill">出车异常记录、数采问题记录</span>
  </div>
  <section class="kpi-grid" id="kpi-grid">{''.join(_kpi_card(*card) for card in cards)}</section>
  <section class="card section" data-section="period-tabs"><div class="section-head"><div><div class="section-title">日期范围汇总</div><div class="section-sub">手动选择起止日期后，按所选范围聚合人员、任务和车辆状态</div></div></div><div class="grain-grid" id="grain-grid">{_range_summary_cards(day_view, range_start, range_end)}</div></section>
  <section class="card section" data-section="metric-registry"><div class="section-head"><div><div class="section-title">可配置指标</div><div class="section-sub">指标启用、顺序、展示格式和阈值来自 collection_dashboard_metrics.yaml</div></div></div><div id="configured-metrics">{_configured_metric_groups(configured_groups)}</div></section>
  <section class="card section" data-section="production-quality"><div class="section-head"><div><div class="section-title">产出与质量快照</div><div class="section-sub">来自 overview_live.html 的采集、入库、Records、里程和质检数据</div></div></div><div class="table-wrap"><table><thead><tr><th>指标</th><th>数值</th><th>说明</th></tr></thead><tbody id="dashboard-kpi-body">{_dashboard_kpi_rows(dashboard_overview)}</tbody></table></div></section>
  <section class="card section" data-section="vehicle-status"><div class="section-head"><div><div class="section-title">每日车辆状态</div><div class="section-sub">点击日期可打开当天车辆明细；状态按 active &gt; abnormal &gt; idle &gt; unknown 去重，备注列不参与判定</div></div></div><div id="vehicle-bars">{_vehicle_bars(summaries[:14])}</div><div class="table-wrap"><table><thead><tr><th>日期</th><th>车辆数</th><th>活跃</th><th>空闲</th><th>异常</th><th>未知</th><th>状态明细</th><th>操作</th></tr></thead><tbody id="vehicle-summary-body">{_vehicle_summary_rows(summaries[:30])}</tbody></table></div></section>
  <section class="card section" data-section="task-top5"><div class="section-head"><div><div class="section-title">Top5 任务</div><div class="section-sub">随日期范围更新，展示所选范围下任务人次和相邻前序周期对比</div></div></div><div class="table-wrap"><table><thead><tr><th>排名</th><th>任务</th><th>当前人次</th><th>对比人次</th><th>变化</th><th>白/夜班</th></tr></thead><tbody id="top-task-body">{_top_task_rows(week_view.get('top5_tasks') or [])}</tbody></table></div></section>
  <section class="card section" data-section="vehicle-detail"><div class="section-head"><div><div class="section-title">车辆状态明细</div><div class="section-sub">异常仅来自未安排有效司机时的车辆状态文本</div></div></div><div class="table-wrap"><table><thead><tr><th>日期</th><th>车号</th><th>状态</th><th>原因</th><th>司机</th><th>任务</th><th>Source</th></tr></thead><tbody id="vehicle-detail-body">{_vehicle_detail_rows((dashboard.get('vehicle_daily_status') or [])[:80])}</tbody></table></div></section>
</main>
<div class="drawer-backdrop" data-action="close-vehicle-drawer"></div>
<aside class="drawer" id="vehicle-drawer" aria-hidden="true" aria-label="每日车辆状态详情">
  <div class="drawer-head"><div><div class="drawer-title" id="drawer-title">车辆状态详情</div><div class="drawer-sub" id="drawer-subtitle"></div></div><button class="drawer-close" type="button" data-action="close-vehicle-drawer" aria-label="关闭">×</button></div>
  <div class="drawer-body"><div class="summary-grid" id="drawer-summary"></div><div class="status-filter" id="drawer-status-filter"></div><div class="table-wrap"><table><thead><tr><th>车号</th><th>状态</th><th>任务</th><th>司机</th><th>班次</th><th>传感器</th><th>原因</th><th>来源行</th></tr></thead><tbody id="drawer-vehicle-body"></tbody></table></div></div>
</aside>
{_interactive_script()}
</body>
</html>
"""


def render_collection_dashboard_iframe_preview(embed_src: str = "collection_data_dashboard_embed.html") -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>采集数据看板 iframe 预览</title>
<link rel="icon" href="data:," />
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:'Microsoft YaHei','PingFang SC','Segoe UI',Arial,sans-serif;background:#f4f6fb;color:#1f2329}}.app{{min-height:100vh;display:grid;grid-template-columns:236px minmax(0,1fr);grid-template-rows:56px minmax(0,1fr)}}.topbar{{grid-column:1/3;background:#fff;border-bottom:1px solid #eef1f6;display:flex;align-items:center;gap:24px;padding:0 18px}}.brand{{display:flex;align-items:center;gap:10px;font-weight:850;font-size:16px}}.mark{{width:32px;height:32px;border-radius:5px;background:linear-gradient(135deg,#0a5cff 0 48%,#fff 48% 58%,#0a5cff 58%)}}.topnav{{display:flex;gap:30px;color:#4e5969;font-size:14px}}.topnav .active{{color:#1677ff;font-weight:700}}.side{{background:#fff;border-right:1px solid #eef1f6;padding:12px 10px}}.side div{{height:40px;display:flex;align-items:center;border-radius:6px;padding:0 16px;color:#4e5969;margin-bottom:4px}}.side .active{{background:#f2f3f5;color:#1f2329;font-weight:700}}.main{{min-width:0;padding:0 20px 20px;overflow:hidden}}.tabs{{height:48px;background:#fff;border-bottom:1px solid #eef1f6;display:flex;align-items:flex-end;gap:26px;padding:0 18px;margin:0 -20px 16px;overflow-x:auto}}.tab{{height:48px;display:flex;align-items:center;color:#4e5969;font-weight:600;white-space:nowrap}}.tab.active{{color:#1677ff;border-bottom:2px solid #1677ff}}.frame-wrap{{height:calc(100vh - 120px);min-height:620px;background:#fff;border:1px solid #e5e8ef;border-radius:8px;overflow:hidden}}iframe{{width:100%;height:100%;border:0;display:block;background:#f4f6fb}}@media(max-width:900px){{.app{{grid-template-columns:1fr}}.topbar{{grid-column:1}}.side,.topnav{{display:none}}.main{{padding:0 12px 12px}}.tabs{{margin:0 -12px 12px}}}}
</style>
</head>
<body>
<div class="app" data-preview="collection-data-dashboard-iframe">
  <header class="topbar"><div class="brand"><span class="mark"></span><span>Neolix DriveStack</span></div><nav class="topnav"><span class="active">AD大盘</span><span>数据闭环</span><span>模型训练</span><span>资源管理</span></nav></header>
  <aside class="side"><div class="active">数据大盘</div><div>资源大盘</div><div>测试大盘</div><div>大盘配置</div></aside>
  <main class="main"><nav class="tabs"><span class="tab active">采集数据看板</span><span class="tab">末端看板</span><span class="tab">地理分布</span></nav><div class="frame-wrap"><iframe title="采集数据看板" src="{_e(embed_src)}"></iframe></div></main>
</div>
</body>
</html>
"""


def _kpi_card(metric_id: str, label: str, value: Any, sub: str, tone: str) -> str:
    return f"<div class='card kpi tone-{_e(tone)}' data-kpi-id='{_e(metric_id)}'><div class='kpi-label'>{_e(label)}</div><div class='kpi-value'>{_e(value)}</div><div class='kpi-sub'>{_e(sub)}</div></div>"


def _range_summary_cards(view: dict[str, Any], start: str, end: str) -> str:
    metrics = view.get("metrics") or {}
    vehicle = view.get("vehicle_status") or {}
    cards = [
        (
            "日期范围",
            [
                ("开始", start or "-"),
                ("结束", end or "-"),
            ],
        ),
        (
            "人员投入",
            [
                ("参与人数", _metric_display(metrics, "active_people")),
                ("出勤人次", _metric_display(metrics, "attendance_count")),
            ],
        ),
        (
            "任务稳定",
            [
                ("SD/天", _metric_display(metrics, "sd_per_day")),
                ("稳定覆盖", _metric_display(metrics, "stable_participant_coverage")),
            ],
        ),
        (
            "车辆状态",
            [
                ("车辆数", vehicle.get("vehicle_count", 0)),
                ("异常", vehicle.get("abnormal_count", 0)),
            ],
        ),
    ]
    rendered = []
    for title, rows in cards:
        rendered.append(
            "<div class='grain-card' data-range-card='summary'>"
            f"<div class='grain-title'>{_e(title)}</div>"
            "<div class='grain-metrics'>"
            + "".join(f"<div><strong>{_e(value)}</strong>{_e(label)}</div>" for label, value in rows)
            + "</div></div>"
        )
    return "".join(rendered)


def _configured_metric_groups(groups: list[dict[str, Any]]) -> str:
    if not groups:
        return "<div class='metric-grid'><div class='metric-box'><div class='metric-name'>配置指标</div><div class='metric-value'>未启用</div></div></div>"
    boxes: list[str] = []
    for group in groups:
        group_name = group.get("name") or group.get("id") or "指标"
        for metric in group.get("metrics") or []:
            risk = metric.get("risk_level")
            risk_class = f" risk-{risk}" if risk else ""
            boxes.append(
                "<div class='metric-box'>"
                f"<div class='metric-group-title'>{_e(group_name)}</div>"
                f"<div class='metric-name'>{_e(metric.get('name'))}</div>"
                f"<div class='metric-value{_e(risk_class)}'>{_e(metric.get('display_value'))}</div>"
                "</div>"
            )
    return "<div class='metric-grid'>" + "".join(boxes) + "</div>"


def _dashboard_kpi_rows(overview: dict[str, Any]) -> str:
    kpis = overview.get("kpis") or {}
    if not kpis:
        return "<tr><td colspan='3'>看板数据未接入</td></tr>"
    rows = []
    for item in kpis.values():
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td class='left'>{_e(item.get('label') or '-')}</td>"
            f"<td>{_e(item.get('value') or '-')}</td>"
            f"<td class='left'>{_e(item.get('sub') or '-')}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='3'>看板数据未接入</td></tr>"


def _vehicle_bars(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return "<div class='bars'>暂无车辆状态数据</div>"
    rows = []
    for item in summaries:
        total = max(int(item.get("vehicle_count") or 0), 1)
        date_text = item.get("date")
        rows.append(
            "<div class='bar-row'>"
            f"<button type='button' data-action='open-vehicle-day' data-date='{_e(date_text)}'>{_e(date_text)}</button><div class='bar-track'>"
            f"<span class='bar-active' style='width:{(int(item.get('active_count') or 0) / total) * 100:.2f}%'></span>"
            f"<span class='bar-idle' style='width:{(int(item.get('idle_count') or 0) / total) * 100:.2f}%'></span>"
            f"<span class='bar-abnormal' style='width:{(int(item.get('abnormal_count') or 0) / total) * 100:.2f}%'></span>"
            f"<span class='bar-unknown' style='width:{(int(item.get('unknown_count') or 0) / total) * 100:.2f}%'></span>"
            f"</div><div>{_e(item.get('vehicle_count'))}</div></div>"
        )
    return "<div class='bars'>" + "".join(rows) + "</div>"


def _vehicle_summary_rows(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<tr><td colspan='8'>暂无车辆状态数据</td></tr>"
    return "".join(
        "<tr>"
        f"<td><button class='link-button' type='button' data-action='open-vehicle-day' data-date='{_e(item.get('date'))}'>{_e(item.get('date'))}</button></td>"
        f"<td>{_e(item.get('vehicle_count'))}</td><td>{_e(item.get('active_count'))}</td><td>{_e(item.get('idle_count'))}</td><td>{_e(item.get('abnormal_count'))}</td><td>{_e(item.get('unknown_count'))}</td>"
        f"<td>{_vehicle_summary_chips(item)}</td>"
        f"<td><button class='link-button' type='button' data-action='open-vehicle-day' data-date='{_e(item.get('date'))}'>查看详情</button></td>"
        "</tr>"
        for item in items
    )


def _vehicle_summary_chips(item: dict[str, Any]) -> str:
    parts = []
    for key, label, cls in (
        ("active_vehicles", "活跃", "active"),
        ("idle_vehicles", "空闲", "idle"),
        ("abnormal_vehicles", "异常", "abnormal"),
        ("unknown_vehicles", "未知", "unknown"),
    ):
        vehicles = item.get(key) or []
        sample = "、".join(str(value) for value in vehicles[:3])
        suffix = f"：{sample}" if sample else ""
        parts.append(f"<span class='chip {cls}'>{label} {len(vehicles)}{_e(suffix)}</span>")
    return "<div class='detail-chips'>" + "".join(parts) + "</div>"


def _vehicle_detail_rows(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<tr><td colspan='7'>暂无车辆明细</td></tr>"
    return "".join(
        "<tr>"
        f"<td>{_e(item.get('date'))}</td><td>{_e(item.get('car_number'))}</td>"
        f"<td><span class='status {_e(item.get('status'))}'>{_e(item.get('status_label'))}</span></td>"
        f"<td class='left'>{_e(item.get('status_reason'))}</td>"
        f"<td>{_e('、'.join(item.get('drivers') or []) or '-')}</td>"
        f"<td class='left'>{_e('、'.join(item.get('tasks') or []) or '-')}</td>"
        f"<td>{_e('、'.join(item.get('sources') or []) or '-')}</td>"
        "</tr>"
        for item in items
    )


def _top_task_rows(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<tr><td colspan='6'>暂无 Top5 任务</td></tr>"
    return "".join(
        f"<tr><td>{_e(item.get('rank'))}</td><td class='left'>{_e(item.get('task'))}</td><td>{_e(item.get('current_total'))}</td><td>{_e(item.get('previous_total'))}</td><td>{_e(item.get('delta'))}</td><td>{_e(item.get('white'))}/{_e(item.get('night'))}</td></tr>"
        for item in items[:5]
    )


def _interactive_script() -> str:
    return r"""<script>
(() => {
  const root = document.querySelector('[data-dashboard="collection-data-dashboard"]');
  if (!root) return;
  const state = { dashboard: null, startDate: null, endDate: null, selectedDate: null, statusFilter: 'all', currentView: null };
  const statusLabels = { active: '活跃', idle: '空闲', abnormal: '异常', unknown: '未知', all: '全部' };
  const statusOrder = ['all', 'active', 'idle', 'abnormal', 'unknown'];
  const dashboardKpiComputeLabels = {
    dashboard_total_collections: ['采集总次数'],
    dashboard_bos_rate: ['入库率'],
    dashboard_records: ['Record 文件', 'Records'],
    dashboard_mileage: ['总里程'],
    dashboard_quality_pass_rate: ['质检通过率']
  };
  const $ = (selector) => document.querySelector(selector);

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
  const join = (values) => Array.isArray(values) && values.length ? values.join('、') : '-';
  const metricDisplay = (metrics, id) => {
    const metric = metrics?.[id] || {};
    return metric.display_value ?? metric.value ?? '-';
  };
  const statusPill = (status, label) => `<span class="status ${escapeHtml(status || 'unknown')}">${escapeHtml(label || statusLabels[status] || status || '未知')}</span>`;

  function setLoadState(text) {
    const node = $('[data-bind="load-state"]');
    if (node) node.textContent = text || '';
  }

  function setRangeMessage(text) {
    const node = $('[data-bind="range-error"]');
    if (node) node.textContent = text || '';
  }

  async function boot() {
    bindEvents();
    try {
      setLoadState('正在加载交互数据');
      const response = await fetch(root.dataset.source || 'collection_dashboard.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.dashboard = await response.json();
      $('[data-bind="anchor-date"]').textContent = state.dashboard.anchor_date || '-';
      $('[data-bind="generated-at"]').textContent = String(state.dashboard.generated_at || '-').replace('T', ' ').slice(0, 16);
      $('[data-bind="record-count"]').textContent = state.dashboard.record_count ?? 0;
      initDateRangeControls();
      renderAll();
      setLoadState('交互已启用');
    } catch (error) {
      setLoadState('使用静态快照');
      console.warn('collection dashboard data was not loaded; static snapshot remains visible');
    }
  }

  function bindEvents() {
    document.addEventListener('click', (event) => {
      if (event.target.closest('[data-action="apply-date-range"]')) {
        applyDateRange();
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
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeVehicleDrawer();
      if (event.key === 'Enter' && event.target.closest('[data-control="start-date"], [data-control="end-date"]')) {
        event.preventDefault();
        applyDateRange();
      }
    });
  }

  function renderAll() {
    applyDateRange();
    renderDashboardKpis();
  }

  function initDateRangeControls() {
    const bounds = resolveDateBounds();
    const dayPeriod = state.dashboard?.period_views?.day?.current_period || {};
    const startInput = $('[data-control="start-date"]');
    const endInput = $('[data-control="end-date"]');
    state.startDate = startInput?.value || dayPeriod.start_date || state.dashboard?.anchor_date || bounds.max || bounds.min;
    state.endDate = endInput?.value || dayPeriod.end_date || state.startDate || bounds.max || bounds.min;
    [startInput, endInput].forEach((input) => {
      if (!input) return;
      if (bounds.min) input.min = bounds.min;
      if (bounds.max) input.max = bounds.max;
    });
    if (startInput) startInput.value = state.startDate || '';
    if (endInput) endInput.value = state.endDate || '';
  }

  function applyDateRange() {
    if (!state.dashboard) return;
    const startInput = $('[data-control="start-date"]');
    const endInput = $('[data-control="end-date"]');
    let startDate = startInput?.value || state.startDate;
    let endDate = endInput?.value || state.endDate || startDate;
    if (!startDate || !endDate) {
      setRangeMessage('请选择开始和结束日期');
      return;
    }
    if (startDate > endDate) {
      [startDate, endDate] = [endDate, startDate];
      if (startInput) startInput.value = startDate;
      if (endInput) endInput.value = endDate;
    }
    state.startDate = startDate;
    state.endDate = endDate;
    const view = buildRangeView(startDate, endDate);
    state.currentView = view;
    renderKpis(view);
    renderRangeSummary(view);
    renderConfiguredMetrics(view);
    renderTopTasks(view);
    renderVehicleStatus(view);
    setRangeMessage(`${startDate} 至 ${endDate}`);
  }

  function renderKpis(view) {
    const metrics = view.metrics || {};
    const vehicle = view.vehicle_status || {};
    const period = view.current_period || {};
    const rangeLabel = `${period.start_date || '-'} 至 ${period.end_date || '-'}`;
    const cards = [
      ['active_people', '参与人数', metricDisplay(metrics, 'active_people'), rangeLabel, 'blue'],
      ['attendance_count', '出勤人次', metricDisplay(metrics, 'attendance_count'), '有效司机记录', 'cyan'],
      ['sd_per_day', 'SD 个数/天', metricDisplay(metrics, 'sd_per_day'), '所选范围', 'green'],
      ['stable_participant_coverage', '稳定覆盖率', metricDisplay(metrics, 'stable_participant_coverage'), '重点任务池', 'orange'],
      ['vehicle_active_count', '活跃车辆', vehicle.active_count ?? 0, '有效司机优先', 'purple'],
      ['vehicle_abnormal_count', '异常车辆', vehicle.abnormal_count ?? 0, '未安排司机状态', 'red']
    ];
    $('#kpi-grid').innerHTML = cards.map(([id, label, value, sub, tone]) => `
      <div class="card kpi tone-${tone}" data-kpi-id="${id}">
        <div class="kpi-label">${escapeHtml(label)}</div>
        <div class="kpi-value">${escapeHtml(value)}</div>
        <div class="kpi-sub">${escapeHtml(sub)}</div>
      </div>
    `).join('');
  }

  function renderRangeSummary(view) {
    const metrics = view.metrics || {};
    const vehicle = view.vehicle_status || {};
    const period = view.current_period || {};
    const cards = [
      ['日期范围', [['开始', period.start_date || '-'], ['结束', period.end_date || '-']]],
      ['人员投入', [['参与人数', metricDisplay(metrics, 'active_people')], ['出勤人次', metricDisplay(metrics, 'attendance_count')]]],
      ['任务稳定', [['SD/天', metricDisplay(metrics, 'sd_per_day')], ['稳定覆盖', metricDisplay(metrics, 'stable_participant_coverage')]]],
      ['车辆状态', [['车辆数', vehicle.vehicle_count ?? 0], ['异常', vehicle.abnormal_count ?? 0]]]
    ];
    $('#grain-grid').innerHTML = cards.map(([title, rows]) => `<div class="grain-card" data-range-card="summary">
        <div class="grain-title">${escapeHtml(title)}</div>
        <div class="grain-metrics">
          ${rows.map(([label, value]) => `<div><strong>${escapeHtml(value)}</strong>${escapeHtml(label)}</div>`).join('')}
        </div>
      </div>`).join('');
  }

  function renderConfiguredMetrics(view) {
    const groups = view.configured_metric_groups || [];
    if (!groups.length) {
      $('#configured-metrics').innerHTML = '<div class="metric-grid"><div class="metric-box"><div class="metric-name">配置指标</div><div class="metric-value">未启用</div></div></div>';
      return;
    }
    const boxes = groups.flatMap((group) => (group.metrics || []).map((metric) => {
      const riskClass = metric.risk_level ? ` risk-${metric.risk_level}` : '';
      return `<div class="metric-box">
        <div class="metric-group-title">${escapeHtml(group.name || group.id || '指标')}</div>
        <div class="metric-name">${escapeHtml(metric.name)}</div>
        <div class="metric-value${riskClass}">${escapeHtml(metric.display_value)}</div>
      </div>`;
    }));
    $('#configured-metrics').innerHTML = `<div class="metric-grid">${boxes.join('')}</div>`;
  }

  function renderDashboardKpis() {
    const kpis = state.dashboard.dashboard_overview?.kpis || {};
    const rows = Object.values(kpis).map((item) => `<tr><td class="left">${escapeHtml(item.label || '-')}</td><td>${escapeHtml(item.value || '-')}</td><td class="left">${escapeHtml(item.sub || '-')}</td></tr>`);
    $('#dashboard-kpi-body').innerHTML = rows.join('') || '<tr><td colspan="3">看板数据未接入</td></tr>';
  }

  function renderTopTasks(view) {
    const rows = (view.top5_tasks || []).slice(0, 5).map((item) => `<tr>
      <td>${escapeHtml(item.rank)}</td><td class="left">${escapeHtml(item.task)}</td><td>${escapeHtml(item.current_total)}</td>
      <td>${escapeHtml(item.previous_total)}</td><td>${escapeHtml(item.delta)}</td><td>${escapeHtml(item.white)}/${escapeHtml(item.night)}</td>
    </tr>`);
    $('#top-task-body').innerHTML = rows.join('') || '<tr><td colspan="6">暂无 Top5 任务</td></tr>';
  }

  function renderVehicleStatus(view = state.currentView) {
    const summaries = view?.vehicle_daily_summary || [];
    $('#vehicle-bars').innerHTML = `<div class="bars">${summaries.slice(0, 14).map(vehicleBarRow).join('')}</div>`;
    $('#vehicle-summary-body').innerHTML = summaries.slice(0, 30).map(vehicleSummaryRow).join('') || '<tr><td colspan="8">暂无车辆状态数据</td></tr>';
    $('#vehicle-detail-body').innerHTML = (view?.vehicle_daily_status || []).slice(0, 80).map(vehicleDetailRow).join('') || '<tr><td colspan="7">暂无车辆明细</td></tr>';
  }

  function vehicleBarRow(item) {
    const total = Math.max(Number(item.vehicle_count || 0), 1);
    const pct = (value) => `${(Number(value || 0) / total * 100).toFixed(2)}%`;
    return `<div class="bar-row">
      <button type="button" data-action="open-vehicle-day" data-date="${escapeHtml(item.date)}">${escapeHtml(item.date)}</button>
      <div class="bar-track"><span class="bar-active" style="width:${pct(item.active_count)}"></span><span class="bar-idle" style="width:${pct(item.idle_count)}"></span><span class="bar-abnormal" style="width:${pct(item.abnormal_count)}"></span><span class="bar-unknown" style="width:${pct(item.unknown_count)}"></span></div>
      <div>${escapeHtml(item.vehicle_count)}</div>
    </div>`;
  }

  function vehicleSummaryRow(item) {
    return `<tr>
      <td><button class="link-button" type="button" data-action="open-vehicle-day" data-date="${escapeHtml(item.date)}">${escapeHtml(item.date)}</button></td>
      <td>${escapeHtml(item.vehicle_count)}</td><td>${escapeHtml(item.active_count)}</td><td>${escapeHtml(item.idle_count)}</td><td>${escapeHtml(item.abnormal_count)}</td><td>${escapeHtml(item.unknown_count)}</td>
      <td>${vehicleSummaryChips(item)}</td>
      <td><button class="link-button" type="button" data-action="open-vehicle-day" data-date="${escapeHtml(item.date)}">查看详情</button></td>
    </tr>`;
  }

  function vehicleSummaryChips(item) {
    const chips = [
      ['active_vehicles', '活跃', 'active'],
      ['idle_vehicles', '空闲', 'idle'],
      ['abnormal_vehicles', '异常', 'abnormal'],
      ['unknown_vehicles', '未知', 'unknown']
    ].map(([key, label, cls]) => {
      const vehicles = item[key] || [];
      const sample = vehicles.slice(0, 3).join('、');
      return `<span class="chip ${cls}">${label} ${vehicles.length}${sample ? `：${escapeHtml(sample)}` : ''}</span>`;
    });
    return `<div class="detail-chips">${chips.join('')}</div>`;
  }

  function vehicleDetailRow(item) {
    return `<tr>
      <td>${escapeHtml(item.date)}</td><td>${escapeHtml(item.car_number)}</td><td>${statusPill(item.status, item.status_label)}</td>
      <td class="left">${escapeHtml(item.status_reason || '-')}</td><td>${escapeHtml(join(item.drivers))}</td>
      <td class="left">${escapeHtml(join(item.tasks))}</td><td>${escapeHtml(join(item.sources))}</td>
    </tr>`;
  }

  function buildRangeView(startDate, endDate) {
    const records = (state.dashboard.records || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const previous = previousRangeBounds(startDate, endDate);
    const previousRecords = (state.dashboard.records || []).filter((item) => dateInRange(item.date, previous.start, previous.end));
    const vehicleRows = (state.dashboard.vehicle_daily_status || []).filter((item) => dateInRange(item.date, startDate, endDate));
    const drivers = unique(records.map((item) => item.driver));
    const recordDates = unique(records.map((item) => item.date));
    const taskNames = unique(records.map((item) => item.task || '未知任务'));
    const whiteAttendance = records.filter((item) => isWhiteShift(item)).length;
    const nightAttendance = records.filter((item) => isNightShift(item)).length;
    const sdPerDay = recordDates.length ? records.length / recordDates.length : 0;
    const stableCoverage = stableParticipantCoverage(records, drivers, recordDates);
    const top5 = buildTopTasks(records, previousRecords);
    const vehicleStatus = aggregateVehicleRows(vehicleRows);
    const metrics = {
      active_people: makeMetric('参与人数', drivers.length),
      attendance_count: makeMetric('出勤人次', records.length),
      white_attendance: makeMetric('白班人次', whiteAttendance),
      night_attendance: makeMetric('夜班人次', nightAttendance),
      sd_per_day: makeMetric('SD 个数/天', sdPerDay, formatNumber(sdPerDay)),
      stable_participant_coverage: makeMetric('稳定参与者覆盖率', stableCoverage, formatPct(stableCoverage)),
      top_task_count: makeMetric('Top5 任务数', top5.length),
      task_types: makeMetric('任务类型数', taskNames.length),
      vehicle_count: makeMetric('车辆总数', vehicleStatus.vehicle_count),
      vehicle_active_count: makeMetric('活跃车辆', vehicleStatus.active_count),
      vehicle_idle_count: makeMetric('空闲车辆', vehicleStatus.idle_count),
      vehicle_abnormal_count: makeMetric('异常车辆', vehicleStatus.abnormal_count),
      vehicle_unknown_count: makeMetric('未知车辆', vehicleStatus.unknown_count)
    };
    const view = {
      grain: 'range',
      label: '自定义',
      current_period: { start_date: startDate, end_date: endDate },
      compare_period: { start_date: previous.start, end_date: previous.end },
      metrics,
      comparison: {},
      top5_tasks: top5,
      vehicle_status: vehicleStatus,
      vehicle_daily_status: vehicleRows,
      vehicle_daily_summary: summarizeVehicleRows(vehicleRows)
    };
    view.configured_metric_groups = buildConfiguredMetricGroups(view);
    return view;
  }

  function buildTopTasks(records, previousRecords) {
    const current = aggregateTasks(records);
    const previous = aggregateTasks(previousRecords);
    return Array.from(current.values()).sort((a, b) => b.current_total - a.current_total || a.task.localeCompare(b.task, 'zh-CN')).slice(0, 5).map((item, index) => {
      const previousTotal = previous.get(item.task)?.current_total || 0;
      return {
        rank: index + 1,
        task: item.task,
        current_total: item.current_total,
        previous_total: previousTotal,
        delta: item.current_total - previousTotal,
        delta_pct: previousTotal ? (item.current_total - previousTotal) / previousTotal : null,
        white: item.white,
        night: item.night,
        driver_count: item.drivers.size,
        attendance_days: item.dates.size
      };
    });
  }

  function aggregateTasks(records) {
    const tasks = new Map();
    records.forEach((record) => {
      const task = record.task || '未知任务';
      if (!tasks.has(task)) tasks.set(task, { task, current_total: 0, white: 0, night: 0, drivers: new Set(), dates: new Set() });
      const item = tasks.get(task);
      item.current_total += 1;
      if (isWhiteShift(record)) item.white += 1;
      if (isNightShift(record)) item.night += 1;
      if (record.driver) item.drivers.add(record.driver);
      if (record.date) item.dates.add(record.date);
    });
    return tasks;
  }

  function aggregateVehicleRows(rows) {
    const vehicles = new Set();
    const counts = { active: 0, idle: 0, abnormal: 0, unknown: 0 };
    rows.forEach((row) => {
      if (row.car_number) vehicles.add(row.car_number);
      const status = row.status || 'unknown';
      counts[status] = (counts[status] || 0) + 1;
    });
    return {
      vehicle_count: vehicles.size,
      vehicle_day_count: rows.length,
      active_count: counts.active || 0,
      idle_count: counts.idle || 0,
      abnormal_count: counts.abnormal || 0,
      unknown_count: counts.unknown || 0,
      abnormal_items: rows.filter((row) => row.status === 'abnormal').slice(0, 20)
    };
  }

  function summarizeVehicleRows(rows) {
    const grouped = new Map();
    rows.forEach((row) => {
      const date = row.date || '-';
      if (!grouped.has(date)) grouped.set(date, []);
      grouped.get(date).push(row);
    });
    return Array.from(grouped.entries()).map(([date, items]) => {
      const payload = {
        date,
        vehicle_count: items.length,
        active_count: 0,
        idle_count: 0,
        abnormal_count: 0,
        unknown_count: 0,
        active_vehicles: [],
        idle_vehicles: [],
        abnormal_vehicles: [],
        unknown_vehicles: []
      };
      items.forEach((item) => {
        const status = item.status || 'unknown';
        payload[`${status}_count`] = (payload[`${status}_count`] || 0) + 1;
        const list = payload[`${status}_vehicles`];
        if (Array.isArray(list) && item.car_number) list.push(item.car_number);
      });
      ['active_vehicles', 'idle_vehicles', 'abnormal_vehicles', 'unknown_vehicles'].forEach((key) => {
        payload[key] = unique(payload[key]);
      });
      return payload;
    }).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  }

  function buildConfiguredMetricGroups(view) {
    const registry = state.dashboard.metric_registry || {};
    const groups = registry.groups || [];
    const metrics = registry.metrics || [];
    if (!groups.length || !metrics.length) return [];
    const groupMap = new Map(groups.map((group) => [String(group.id), { ...group, metrics: [] }]));
    metrics.forEach((metric) => {
      if (metric.enabled === false || !groupMap.has(String(metric.group))) return;
      const payload = computeConfiguredMetric(metric.compute, view);
      const value = payload.value;
      const display = metric.display || payload.display || 'number';
      groupMap.get(String(metric.group)).metrics.push({
        id: metric.id,
        group: metric.group,
        group_name: groupMap.get(String(metric.group)).name,
        name: metric.name,
        compute: metric.compute,
        display,
        value,
        display_value: payload.display_value ?? formatMetricValue(value, display),
        order: Number(metric.order || 0),
        risk_level: riskLevel(value, metric.thresholds, metric.threshold_direction || 'higher_is_risk')
      });
    });
    return Array.from(groupMap.values())
      .sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
      .map((group) => ({ ...group, metrics: group.metrics.sort((a, b) => a.order - b.order) }))
      .filter((group) => group.metrics.length);
  }

  function computeConfiguredMetric(compute, view) {
    if (compute === 'vehicle_day_count') {
      const value = view.vehicle_status?.vehicle_day_count || 0;
      return { value, display_value: String(value) };
    }
    if (dashboardKpiComputeLabels[compute]) {
      const kpis = state.dashboard.dashboard_overview?.kpis || {};
      for (const label of dashboardKpiComputeLabels[compute]) {
        const item = kpis[label];
        if (item && item.value !== undefined && item.value !== '') {
          return { value: numberFromValue(item.value), display_value: String(item.value) };
        }
      }
      return { value: null, display_value: '-' };
    }
    const metric = view.metrics?.[compute] || {};
    return { value: metric.value, display_value: metric.display_value };
  }

  function stableParticipantCoverage(records, drivers, dates) {
    if (!drivers.length || dates.length <= 1) return 0;
    const daysByDriver = new Map();
    records.forEach((record) => {
      if (!record.driver || !record.date) return;
      if (!daysByDriver.has(record.driver)) daysByDriver.set(record.driver, new Set());
      daysByDriver.get(record.driver).add(record.date);
    });
    const minimumDays = Math.min(2, dates.length);
    const stableCount = Array.from(daysByDriver.values()).filter((days) => days.size >= minimumDays).length;
    return stableCount / drivers.length;
  }

  function makeMetric(name, value, displayValue) {
    return { name, value, display_value: displayValue ?? formatMetricValue(value, 'number') };
  }

  function formatMetricValue(value, display) {
    if (value === null || value === undefined || value === '') return '-';
    if (display === 'percent') return formatPct(Number(value));
    return formatNumber(value);
  }

  function formatNumber(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return String(value ?? '-');
    return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/\.?0+$/, '');
  }

  function formatPct(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return '-';
    return `${(number * 100).toFixed(1)}%`;
  }

  function riskLevel(value, thresholds, direction) {
    if (!thresholds || value === null || value === undefined) return null;
    const number = Number(value);
    if (!Number.isFinite(number)) return null;
    const medium = thresholds.medium;
    const high = thresholds.high;
    if (direction === 'lower_is_risk') {
      if (high !== undefined && number <= Number(high)) return 'high';
      if (medium !== undefined && number <= Number(medium)) return 'medium';
      return 'low';
    }
    if (high !== undefined && number >= Number(high)) return 'high';
    if (medium !== undefined && number >= Number(medium)) return 'medium';
    return 'low';
  }

  function resolveDateBounds() {
    const dates = [
      ...(state.dashboard.records || []).map((item) => item.date),
      ...(state.dashboard.vehicle_daily_status || []).map((item) => item.date),
      ...(state.dashboard.vehicle_daily_summary || []).map((item) => item.date)
    ].filter(Boolean).sort();
    const fallback = state.dashboard.anchor_date || '';
    return { min: dates[0] || fallback, max: dates[dates.length - 1] || fallback };
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
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;
    return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  }

  function addDays(date, days) {
    const next = new Date(date.getTime());
    next.setUTCDate(next.getUTCDate() + days);
    return next;
  }

  function formatDate(date) {
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, '0');
    const day = String(date.getUTCDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function dateInRange(date, startDate, endDate) {
    return Boolean(date && date >= startDate && date <= endDate);
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean).map(String))).sort((a, b) => a.localeCompare(b, 'zh-CN'));
  }

  function isWhiteShift(record) {
    return `${record.shift || ''}${record.shift_table || ''}`.includes('白');
  }

  function isNightShift(record) {
    return `${record.shift || ''}${record.shift_table || ''}`.includes('夜');
  }

  function numberFromValue(value) {
    if (value === null || value === undefined || value === '') return null;
    const text = String(value).replace(/,/g, '').trim();
    const number = Number(text.replace(/[%公里kmKM万]/g, ''));
    if (!Number.isFinite(number)) return null;
    if (text.includes('%')) return number / 100;
    if (text.includes('万')) return number * 10000;
    return number;
  }

  function openVehicleDay(date) {
    if (!state.dashboard || !date) return;
    state.selectedDate = date;
    state.statusFilter = 'all';
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
    const rows = (state.dashboard.vehicle_daily_status || []).filter((item) => item.date === date);
    const counts = rows.reduce((acc, item) => {
      const key = item.status || 'unknown';
      acc[key] = (acc[key] || 0) + 1;
      acc.all += 1;
      return acc;
    }, { all: 0, active: 0, idle: 0, abnormal: 0, unknown: 0 });
    $('#drawer-title').textContent = `${date} 车辆状态`;
    $('#drawer-subtitle').textContent = `共 ${counts.all} 台车；点击状态筛选当天明细`;
    $('#drawer-summary').innerHTML = statusOrder.slice(1).map((status) => `<div class="summary-item"><span>${statusLabels[status]}</span><strong>${counts[status] || 0}</strong></div>`).join('') + `<div class="summary-item"><span>总车辆</span><strong>${counts.all}</strong></div>`;
    $('#drawer-status-filter').innerHTML = statusOrder.map((status) => `<button type="button" class="${state.statusFilter === status ? 'active' : ''}" data-status-filter="${status}">${statusLabels[status]} ${counts[status] || 0}</button>`).join('');
    const filtered = state.statusFilter === 'all' ? rows : rows.filter((item) => item.status === state.statusFilter);
    $('#drawer-vehicle-body').innerHTML = filtered.map((item) => `<tr>
      <td>${escapeHtml(item.car_number)}</td><td>${statusPill(item.status, item.status_label)}</td><td class="left">${escapeHtml(join(item.tasks))}</td>
      <td>${escapeHtml(join(item.drivers))}</td><td>${escapeHtml(join(item.shift_tables))}</td><td>${escapeHtml(join(item.sensors))}</td>
      <td class="left">${escapeHtml(item.status_reason || '-')}</td><td>${escapeHtml(join(item.sources))}:${escapeHtml(join(item.source_lines))}</td>
    </tr>`).join('') || '<tr><td colspan="8">暂无车辆明细</td></tr>';
  }

  boot();
})();
</script>"""


def _metric_display(metrics: dict[str, Any], metric_id: str) -> str:
    metric = metrics.get(metric_id) or {}
    return str(metric.get("display_value") if metric.get("display_value") is not None else metric.get("value", "-"))


def _date_range_defaults(dashboard: dict[str, Any], active_view: dict[str, Any]) -> tuple[str, str, str, str]:
    dates = sorted(
        {
            str(item.get("date"))
            for key in ("records", "vehicle_daily_status", "vehicle_daily_summary")
            for item in (dashboard.get(key) or [])
            if item.get("date")
        }
    )
    current = active_view.get("current_period") or {}
    anchor = str(dashboard.get("anchor_date") or "")
    minimum = dates[0] if dates else anchor
    maximum = dates[-1] if dates else anchor
    start = str(current.get("start_date") or anchor or minimum)
    end = str(current.get("end_date") or start or maximum)
    return start, end, minimum, maximum


def _fmt_generated_at(value: Any) -> str:
    text = str(value or "-").replace("T", " ")
    return text[:16]


def _e(value: Any) -> str:
    return escape("" if value is None else str(value))
