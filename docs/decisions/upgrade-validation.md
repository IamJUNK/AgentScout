# 改造验收记录 · 2026-10-17

## 执行结果

| 项目 | 实测结果 | 证据 |
|---|---|---|
| 原始基线 | 85 passed，7.63 秒 | 实施起点记录 |
| Windows 离线回归 | 109 passed，14 skipped；跳过项为 MySQL / Linux 队列 | 本地 pytest 输出 |
| Linux 完整回归 | **123 passed，0 skipped，10.22 秒（最终代码复验）** | `data/upgrade-local/linux-tests-final.log` |
| Alembic | 0001→0002→0003 成功；check 无新操作 | 同上 |
| 安装兼容性 | Windows / Linux pip check 通过，Docker image build 成功 | 构建日志、requirements.lock |
| 真实服务页面 | 提交→Worker→报告→证据→下载→双会话→重试历史通过 | `data/upgrade-local/service-ui.json` |
| 故障验收 | queued 取消、Redis 不可用后自动补发、全部容器重启保留报告通过 | `data/upgrade-local/service-faults.json` |
| 可选本地向量容器 | pip check、断网推理、长文条件、元数据持久化通过 | `data/upgrade-local/embedding-container.log` |
| 收尾定向回归 | 23 passed，2.48 秒 | retrieval / quality / workflow / UI |
| 远端 CI / GitHub | 上述本地验收截止时未运行；用户随后于 2026-10-17 授权发布 | 远端实际状态以 GitHub Actions 为准 |

服务测试只使用 Mock 研究，但 MySQL、Redis、Celery Worker、浏览器均为真实进程。真实付费研究验证的是核心研究流程；本轮未把付费请求再经完整服务重复跑一次。

## 故障与状态不变量

- 并发相同幂等键只创建一个任务；不同请求冲突，大小写键区分。
- 重复投递只能取得一个有效令牌；失败后的旧令牌、迟到保存被拒绝。
- 最终报告插入失败回滚尝试终态；不会显示成功而缺少报告。
- 运行中取消、真实 Linux Worker 协作停止、Worker SIGSTOP / kill 后失效与预算保留均通过。Worker 故障测试在专用进程中加等待门，实测进程和数据库语义；未声称覆盖每一种外部 API 故障。
- 累计搜索预算与 Token 预算不能由重试绕过；Legacy 重复导入跳过，相同旧 ID 不同内容冲突。
- Redis 暂停时提交耗时 4.031 秒，状态 pending_dispatch；恢复后正常调度补发，dispatch_count=2。没有手动发布目标消息。
- 排队取消后新建 Attempt 成功；MySQL / Redis / Web / Worker / Reconciler 重启后原报告完全一致。

## 5 次授权真实任务（全部保留）

| 任务 | 研究状态 | 已知 Token | 搜索 | 模型调用 | 观察 |
|---|---|---:|---:|---:|---|
| WAL 首次 | partial | 22,188 | 4 | 5 | 暴露来源要求错误拆题、翻译页挤占原文和逐字引文问题 |
| WAL 修正后 | completed | 14,773 | 4 | 4 | 两个问题分别回答，使用官方正文；仍需人工核对复合结论 |
| 仅材料双问题 | completed | 4,632 | 0 | 4 | 未搜索，分别回答写入者与未知费用 |
| 矛盾且无日期材料 | partial | 5,926 | 0 | 5 | 保留冲突，不猜测当前限额 |
| 长文后部与条件 | completed | 8,378 | 0 | 4 | 混合检索入选 11,201–11,280 位置，保留适用条件 |

合计 **55,897 已知 Token、8 次搜索、22 次模型调用**；5 个名额全部用完，预留 150,000 Token。未知 Token 预留 0；价格/实际账单金额未验证，不表示免费。每次请求内容、搜索结果和代码不同，不能计算通用准确率或宣称受控提升。日志在已忽略的 `data/upgrade-local/`；公开汇总仅列必要指标，不包含密钥。

## 固定资料检索实验

8 条跨语言合成夹具，4dev / 4frozen；同语料、问题和 top-3 计算 Recall 与首个相关片段倒数排名。

| 集合 | BM25 Recall@3 / MRR | Dense | Hybrid RRF |
|---|---|---|---|
| dev | 0 / 0 | 1 / .875 | 1 / .625 |
| frozen | .25 / .25 | 1 / 1 | 1 / 1 |

原始结果 `evals/results/retrieval-upgrade.json`。首次本地嵌入记录 2.185 秒；不是完整任务延迟。检索夹具为助手编写、待独立人工复核。分集是在实施期间建立，不满足原计划“所有质量调优前冻结”的严格时序；这是明确偏差。未进行旧系统/质量改造/混合检索三组同模型同资料的完整受控回答实验，当前预算也不能新增付费任务。

## 重跑步骤

1. 启动 Docker Linux 引擎。
2. 创建本地 `data/upgrade-local/validation.env`，其中 LLM_API_KEY、LLM_MODEL、TAVILY_API_KEY、EMBEDDING_API_KEY 为空。
3. `docker compose --env-file data/upgrade-local/validation.env -p agentscout-validation -f compose.yaml -f compose.test.yaml build test`
4. 同参数 `up -d mysql redis`；然后 `run --rm --no-deps test sh -c 'alembic upgrade head && alembic check && pip check && pytest -q'`。
5. 同参数 `up -d --no-build web worker reconciler`；执行 `node scripts/check_service_ui.cjs`。
6. 明确故障注入：`python scripts/check_service_faults.py --apply`。仅针对上述测试项目，脚本验证空密钥和测试库。

`tests/integration/` 使用 agentscout_test 和 Redis DB15；绝不能把 TEST_DATABASE_URL 指向用户业务库。测试 Web 使用 8081；正式服务默认8080。

## 当前限制

无独立人工金标准；同模型语义核验可能误判，原子结论约束并非确定性语义验证。Prompt injection 没有绝对免疫保证。未知调用费用按保守预留处理，实际账单可能不同。只读 legacy 导出会移除 config/settings，但历史正文/报告仍可能含用户资料，不应未经审查公开。

本地混合检索已在 Windows 和 Linux 可选 FastEmbed 镜像中运行。Linux 容器使用 network=none、模型目录只读挂载，384 维向量、hybrid_rrf、13,056–13,663 字符后部片段与条件保留均通过，模型调用/搜索均为 0；因未配置写作模型，结果正确保持 partial。FastEmbed 提示缓存文件大小元数据不一致，但本地模型载入和离线推理成功，未触发网络下载；已重新核对准备脚本 manifest 的 7 个文件 SHA-256，全部一致。API Embedding 未做付费供应商验证。备份恢复演练、压力测试、公网安全、多租户、LangGraph 任意节点断点恢复不在已通过范围。
