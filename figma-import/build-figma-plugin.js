const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const dashboard = JSON.parse(
  fs.readFileSync(path.join(root, "app", "collection_dashboard.json"), "utf8")
);

function pickKpis() {
  const overviewKpis = Object.values(dashboard.dashboard_overview?.kpis || {});
  const dayMetrics = dashboard.period_views?.day?.metrics || {};
  const daily = [
    ["参与人数", dayMetrics.active_people?.display_value],
    ["出勤人次", dayMetrics.attendance_count?.display_value],
    ["车辆总数", dayMetrics.vehicle_count?.display_value],
    ["活跃车辆", dayMetrics.vehicle_active_count?.display_value],
    ["异常车辆", dayMetrics.vehicle_abnormal_count?.display_value],
  ]
    .filter(([, value]) => value !== undefined)
    .map(([label, value]) => ({ label, value, sub: "当前日" }));

  return overviewKpis.slice(0, 7).concat(daily).slice(0, 12);
}

function pickTasks() {
  return (dashboard.period_views?.day?.top5_tasks || []).slice(0, 5).map((item, index) => ({
    rank: index + 1,
    task: item.task || item.name || "-",
    current: item.current_count ?? item.current_value ?? item.count ?? "-",
    compare: item.compare_count ?? item.compare_value ?? "-",
    delta: item.delta ?? "-",
  }));
}

function pickVehicles() {
  const dayVehicleStatus = dashboard.period_views?.day?.vehicle_status;
  const rows = Array.isArray(dayVehicleStatus)
    ? dayVehicleStatus
    : Array.isArray(dashboard.vehicle_daily_summary)
      ? dashboard.vehicle_daily_summary
      : [];
  return rows
    .slice(0, 8)
    .map((item) => ({
      date: item.date || "-",
      total: item.vehicle_count ?? item.total_count ?? "-",
      active: item.active_count ?? "-",
      idle: item.idle_count ?? "-",
      abnormal: item.abnormal_count ?? "-",
      unknown: item.unknown_count ?? "-",
    }));
}

function pickScenes() {
  return (dashboard.dashboard_overview?.scene_summary || [])
    .filter((item) => item.level === "primary")
    .slice(0, 8)
    .map((item) => ({
      label: String(item.value || item.text || "-").replace(/^p:/, ""),
      count: item.count || "",
    }));
}

const importData = {
  title: "采集数据看板",
  generatedAt: dashboard.generated_at,
  anchorDate: dashboard.anchor_date,
  recordCount: dashboard.record_count,
  dateRange: dashboard.dashboard_overview?.date_filter?.range_text || "",
  kpis: pickKpis(),
  tasks: pickTasks(),
  vehicles: pickVehicles(),
  scenes: pickScenes(),
};

const dataLiteral = JSON.stringify(importData, null, 2);

const manifest = {
  name: "采集数据看板导入器",
  id: "collection-data-dashboard-importer",
  api: "1.0.0",
  main: "code.js",
  documentAccess: "dynamic-page",
  editorType: ["figma"],
};

