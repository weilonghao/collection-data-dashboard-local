# 采集数据看板本地版

这个文件夹是从 `data-analyst-agent` 项目中整理出来的看板相关资源包。

## 直接打开

双击打开：

```text
app/collection_data_dashboard.html
```

这个 HTML 是自包含文件，数据已经内嵌，不依赖本地 `fetch()`，可以直接用浏览器打开。

## 文件结构

```text
app/
  collection_data_dashboard.html      本地交互版入口
  collection_dashboard.json           当前看板结构化数据
  dashboard_overview.json             数据大盘快照解析结果
  sources_manifest.json               数据源清单
  raw/                                生成看板用的原始快照

source/
  backend/domain/collection_dashboard/local_app.py
                                      本地 HTML 页面模板，改样式主要改这里
  backend/jobs/generate_collection_dashboard.py
                                      看板生成入口
  config/collection_dashboard.yaml    看板生成配置
  config/collection_dashboard_metrics.yaml
                                      旧指标配置，当前本地页不展示“可配置指标”
  config/weekly_sources.yaml          飞书数据源配置
  data/weekly/latest/report.json      周报页嵌入数据来源
  tests/test_collection_data_dashboard.py
                                      看板相关测试
```

## 修改页面样式

主要修改：

```text
source/backend/domain/collection_dashboard/local_app.py
```

常见修改位置：

- 改颜色、卡片、间距、字体：修改 `_LOCAL_APP_TEMPLATE` 里的 `<style>`
- 改页面模块：修改 `_LOCAL_APP_TEMPLATE` 里的 HTML
- 改交互逻辑：修改 `_LOCAL_APP_TEMPLATE` 里的 `<script>`
- 改嵌入数据字段：修改 `build_collection_frontend_payload()`

## 重新生成

在当前文件夹右键打开 PowerShell，然后运行：

```powershell
.\生成看板.ps1
```

脚本会：

1. 进入 `source/`
2. 使用 `app/raw/` 里的原始快照重新生成看板
3. 把最新生成的 `collection_data_dashboard.html` 复制回 `app/`

生成后重新双击：

```text
app/collection_data_dashboard.html
```

## 定时更新并同步飞书

完整链路脚本：

```powershell
.\定时更新并同步飞书.ps1
```

脚本会：

1. 实时拉取 `source/config/weekly_sources.yaml` 中的 6 个飞书采集明细源。
2. 重新生成 `app/collection_data_dashboard.html`。
3. 上传最新 HTML 到飞书云空间文件夹“采集数据看板自动更新”。
4. 创建或刷新飞书入口文档“采集数据看板自动更新入口”。
5. 写入 `app/feishu_publish_result.json` 和 `app/scheduled_refresh.log`。

飞书发布目标配置：

```text
config/feishu_publish.json
```

当前已通过 Codex App 定时任务设置为每 2 小时执行一次。

## 手动运行命令

也可以不用脚本，手动执行：

```powershell
cd .\source

python backend\jobs\generate_collection_dashboard.py `
  --config config\collection_dashboard.yaml `
  --from-raw-dir ..\app\raw `
  --anchor-date 2026-05-12
```

生成结果在：

```text
source/data/collection-dashboard/latest/collection_data_dashboard.html
```
