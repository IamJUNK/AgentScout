from __future__ import annotations
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st
from agent.graph import run_research
from config import ROOT, load_settings, safe_error
from evals.judge import attach_judge
from evals.runner import run_evaluation
from storage.database import RunStore

st.set_page_config(page_title="AgentScout", page_icon=":mag:", layout="wide")
st.title("AgentScout")
settings, store = load_settings(), RunStore()
st.session_state.setdefault("busy", False)
st.session_state.setdefault("comparisons", [])
STATUS = {"completed": "研究完成", "partial": "部分结果", "needs_review": "需要复核", "insufficient_evidence": "证据不足", "demo": "演示资料", "failed": "执行失败", "running": "运行中", "legacy": "旧版记录（原指标口径）"}


def mark_busy(action):
    st.session_state.busy = True
    st.session_state.pending_action = action


def display_time(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S") if value else "未知"


def show_run(run, scope):
    status = run.get("status", "legacy")
    st.info(STATUS.get(status, status))
    for error in run.get("errors", []): st.error(error)
    for warning in run.get("warnings", []): st.warning(warning)
    if run.get("citation_warning"): st.warning(run["citation_warning"])
    metrics = run.get("citation_metrics", {})
    columns = st.columns(5)
    for col, label, value in zip(columns, ["研究耗时", "研究 Token", "研究估算成本", "正文引用来源", "段落引用率"], [f"{run.get('total_duration_ms', 0)/1000:.2f}s", run.get("token_usage", 0), f"USD {run.get('estimated_cost', 0):.6f}", metrics.get("cited_sources", 0), f"{metrics.get('citation_coverage', 0):.0%}"]):
        col.metric(label, value)
    price = run.get("config", {}).get("settings", {}).get("price_per_million_tokens")
    if run.get("token_usage") and not price: st.warning("本次研究未记录有效单价，成本数值不代表实际费用。")
    if run.get("cost_incomplete"): st.warning("部分失败请求无 usage，实际费用未知。")
    st.caption("段落引用率是结构检查，不代表事实正确。发布日期未知时，不以抓取日期替代。")
    if run.get("report"):
        st.markdown(run["report"])
        st.download_button("下载 Markdown", run["report"], file_name=f"agentscout-{run['run_id'][:8]}.md", mime="text/markdown", key=f"download-{scope}-{run['run_id']}")
    with st.expander("研究需求与计划"):
        st.json({"brief": run.get("brief", {}), "plan": run.get("plan", {}), "stop_reason": run.get("stop_reason")})
    with st.expander("证据覆盖与质量检查"):
        st.json({"questions": run.get("assessment", []), "selection": run.get("evidence_selection", {}), "citations": metrics, "report_review": run.get("report_review", {})})
    with st.expander("证据片段与来源"):
        for evidence in run.get("evidence", []):
            st.write(f"{evidence['id']} · {evidence['title']} · {evidence['kind']} · {evidence['start']}–{evidence['end']}")
            st.text(evidence["text"])
            st.caption(f"{evidence['url']} · 发布日期：{evidence.get('published_at') or '未知'} · 获取时间：{evidence['retrieved_at']}")
        st.json(run.get("source_documents", []), expanded=False)
    reviews = store.list_reviews(run["run_id"])
    if reviews:
        with st.expander("独立 Judge 评审（费用单列）"):
            st.json(reviews)


research, trace, evaluation = st.tabs(["Research", "Trace", "Evaluation"])
with research:
    with st.form("research_form"):
        text = st.text_area("研究需求", "比较 LangGraph、CrewAI 和 AutoGen 的适用场景", height=150, help="说明问题、时间范围、排除项和输出要求，无需选择任务类别。")
        supplied = st.text_area("可选：提供的研究材料", height=100, help="只使用该材料时，请在需求中明确说明。")
        columns = st.columns(4)
        count = columns[0].number_input("每个查询候选数", min_value=1, max_value=10, value=5)
        mock = columns[1].checkbox("Mock 演示（不验证真实研究质量）", value=settings.search_provider == "mock")
        judge = columns[2].checkbox("独立 LLM Judge（可能收费）", value=False)
        refresh = columns[3].checkbox("强制刷新网页缓存", value=False)
        model = st.text_input("模型名称", value=settings.llm_model)
        submitted = st.form_submit_button("开始研究", disabled=st.session_state.busy, on_click=mark_busy, args=("research",))
    if submitted or st.session_state.get("pending_action") == "research":
        st.session_state.pop("pending_action", None)
        try:
            with st.status("研究运行中", expanded=True):
                current = st.empty()
                result = run_research(text, supplied_text=supplied, mock=mock, search_count=int(count), model=model, force_refresh=refresh, settings=settings, store=store, on_node=lambda node: current.write(f"当前步骤：{node}"))
                if judge: attach_judge(result, text, settings, model, store=store)
                st.session_state.research_result = result
        except Exception as exc:
            st.session_state.last_error = safe_error(exc, settings)
        finally:
            st.session_state.busy = False
        st.rerun()
    if st.session_state.get("last_error"): st.error(st.session_state.pop("last_error"))
    if "research_result" in st.session_state: show_run(st.session_state.research_result, "research")

with trace:
    runs = store.list_runs()
    if not runs:
        st.info("暂无运行记录。")
    else:
        st.dataframe([{"run_id": r["run_id"], "时间（上海）": display_time(r["created_at"]), "输入": r["input_text"][:100], "状态": STATUS.get(r["status"], r["status"]), "耗时 ms": r["total_duration_ms"], "Token": r["token_usage"], "成本 USD": r["estimated_cost"]} for r in runs], hide_index=True, width="stretch")
        run_id = st.selectbox("选择运行", [r["run_id"] for r in runs])
        selected = store.get_run(run_id)
        if selected:
            events = [e for e in selected.get("traces", []) if e["event_type"] != "start"]
            if events:
                frame = pd.DataFrame(events)
                frame["started_at"] = pd.to_datetime(frame["started_at"], utc=True)
                frame["ended_at"] = pd.to_datetime(frame["ended_at"], utc=True)
                st.plotly_chart(px.timeline(frame, x_start="started_at", x_end="ended_at", y="node_name", color="event_type"), width="stretch")
                st.dataframe(frame, hide_index=True, width="stretch")
            with st.expander("运行详情"): show_run(selected, "trace")

with evaluation:
    st.caption("Mock 衡量流程行为；研究完成率只计入证据充分且通过报告检查的真实研究。关键词仅作辅助诊断。")
    with st.form("evaluation_form"):
        columns = st.columns(3)
        limit = columns[0].number_input("评测任务数量", min_value=1, max_value=20, value=10)
        eval_mock = columns[1].checkbox("Mock 评测", value=True)
        eval_judge = columns[2].checkbox("独立 Judge", value=False, key="eval_judge")
        variant = st.selectbox("报告表达策略（证据预算相同）", ["structured", "baseline"])
        eval_model = st.text_input("评测模型", value=settings.llm_model)
        run_eval = st.form_submit_button("运行评测集", disabled=st.session_state.busy, on_click=mark_busy, args=("evaluation",))
    if run_eval or st.session_state.get("pending_action") == "evaluation":
        st.session_state.pop("pending_action", None)
        try:
            progress = st.progress(0)
            result = run_evaluation(limit=int(limit), mock=eval_mock, variant=variant, model=eval_model, judge=eval_judge, settings=settings, store=store, on_progress=lambda current, total: progress.progress(current/total))
            st.session_state.comparisons.append(result)
            st.session_state.evaluation_result = result
        except Exception as exc:
            st.session_state.last_error = safe_error(exc, settings)
        finally:
            st.session_state.busy = False
        st.rerun()
    saved = []
    for path in sorted((ROOT / "evals" / "results").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") == 2: saved.append((path.name, data))
        except (ValueError, OSError):
            continue
    result = st.session_state.get("evaluation_result")
    if result is None and saved:
        selected = st.selectbox("已保存的新版评测", [name for name, _ in saved])
        result = next(data for name, data in saved if name == selected)
    if result:
        summary = result["summary"]
        columns = st.columns(4)
        for col, label, value in zip(columns, ["研究完成率", "流程执行率", "问题证据覆盖", "段落引用率"], [summary["completion_rate"], summary["execution_rate"], summary["avg_question_coverage"], summary["avg_citation_coverage"]]):
            col.metric(label, f"{value:.0%}")
        if summary.get("expected_behavior_rate") is not None:
            st.caption(f"离线预期行为通过率：{summary['expected_behavior_rate']:.0%}（检查演示/证据不足等预期状态，不代表研究答案质量）")
        frame = pd.DataFrame(result["results"])
        st.plotly_chart(px.bar(frame, x="task_id", y=["question_coverage", "citation_coverage"], barmode="group"), width="stretch")
        st.dataframe(frame.drop(columns=["review"], errors="ignore"), hide_index=True, width="stretch")
        task = st.selectbox("任务详情", [row["task_id"] for row in result["results"]])
        row = next(row for row in result["results"] if row["task_id"] == task)
        st.json(row)
        detail = store.get_run(row["run_id"]) or next((run for run in result.get("runs", []) if run and run["run_id"] == row["run_id"]), None)
        if detail:
            with st.expander("任务报告与来源"): show_run(detail, "evaluation")
        st.download_button("下载评测 JSON", json.dumps(result, ensure_ascii=False, indent=2), "evaluation.json", "application/json")
    comparisons = st.session_state.comparisons or [data for _, data in saved]
    if comparisons:
        st.subheader("模型与策略对比")
        st.dataframe([{"variant": r["variant"], "model": r["model"], "mock": r["mock"], **r["summary"]} for r in comparisons], hide_index=True, width="stretch")
