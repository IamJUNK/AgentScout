# 新版界面截图

拍摄日期：2026-10-13。截图来自当前 `app.py` 的实际浏览器操作，没有修改页面指标或伪造报告内容。全部采用 Mock 演示与离线评测，独立 Judge 关闭，不使用真实密钥或付费服务。

| 文件 | 内容 |
|---|---|
| [01-research.png](01-research.png) | 研究需求、可选材料及模式选择 |
| [02-report.png](02-report.png) | 演示资料状态、引用、警告与 Markdown 下载 |
| [03-evidence.png](03-evidence.png) | 展开的证据片段、类型、来源及原文位置 |
| [04-trace.png](04-trace.png) | 节点时间线与事件类型 |
| [05-evaluation.png](05-evaluation.png) | 20 条 Mock 任务的当前指标口径 |

截图中的零 Token、低耗时和零估算费用仅属于 Mock。图中段落引用率不代表事实正确，研究完成率为零也不是程序执行失败。真实联网结果见 [SQLite WAL 验证](../../data/live-validation-2026-10-13/README.md)。

## 重新拍摄

需要项目 Python 依赖、Node.js、可由 Node 解析到的 Playwright 包，以及已安装的 Google Chrome。Playwright 仅用于文档截图，不是应用运行依赖。

在项目根目录启动隔离演示入口：

```powershell
.\.venv\Scripts\python.exe -m streamlit run scripts/demo_app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
```

另开终端运行：

```powershell
node scripts/capture_demo.cjs
```

演示入口使用空密钥配置，跳过 `.env` 并将数据写入 `data/readme-demo.db`。截图脚本显式选择 Mock，关闭两个 Judge，等待页面完成渲染；输出至本目录并覆盖同名图片，记录元数据至 `capture.json`。生成前请确认不需要保留这些截图的旧版本。

研究视图为 1440 × 1000，评测视图为 1440 × 1200；证据和轨迹直接截取对应组件，其他图片截取相关页面区域。旧版图片和 `demo.webm` 保留在 docs 根目录，仅作历史材料。
