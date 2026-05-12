# Figma 导入包

这个目录用于把当前本地看板导入 Figma。

## 产物

- `manifest.json`: Figma 本地插件入口
- `code.js`: 插件主代码，会在 Figma 中生成可编辑的看板 Frame
- `import-data.json`: 从 `app/collection_dashboard.json` 抽取的导入数据
- `collection-dashboard-desktop.png`: 当前桌面版看板截图
- `collection-dashboard-mobile.png`: 当前移动版看板截图

## 在 Figma 中导入

不要在 Figma 首页或 Team project 里用 `Import` 上传 `manifest.json`，那个入口是导入设计文件，不是导入插件，会提示 `Unsupported file format`。

1. 打开 Figma Desktop。
2. 新建或打开一个 Design file，必须进入画布编辑界面。
3. 在顶部菜单选择 `Plugins` -> `Development` -> `Import plugin from manifest...`。
4. 选择本目录里的 `manifest.json`。
5. 再次进入 `Plugins` -> `Development`，运行 `采集数据看板导入器`。

运行后会生成一个名为 `采集数据看板 / Codex Import` 的 Frame，包含 KPI、Top5 任务、一级场景分布和每日车辆状态等可编辑图层。

如果只需要视觉参考，可以直接把 `collection-dashboard-desktop.png` 拖进 Figma。

## 重新生成

看板数据更新后，在当前目录执行：

```powershell
node build-figma-plugin.js
node capture-dashboard.js
```
