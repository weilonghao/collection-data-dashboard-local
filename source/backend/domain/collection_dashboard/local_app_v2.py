"""Neutral resource-management HTML app for the collection dashboard."""

from __future__ import annotations

import json
from html import escape
from typing import Any


def render_collection_dashboard_local_app_v2(
    dashboard: dict[str, Any],
    *,
    weekly_report: dict[str, Any] | None = None,
) -> str:
    payload = build_collection_frontend_payload_v2(dashboard, weekly_report=weekly_report)
    return HTML.replace("__TITLE__", escape("采集资源管理看板")).replace("__PAYLOAD__", _json_payload(payload))


def build_collection_frontend_payload_v2(
    dashboard: dict[str, Any],
    *,
    weekly_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    units = _task_units(list(dashboard.get("records") or []))
    vehicles = list(dashboard.get("vehicle_daily_status") or [])
    outputs = list(dashboard.get("collection_output_records") or [])
    schedules = list(dashboard.get("resource_schedule_records") or [])
    diagnostics = [*list(dashboard.get("diagnostics") or []), *list(dashboard.get("metric_diagnostics") or [])]
    rows = [*units, *vehicles, *outputs, *schedules]
    dates = sorted({str(row.get("date")) for row in rows if row.get("date")})
    return {
        "generated_at": dashboard.get("generated_at"),
        "anchor_date": dashboard.get("anchor_date") or (dates[-1] if dates else ""),
        "record_count": dashboard.get("record_count", 0),
        "date_bounds": {"min": dates[0] if dates else "", "max": dates[-1] if dates else ""},
        "task_attendance_units": units,
        "vehicle_daily_status": vehicles,
        "collection_output_records": outputs,
        "resource_schedule_records": schedules,
        "diagnostics": diagnostics,
        "weekly_report_summary": _weekly_summary(weekly_report),
        "filter_options": {
            "departments": _unique(row.get("department") for row in rows),
            "sites": _unique(row.get("site") for row in rows),
            "source_roles": _unique(row.get("source_role") for row in rows),
        },
    }


def _task_units(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for record in records:
        date = str(record.get("date") or "").strip()
        driver = str(record.get("driver") or "").strip()
        if not date or not driver:
            continue
        department = str(record.get("department") or "数采")
        site = str(record.get("site") or "")
        task = str(record.get("task") or "未标注任务")
        key = (date, department, site, task, driver)
        item = seen.setdefault(
            key,
            {
                "date": date,
                "department": department,
                "site": site,
                "source_role": str(record.get("source_role") or ""),
                "task": task,
                "driver": driver,
                "car_number": str(record.get("car_number") or ""),
                "shift": str(record.get("shift") or record.get("shift_table") or ""),
                "effective_time": 0.0,
                "total_collection": 0.0,
            },
        )
        item["effective_time"] = float(item.get("effective_time") or 0) + _float_value(record.get("effective_time"))
        item["total_collection"] = float(item.get("total_collection") or 0) + _float_value(record.get("total_collection"))
    rows = list(seen.values())
    rows.sort(key=lambda row: (row["date"], row["department"], row["site"], row["task"], row["driver"]), reverse=True)
    return rows


def _weekly_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {"available": False}
    focus = report.get("focus_summary") or {}
    return {
        "available": True,
        "week_id": report.get("week_id"),
        "period": report.get("period") or {},
        "generated_at": report.get("generated_at"),
        "kpis": report.get("kpis") or {},
        "tasks": list(focus.get("top5_tasks") or [])[:8],
        "stability": list(focus.get("top_task_personnel_stability") or [])[:8],
    }


def _unique(values: Any) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value or "").strip()})


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _json_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>__TITLE__</title>
<link rel="icon" href="data:," />
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f7fb;color:#172033;font:14px/1.5 "Microsoft YaHei","PingFang SC","Segoe UI",Arial,sans-serif}button,input,select{font:inherit}.top{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #dfe5ee}.topline{display:flex;gap:18px;align-items:center;padding:12px 18px}.brand{min-width:190px}.brand b{display:block;font-size:18px}.muted,.brand span{color:#667085;font-size:12px}.nav{display:flex;gap:4px;overflow:auto}.nav button{height:34px;border:0;border-radius:6px;background:transparent;color:#344054;padding:0 12px;white-space:nowrap;cursor:pointer}.nav button.active{background:#172033;color:#fff}.filters{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:10px;padding:0 18px 12px}.field{display:grid;gap:4px}.field span{color:#667085;font-size:12px}.field input,.field select{height:34px;border:1px solid #d0d7e2;border-radius:6px;background:#fff;padding:0 9px;min-width:0}.content{padding:16px 18px 28px}.page{display:none}.page.active{display:block}.head{display:flex;justify-content:space-between;gap:16px;margin-bottom:12px}.title{font-size:20px;font-weight:900}.stamp{color:#667085;font-size:12px;text-align:right}.kpis{display:grid;grid-template-columns:repeat(7,minmax(115px,1fr));gap:10px;margin-bottom:12px}.card{background:#fff;border:1px solid #dfe5ee;border-radius:8px;overflow:hidden}.kpi{padding:14px;min-height:96px}.kpi span{display:block;color:#667085;font-size:12px}.kpi strong{display:block;font-size:24px;margin-top:7px}.kpi small{display:block;color:#667085;font-size:12px;margin-top:7px}.blue strong{color:#2364d8}.green strong{color:#07875a}.amber strong{color:#b76e00}.red strong{color:#c93535}.teal strong{color:#007c89}.section{margin-bottom:12px}.section-h{padding:12px 14px;border-bottom:1px solid #dfe5ee}.section-h b{display:block}.section-h span{display:block;color:#667085;font-size:12px}.split{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr);gap:12px}.table{overflow:auto}table{width:100%;min-width:760px;border-collapse:collapse}th,td{padding:9px 10px;border-bottom:1px solid #edf1f6;text-align:center;vertical-align:top}th{background:#f8fafc;color:#465062;font-size:12px;font-weight:850}td.left{text-align:left}.empty{padding:22px;color:#667085;text-align:center}.tag{display:inline-flex;border-radius:999px;padding:2px 8px;font-size:12px;font-weight:800}.active-tag{background:#e9fbf3;color:#07875a}.idle-tag{background:#eef2f7;color:#526071}.risk-tag{background:#fff1f1;color:#c93535}.risk-list{padding:10px 14px}.risk{display:grid;grid-template-columns:92px minmax(0,1fr);gap:10px;padding:8px 0;border-bottom:1px solid #edf1f6}.risk small{display:block;color:#667085}@media(max-width:1180px){.filters{grid-template-columns:repeat(2,minmax(140px,1fr))}.kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.split{grid-template-columns:1fr}}@media(max-width:680px){.topline{display:block}.nav{margin-top:10px}.filters{grid-template-columns:1fr;padding:0 12px 12px}.content{padding:12px}.head{display:block}.stamp{text-align:left;margin-top:6px}.kpis{grid-template-columns:1fr}}
</style>
</head>
<body>
<main class="app" data-app="collection-dashboard-local">
<header class="top"><div class="topline"><div class="brand"><b>统一资源管理视图</b><span>采集数据看板</span></div><nav class="nav" aria-label="页面导航"><button class="active" type="button" data-page="overview">资源总览</button><button type="button" data-page="dispatch">车辆/人员调度</button><button type="button" data-page="output">采集产出</button><button type="button" data-page="risk">异常风险</button><button type="button" data-page="weekly">周报与诊断</button></nav></div><section class="filters" aria-label="全局筛选"><label class="field"><span>开始日期</span><input type="date" data-filter="from"></label><label class="field"><span>结束日期</span><input type="date" data-filter="to"></label><label class="field"><span>责任域</span><select data-filter="department"><option value="">全部责任域</option></select></label><label class="field"><span>城市</span><select data-filter="site"><option value="">全部城市</option></select></label><label class="field"><span>数据类型</span><select data-filter="source_role"><option value="">全部类型</option></select></label></section></header>
<section class="content">
<section class="page active" data-page-panel="overview"><div class="head"><div><div class="title" data-title>资源总览</div><div class="muted">统一查看资源状态、产出和风险定位；责任域仅用于归属筛选。</div></div><div class="stamp" data-stamp></div></div><div class="kpis" id="kpis"></div><div class="split"><section class="card section"><div class="section-h"><b>资源分布列表</b><span>按责任域、城市、任务聚合展示资源占用和风险数量</span></div><div class="table"><table><thead><tr><th>责任域</th><th>城市</th><th>任务</th><th>人员</th><th>车辆</th><th>活跃车</th><th>空闲车</th><th>采集时长</th><th>风险</th></tr></thead><tbody id="distribution"></tbody></table></div></section><section class="card section"><div class="section-h"><b>风险定位</b><span>异常车辆、异常备注和生成诊断</span></div><div id="risk-snapshot" class="risk-list"></div></section></div></section>
<section class="page" data-page-panel="dispatch"><div class="head"><div><div class="title" data-title>车辆/人员调度</div><div class="muted">查看车辆池、任务、班次、司机和出车备注。</div></div><div class="stamp" data-stamp></div></div><section class="card section"><div class="section-h"><b>调度明细</b><span>来自排班和车辆资源表</span></div><div class="table"><table><thead><tr><th>日期</th><th>责任域</th><th>城市</th><th>任务</th><th>班次</th><th>车号</th><th>司机</th><th>出车时间</th><th>异常备注</th><th>来源</th></tr></thead><tbody id="dispatch"></tbody></table></div></section></section>
<section class="page" data-page-panel="output"><div class="head"><div><div class="title" data-title>采集产出</div><div class="muted">查看采集员、场景、路线、时长、里程和取数状态。</div></div><div class="stamp" data-stamp></div></div><section class="card section"><div class="section-h"><b>产出明细</b><span>来自实际采集明细表</span></div><div class="table"><table><thead><tr><th>日期</th><th>责任域</th><th>城市</th><th>车号</th><th>采集员</th><th>场景</th><th>路线</th><th>开始</th><th>结束</th><th>时长</th><th>里程</th><th>是否取数</th><th>异常备注</th></tr></thead><tbody id="output"></tbody></table></div></section></section>
<section class="page" data-page-panel="risk"><div class="head"><div><div class="title" data-title>异常风险</div><div class="muted">聚合车辆异常、产出异常备注和生成链路诊断。</div></div><div class="stamp" data-stamp></div></div><section class="card section"><div class="section-h"><b>风险清单</b><span>用于定位资源与数据链路问题</span></div><div id="risk-list" class="risk-list"></div></section></section>
<section class="page" data-page-panel="weekly"><div class="head"><div><div class="title" data-title>周报与诊断</div><div class="muted">保留周报摘要与数据源诊断，便于追溯。</div></div><div class="stamp" data-stamp></div></div><section class="card section"><div class="section-h"><b>周报摘要</b><span id="weekly-meta">暂无周报数据</span></div><div class="table"><table><thead><tr><th>项目</th><th>数值</th><th>说明</th></tr></thead><tbody id="weekly"></tbody></table></div></section></section>
</section>
<script id="collection-dashboard-data" type="application/json">__PAYLOAD__</script>
<script>
(() => {
const D=JSON.parse(document.getElementById("collection-dashboard-data").textContent);
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>Array.from(r.querySelectorAll(s));
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));
const roleName={resource_schedule:"排班/资源",collection_output:"采集产出",collection_detail:"采集明细"};
const S={page:"overview",from:D.date_bounds?.min||"",to:D.date_bounds?.max||"",department:"",site:"",source_role:""};
function setSelect(name,items,label){const el=$(`[data-filter="${name}"]`);el.innerHTML=`<option value="">全部${label}</option>`+(items||[]).map(v=>`<option value="${esc(v)}">${esc(roleName[v]||v)}</option>`).join("");}
function init(){setSelect("department",D.filter_options?.departments,"责任域");setSelect("site",D.filter_options?.sites,"城市");setSelect("source_role",D.filter_options?.source_roles,"类型");$('[data-filter="from"]').value=S.from;$('[data-filter="to"]').value=S.to;$$("[data-filter]").forEach(el=>el.addEventListener("change",()=>{S[el.dataset.filter]=el.value;render();}));$$("[data-page]").forEach(b=>b.addEventListener("click",()=>{S.page=b.dataset.page;$$("[data-page]").forEach(x=>x.classList.toggle("active",x===b));$$("[data-page-panel]").forEach(p=>p.classList.toggle("active",p.dataset.pagePanel===S.page));renderTitles();}));render();}
function ok(r){const d=String(r.date||"");return(!d||((!S.from||d>=S.from)&&(!S.to||d<=S.to)))&&(!S.department||r.department===S.department)&&(!S.site||r.site===S.site)&&(!S.source_role||r.source_role===S.source_role);}
function rows(k){return (D[k]||[]).filter(ok);}
function uniq(a){return new Set(a.filter(Boolean).map(String)).size}
function sum(a,f){return a.reduce((n,x)=>n+(Number(f(x))||0),0)}
function fmt(n,d=0){return Number(n||0).toLocaleString("zh-CN",{maximumFractionDigits:d})}
function join(v){return Array.isArray(v)?v.filter(Boolean).join("、"):String(v||"")}
function render(){const u=rows("task_attendance_units"),v=rows("vehicle_daily_status"),o=rows("collection_output_records"),s=rows("resource_schedule_records"),risk=risks(v,o,s);renderTitles();renderKpis(u,v,o,s,risk);renderDistribution(u,v,o,s);renderRisks(risk,"#risk-snapshot",8);renderRisks(risk,"#risk-list",120);renderDispatch(s);renderOutput(o);renderWeekly();}
function renderTitles(){const scope=S.department||"全部责任域";$$("[data-title]").forEach(t=>{const base=t.textContent.split(" · ").pop();t.textContent=`${scope} · ${base}`});$$("[data-stamp]").forEach(e=>e.textContent=`生成 ${D.generated_at||"-"} | 日期 ${S.from||"-"} 至 ${S.to||"-"}`);}
function renderKpis(u,v,o,s,risk){const people=uniq([...u.map(x=>x.driver),...o.map(x=>x.collector),...s.map(x=>x.driver)]);const vehicles=uniq([...v.map(x=>x.car_number),...o.map(x=>x.car_number),...s.map(x=>x.car_number)]);const active=uniq(v.filter(x=>x.status==="active").map(x=>x.car_number));const idle=uniq(v.filter(x=>x.status==="idle").map(x=>x.car_number));const hours=sum(u,x=>x.effective_time)+sum(o,x=>Number(x.duration_minutes||0)/60);const miles=sum(o,x=>x.mileage_km);const cards=[["出勤人数",people,"去重人员","blue"],["车辆总数",vehicles,"筛选范围车辆","teal"],["活跃车辆",active,"有司机安排","green"],["空闲车辆",idle,"未安排司机","amber"],["采集时长",fmt(hours,1)+"h","产出与明细合计","blue"],["采集里程",fmt(miles,1)+"km","来自产出表","green"],["异常数",risk.length,"需定位处理","red"]];$("#kpis").innerHTML=cards.map(c=>`<div class="card kpi ${c[3]}"><span>${c[0]}</span><strong>${c[1]}</strong><small>${c[2]}</small></div>`).join("");}
function renderDistribution(u,v,o,s){const m=new Map(),ensure=(d,site,task)=>{const k=[d||"未标注",site||"未标注",task||"未标注任务"].join("|");if(!m.has(k))m.set(k,{d:d||"未标注",site:site||"未标注",task:task||"未标注任务",people:new Set(),cars:new Set(),active:new Set(),idle:new Set(),hours:0,risk:0});return m.get(k)};u.forEach(x=>{const r=ensure(x.department,x.site,x.task);r.people.add(x.driver);if(x.car_number)r.cars.add(x.car_number);r.hours+=Number(x.effective_time||0)});s.forEach(x=>{const r=ensure(x.department,x.site,x.task);if(x.driver)r.people.add(x.driver);if(x.car_number)r.cars.add(x.car_number);if(x.exception_note)r.risk++});o.forEach(x=>{const r=ensure(x.department,x.site,x.scene||x.route);if(x.collector)r.people.add(x.collector);if(x.car_number)r.cars.add(x.car_number);r.hours+=Number(x.duration_minutes||0)/60;if(x.exception_note)r.risk++});v.forEach(x=>(x.tasks?.length?x.tasks:["未标注任务"]).forEach(t=>{const r=ensure(x.department,x.site,t);if(x.car_number)r.cars.add(x.car_number);if(x.status==="active")r.active.add(x.car_number);if(x.status==="idle")r.idle.add(x.car_number);if(x.status==="abnormal"||x.status==="unknown")r.risk++}));const out=[...m.values()].sort((a,b)=>b.risk-a.risk||a.d.localeCompare(b.d,"zh-CN"));$("#distribution").innerHTML=out.map(r=>`<tr><td>${esc(r.d)}</td><td>${esc(r.site)}</td><td class="left">${esc(r.task)}</td><td>${r.people.size}</td><td>${r.cars.size}</td><td>${r.active.size}</td><td>${r.idle.size}</td><td>${fmt(r.hours,1)}h</td><td>${r.risk}</td></tr>`).join("")||`<tr><td colspan="9" class="empty">暂无资源数据</td></tr>`;}
function risks(v,o,s){const a=[];v.filter(x=>x.status==="abnormal"||x.status==="unknown").forEach(x=>a.push({k:"车辆",t:x.car_number||"-",m:x.status_reason||x.status_label,d:x.date,dept:x.department,site:x.site}));o.filter(x=>x.exception_note).forEach(x=>a.push({k:"产出",t:x.car_number||x.collector||"-",m:x.exception_note,d:x.date,dept:x.department,site:x.site}));s.filter(x=>x.exception_note).forEach(x=>a.push({k:"调度",t:x.car_number||x.driver||"-",m:x.exception_note,d:x.date,dept:x.department,site:x.site}));(D.diagnostics||[]).forEach(x=>a.push({k:"诊断",t:x.code||x.source||"-",m:x.message||x.reason||JSON.stringify(x),d:x.date||"",dept:x.department||"",site:x.site||""}));return a}
function renderRisks(a,sel,max){$(sel).innerHTML=a.slice(0,max).map(x=>`<div class="risk"><div class="muted">${esc(x.k)}</div><div><b>${esc(x.t)}</b><small>${esc([x.d,x.dept,x.site].filter(Boolean).join(" / "))}</small><div>${esc(x.m||"-")}</div></div></div>`).join("")||`<div class="empty">暂无异常风险</div>`}
function renderDispatch(a){$("#dispatch").innerHTML=a.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.department)}</td><td>${esc(x.site)}</td><td class="left">${esc(x.task)}</td><td>${esc(x.shift)}</td><td>${esc(x.car_number)}</td><td>${esc(x.driver||"-")}</td><td>${esc(x.departure_time||"-")}</td><td class="left">${esc(x.exception_note||"-")}</td><td>${esc(x.source||"-")}:${esc(x.source_line||"")}</td></tr>`).join("")||`<tr><td colspan="10" class="empty">暂无调度明细</td></tr>`}
function renderOutput(a){$("#output").innerHTML=a.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.department)}</td><td>${esc(x.site)}</td><td>${esc(x.car_number)}</td><td>${esc(x.collector)}</td><td class="left">${esc(x.scene)}</td><td class="left">${esc(x.route)}</td><td>${esc(x.start_time)}</td><td>${esc(x.end_time)}</td><td>${fmt(x.duration_minutes,1)}min</td><td>${fmt(x.mileage_km,1)}km</td><td>${esc(x.is_collected||"-")}</td><td class="left">${esc(x.exception_note||"-")}</td></tr>`).join("")||`<tr><td colspan="13" class="empty">暂无采集产出</td></tr>`}
function renderWeekly(){const w=D.weekly_report_summary||{};if(!w.available){$("#weekly-meta").textContent="暂无周报数据";$("#weekly").innerHTML=`<tr><td colspan="3" class="empty">暂无周报数据</td></tr>`;return}$("#weekly-meta").textContent=`${w.week_id||"-"} ${w.period?.start_date||""} 至 ${w.period?.end_date||""}`;const k=w.kpis||{};$("#weekly").innerHTML=[["周出勤人次",k.total_attendance,"周报口径"],["唯一人员",k.unique_drivers,"周内去重"],["日均人员",k.avg_daily_sd,"按有数据日期"],["重点任务样本",(w.tasks||[]).map(x=>x.task).filter(Boolean).join("、"),"用于诊断任务集中情况"]].map(x=>`<tr><td>${esc(x[0])}</td><td>${esc(x[1]??"-")}</td><td class="left">${esc(x[2])}</td></tr>`).join("")}
init();
})();
</script>
</main>
</body>
</html>"""
