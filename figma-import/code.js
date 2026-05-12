const DATA = {
  "title": "采集数据看板",
  "generatedAt": "2026-05-11T17:54:28",
  "anchorDate": "2026-05-11",
  "recordCount": 7886,
  "dateRange": "",
  "kpis": [
    {
      "label": "采集总次数",
      "value": "78,897",
      "sub": "2025-10-17 ~ 2026-05-11",
      "allText": "采集总次数\n78,897\n2025-10-17 ~ 2026-05-11"
    },
    {
      "label": "已入库 BOS",
      "value": "76,487",
      "sub": "2,410 待入库",
      "allText": "已入库 BOS\n76,487\n2,410 待入库"
    },
    {
      "label": "入库率",
      "value": "96.9%",
      "sub": "采集 -> BOS",
      "allText": "入库率\n96.9%\n采集 -> BOS"
    },
    {
      "label": "Record 文件",
      "value": "1,087,926",
      "sub": "平均 14.2 个/次",
      "allText": "Record 文件\n1,087,926\n平均 14.2 个/次"
    },
    {
      "label": "总里程",
      "value": "180,317.15 km",
      "sub": "平均 2.3 km/次",
      "allText": "总里程\n180,317.15 km\n平均 2.3 km/次"
    },
    {
      "label": "车辆数",
      "value": "163",
      "sub": "参与采集车辆",
      "allText": "车辆数\n163\n参与采集车辆"
    },
    {
      "label": "城市数",
      "value": "9",
      "sub": "城市分布",
      "allText": "城市数\n9\n城市分布"
    },
    {
      "label": "参与人数",
      "value": "39",
      "sub": "当前日"
    },
    {
      "label": "出勤人次",
      "value": "44",
      "sub": "当前日"
    },
    {
      "label": "车辆总数",
      "value": "86",
      "sub": "当前日"
    },
    {
      "label": "活跃车辆",
      "value": "51",
      "sub": "当前日"
    },
    {
      "label": "异常车辆",
      "value": "19",
      "sub": "当前日"
    }
  ],
  "tasks": [
    {
      "rank": 1,
      "task": "E2E",
      "current": "-",
      "compare": "-",
      "delta": -4
    },
    {
      "rank": 2,
      "task": "TLD 数据回灌",
      "current": "-",
      "compare": "-",
      "delta": 2
    },
    {
      "rank": 3,
      "task": "掉头&右转",
      "current": "-",
      "compare": "-",
      "delta": -8
    },
    {
      "rank": 4,
      "task": "拓路 ISSUE 黑名单",
      "current": "-",
      "compare": "-",
      "delta": -10
    },
    {
      "rank": 5,
      "task": "TLD 数据回灌,4Dlane issue",
      "current": "-",
      "compare": "-",
      "delta": 4
    }
  ],
  "vehicles": [
    {
      "date": "2026-05-12",
      "total": 86,
      "active": 7,
      "idle": 61,
      "abnormal": 18,
      "unknown": 0
    },
    {
      "date": "2026-05-11",
      "total": 86,
      "active": 51,
      "idle": 16,
      "abnormal": 19,
      "unknown": 0
    },
    {
      "date": "2026-05-10",
      "total": 86,
      "active": 58,
      "idle": 13,
      "abnormal": 15,
      "unknown": 0
    },
    {
      "date": "2026-05-09",
      "total": 86,
      "active": 63,
      "idle": 7,
      "abnormal": 16,
      "unknown": 0
    },
    {
      "date": "2026-05-08",
      "total": 86,
      "active": 60,
      "idle": 9,
      "abnormal": 17,
      "unknown": 0
    },
    {
      "date": "2026-05-07",
      "total": 86,
      "active": 62,
      "idle": 5,
      "abnormal": 19,
      "unknown": 0
    },
    {
      "date": "2026-05-06",
      "total": 86,
      "active": 63,
      "idle": 6,
      "abnormal": 17,
      "unknown": 0
    },
    {
      "date": "2026-05-05",
      "total": 86,
      "active": 61,
      "idle": 10,
      "abnormal": 15,
      "unknown": 0
    }
  ],
  "scenes": [
    {
      "label": "路口",
      "count": "18,304"
    },
    {
      "label": "其他",
      "count": "16,418"
    },
    {
      "label": "里程",
      "count": "14,123"
    },
    {
      "label": "末端",
      "count": "12,575"
    },
    {
      "label": "抬杆",
      "count": "10,995"
    },
    {
      "label": "施工",
      "count": "2,757"
    },
    {
      "label": "动态目标专项场景",
      "count": "1,925"
    },
    {
      "label": "TLD",
      "count": "1,365"
    }
  ]
};

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
