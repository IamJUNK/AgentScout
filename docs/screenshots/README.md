# 界面截图版本说明

## NiceGUI 改造版 · 2026-10-17

`nicegui-workbench.png`、`nicegui-report.png`、`nicegui-evidence.png`、`nicegui-trace.png`、`nicegui-mobile.png` 来自实际浏览器截图。使用本轮已保存的 WAL 真实结果，页面明确标注只读预览。拍照不重跑模型和搜索，也不证明 MySQL / Celery 完整链路已经通过。

检查桌面 1440×1000、手机 390×844、Markdown 下载、刷新和浏览器异常；原始结果在 `nicegui-capture.json`。

重拍：先运行 `python scripts/preview_saved.py PATH_TO_STATE.json`，再运行 `node scripts/capture_demo.cjs`。需要 Node、Playwright 包和 Chrome；这些是文档验收工具，不是应用依赖。截图会覆盖同名 NiceGUI 图片。

没有真实保存结果时，可运行 `python scripts/demo_app.py` 查看明确标注的 Mock 只读预览。

## 真实服务验收截图

`nicegui-service-mock.png` 来自独立 agentscout-validation 服务：真实 MySQL、Redis 和 Celery Worker，研究内容为明确标注的 Mock。浏览器提交、报告/证据、下载、刷新、双会话、重试与历史选择已通过；原始结果在本地 `data/upgrade-local/service-ui.json`，公开摘要在 `evals/results/upgrade-summary.json`。

## 历史 Streamlit 版 · 2026-10-13

`01-research.png` 至 `05-evaluation.png` 和 `capture.json` 保留原样，来自旧 Streamlit Mock 演示。它们不是当前入口，不能作为新版完成情况。docs 根目录更早的 PNG / demo.webm 同样属于历史资料。