const code = `const DATA = ${dataLiteral};

figma.showUI("<p style='font:13px sans-serif;margin:12px'>正在导入采集数据看板...</p>", { visible: false });

const C = {
  page: { r: 244 / 255, g: 246 / 255, b: 251 / 255 },
  white: { r: 1, g: 1, b: 1 },
  border: { r: 229 / 255, g: 232 / 255, b: 239 / 255 },
  text: { r: 31 / 255, g: 35 / 255, b: 41 / 255 },
  muted: { r: 134 / 255, g: 144 / 255, b: 156 / 255 },
  blue: { r: 22 / 255, g: 119 / 255, b: 255 / 255 },
  cyan: { r: 19 / 255, g: 194 / 255, b: 194 / 255 },
  green: { r: 0, g: 168 / 255, b: 112 / 255 },
  orange: { r: 250 / 255, g: 140 / 255, b: 22 / 255 },
  red: { r: 255 / 255, g: 77 / 255, b: 79 / 255 },
};

function paint(color) {
  return [{ type: "SOLID", color }];
}

function rect(name, x, y, w, h, fill = C.white, radius = 8) {
  const node = figma.createRectangle();
  node.name = name;
  node.x = x;
  node.y = y;
  node.resize(w, h);
  node.fills = paint(fill);
  node.cornerRadius = radius;
  node.strokes = paint(C.border);
  node.strokeWeight = 1;
  return node;
}

async function text(name, value, x, y, size = 14, color = C.text, weight = "Regular", width = 220) {
  await figma.loadFontAsync({ family: "Inter", style: weight });
  const node = figma.createText();
  node.name = name;
  node.x = x;
  node.y = y;
  node.resize(width, 20);
  node.characters = String(value === undefined || value === null ? "" : value);
  node.fontName = { family: "Inter", style: weight };
  node.fontSize = size;
  node.fills = paint(color);
  node.textAutoResize = "HEIGHT";
  return node;
}

function fmt(value) {
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

async function main() {
  const frame = figma.createFrame();
  frame.name = "采集数据看板 / Codex Import";
  frame.resize(1440, 1280);
  frame.fills = paint(C.page);
  frame.x = 0;
  frame.y = 0;

  await text("标题", DATA.title, 32, 28, 28, C.text, "Bold", 360);
  await text("元信息", "锚点日期 " + fmt(DATA.anchorDate) + "   生成 " + fmt(DATA.generatedAt) + "   记录 " + fmt(DATA.recordCount), 32, 68, 13, C.muted, "Regular", 760);

  const tones = [C.blue, C.cyan, C.green, C.orange, C.blue, C.green, C.orange, C.red, C.cyan, C.blue, C.orange, C.green];
  DATA.kpis.forEach((item, index) => {
    const col = index % 4;
    const row = Math.floor(index / 4);
    const x = 32 + col * 344;
    const y = 112 + row * 136;
    frame.appendChild(rect("KPI / " + item.label, x, y, 320, 112));
  });

  for (let index = 0; index < DATA.kpis.length; index++) {
    const item = DATA.kpis[index];
    const col = index % 4;
    const row = Math.floor(index / 4);
    const x = 52 + col * 344;
    const y = 130 + row * 136;
    frame.appendChild(await text("KPI Label / " + item.label, item.label, x, y, 12, C.muted, "Regular", 260));
    frame.appendChild(await text("KPI Value / " + item.label, item.value, x, y + 28, 28, tones[index % tones.length], "Bold", 260));
    frame.appendChild(await text("KPI Sub / " + item.label, fmt(item.sub), x, y + 72, 12, C.muted, "Regular", 260));
  }

  const sectionY = 540;
  frame.appendChild(rect("Section / Top5 任务", 32, sectionY, 660, 310));
  frame.appendChild(await text("Section Title / Top5", "Top5 任务", 56, sectionY + 18, 18, C.text, "Bold", 240));
  const headers = ["排名", "任务", "当前", "对比", "变化"];
  const colX = [56, 118, 430, 510, 590];
  for (let i = 0; i < headers.length; i++) {
    frame.appendChild(await text("Table Header / " + headers[i], headers[i], colX[i], sectionY + 58, 12, C.muted, "Bold", i === 1 ? 280 : 64));
  }
  for (let r = 0; r < DATA.tasks.length; r++) {
    const row = DATA.tasks[r];
    const y = sectionY + 92 + r * 38;
    frame.appendChild(await text("Task Rank / " + row.rank, row.rank, colX[0], y, 13, C.text, "Regular", 48));
    frame.appendChild(await text("Task Name / " + row.rank, fmt(row.task), colX[1], y, 13, C.text, "Regular", 290));
    frame.appendChild(await text("Task Current / " + row.rank, fmt(row.current), colX[2], y, 13, C.text, "Regular", 64));
    frame.appendChild(await text("Task Compare / " + row.rank, fmt(row.compare), colX[3], y, 13, C.text, "Regular", 64));
    frame.appendChild(await text("Task Delta / " + row.rank, fmt(row.delta), colX[4], y, 13, C.text, "Regular", 64));
  }

  frame.appendChild(rect("Section / 场景分布", 724, sectionY, 684, 310));
  frame.appendChild(await text("Section Title / Scenes", "一级场景分布", 748, sectionY + 18, 18, C.text, "Bold", 260));
  const maxScene = Math.max(...DATA.scenes.map((s) => Number(String(s.count).replace(/,/g, "")) || 0), 1);
  for (let i = 0; i < DATA.scenes.length; i++) {
    const scene = DATA.scenes[i];
    const y = sectionY + 60 + i * 28;
    const n = Number(String(scene.count).replace(/,/g, "")) || 0;
    frame.appendChild(await text("Scene Label / " + scene.label, scene.label, 748, y, 12, C.text, "Regular", 150));
    const bar = rect("Scene Bar / " + scene.label, 910, y + 4, Math.max(4, (n / maxScene) * 370), 12, i % 2 ? C.cyan : C.blue, 6);
    bar.strokes = [];
    frame.appendChild(bar);
    frame.appendChild(await text("Scene Count / " + scene.label, scene.count, 1300, y, 12, C.muted, "Regular", 80));
  }

  const vehicleY = 884;
  frame.appendChild(rect("Section / 每日车辆状态", 32, vehicleY, 1376, 340));
  frame.appendChild(await text("Section Title / Vehicles", "每日车辆状态", 56, vehicleY + 18, 18, C.text, "Bold", 260));
  const vehicleHeaders = ["日期", "车辆数", "活跃", "空闲", "异常", "未知"];
  const vx = [56, 260, 430, 600, 770, 940];
  for (let i = 0; i < vehicleHeaders.length; i++) {
    frame.appendChild(await text("Vehicle Header / " + vehicleHeaders[i], vehicleHeaders[i], vx[i], vehicleY + 58, 12, C.muted, "Bold", 120));
  }
  for (let r = 0; r < DATA.vehicles.length; r++) {
    const row = DATA.vehicles[r];
    const y = vehicleY + 94 + r * 28;
    frame.appendChild(await text("Vehicle Date / " + r, row.date, vx[0], y, 13, C.text, "Regular", 120));
    frame.appendChild(await text("Vehicle Total / " + r, row.total, vx[1], y, 13, C.text, "Regular", 90));
    frame.appendChild(await text("Vehicle Active / " + r, row.active, vx[2], y, 13, C.green, "Regular", 90));
    frame.appendChild(await text("Vehicle Idle / " + r, row.idle, vx[3], y, 13, C.muted, "Regular", 90));
    frame.appendChild(await text("Vehicle Abnormal / " + r, row.abnormal, vx[4], y, 13, C.red, "Regular", 90));
    frame.appendChild(await text("Vehicle Unknown / " + r, row.unknown, vx[5], y, 13, C.orange, "Regular", 90));
  }

  figma.currentPage.appendChild(frame);
  figma.viewport.scrollAndZoomIntoView([frame]);
  figma.closePlugin("已导入采集数据看板，可继续编辑图层。");
}

main().catch((error) => {
  figma.closePlugin("导入失败: " + error.message);
});
`;

fs.writeFileSync(path.join(__dirname, "manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
fs.writeFileSync(path.join(__dirname, "code.js"), code, "utf8");
fs.writeFileSync(path.join(__dirname, "import-data.json"), JSON.stringify(importData, null, 2), "utf8");

console.log("Generated Figma plugin files in " + __dirname);
