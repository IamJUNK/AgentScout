# 改造实施与技术决策 · 2026-10-17

## 起点与授权

用户已授权按 MySQL + NiceGUI 执行计划实施，并授权安装 Docker / WSL，以及最多 5 个真实任务、合计预留 150,000 Token、20 次搜索。基线 08a5ac9，原有 85 项测试本轮重新运行通过（7.63 秒）。分支为 `codex/agentscout-business-upgrade`；本地验收时未提交或推送；用户随后于 2026-10-17 授权发布到 GitHub。

Windows 还原后的目录含新旧混合代码与未跟踪模块。逐项核验后接入，没有把残留文件当已验收。原 `.env`、原数据库、个人 QA / 学习文档、历史结果保持原状。测试新建隔离环境 `.venv-upgrade`，正式服务测试在独立 `agentscout-validation` Compose 项目。

## 业务边界

- MySQL 是唯一正式业务数据库；SQLite 接口改为只读，迁移使用 URI mode=ro / query_only，默认 dry-run。核心调试与单元测试只用内存存储。
- NiceGUI 和 HTTP API 共享 TaskService，阻塞数据库操作离开 UI 事件循环；Celery 仅接收尝试 ID。Redis 只作代理，不作业务结果库。
- 每次尝试的执行令牌和心跳隔离重复消息/迟到写入；终态、报告在同一事务落库。无自动图断点恢复。
- 任务级 Token 和搜索预算累计所有尝试；未知用量保守占用，不能以重试重置预算。金额只是估算，并非精确账单上限。
- 官方来源用用户可见的 HTTPS 前缀；论坛、重定向最终地址、摘要和正文分别判断。空前缀时不猜测“官方”。

## 依赖与安装

Windows 安装、Linux 容器构建和 pip check 均实际执行。NiceGUI 3.18.0、FastAPI 0.143.3、SQLAlchemy 2.0.55、Alembic 1.20.0、Celery 5.6.3；完整版本见 requirements.lock，Linux 专用 uvloop 有平台标记。

Docker Desktop 已安装；WSL 官方 MSI 使用分段下载完成，经 Microsoft Corporation 有效 Authenticode 签名后安装，退出码 0。WSL 3.0.3.0，Docker Linux Engine 29.8.2。VirtualMachinePlatform 原已启用，Hypervisor 正常；未重启电脑。早先 Win32_Processor 的 False 不应单独解读为 BIOS 虚拟化关闭。

WSL MSI SHA-256：`AE977286974255BD26BF925F00F40F5692C6B2084155CBC0563C09AEA091F211`。用户提供的 Ubuntu APPX 镜像地址当时返回 404；Ubuntu 发行版与 WSL MSI 是不同组件，此次没有安装额外 Ubuntu，也没有修改 apt 软件源。

Compose 实测镜像：python:3.12.12-slim-bookworm、mysql:8.4.6、redis:7.4.6-alpine。测试 Web 仅 127.0.0.1:8081，正式配置默认 8080；MySQL / Redis 无宿主端口。原有数据未导入。

## Embedding 决策

选择 FastEmbed CPU 的 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2，384 维，Apache-2.0 元数据。明确下载步骤、模型文件哈希；研究期间不自动下载。按真实 tokenizer 进行 120 Token / 16 overlap 分窗再聚合，避免模型窗口截断遗漏尾部。

默认 BM25，用户显式选混合检索。本轮本地 Embedding 在 Windows 及 Linux 可选镜像实际运行通过；Linux 以断网、只读模型挂载验证，未下载或付费调用；API Embedding 为独立可选接口，只有隔离测试，没有真实供应商验证。无独立向量数据库，不维护跨任务向量索引；同一模型实例在 Worker 内复用，不宣称所有内容跨轮嵌入都已有持久缓存。

固定 8 条检索夹具为助手编写，开发/冻结各 4 条，在实现期间建立，未人工独立标注。冻结集混合 Recall@3 / MRR = 1 / 1；开发集混合 MRR .625，低于纯向量 .875。保留退化结果，不把数据当通用事实准确率。

## 当前交付

研究契约、抓取检索、MySQL 迁移、异步状态机、NiceGUI、Compose、CI 配置与验收脚本已落地。真实测试证据及未完成实验见 [upgrade-validation.md](upgrade-validation.md)。全量质量改造受控对照与人工金标准尚缺；不能标记为所有计划实验都完成。
