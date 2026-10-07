from __future__ import annotations

import json
from pathlib import Path
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

settings = load_settings()
store = RunStore()
st.session_state.setdefault("busy", False)
st.session_state.setdefault("comparisons", [])

def mark_busy(action: str):
    st.session_state.busy = True
    st.session_state.pending_action = action

def display_time(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def show_run(run: dict, scope: str):
    if run.get("errors"):
        for error in run["errors"]:
            st.error(error)
    for warning in run.get("warnings", []):
        st.warning(warning)
    if run.get("citation_warning"):
        st.warning(run["citation_warning"])
    cols = st.columns(5)
    cols[0].metric("耗时", f"{run.get('total_duration_ms', 0) / 1000:.2f}s")
    cols[1].metric("Token", run.get("token_usage", 0))
    cols[2].metric("估算成本", f"${run.get('estimated_cost', 0):.6f}")
    metrics = run.get("citation_metrics", {})
    if run.get("token_usage", 0) and settings.price_per_million_tokens == 0:
        st.warning("模型价格未配置，当前成本数值不代表实际费用。")
    cols[3].metric("有效来源", metrics.get("cited_sources", 0))
    cols[4].metric("引用覆盖率", f"{metrics.get('citation_coverage', 0):.0%}")
    if run.get("report"):
        st.markdown(run["report"])
        st.download_button("下载 Markdown", run["report"], file_name=f"agentscout-{run['run_id'][:8]}.md", mime="text/markdown", icon=":material/download:", key=f"download-{scope}-{run['run_id']}")
    with st.expander("来源与引用校验"):
        st.json(metrics)
        for document in run.get("source_documents", []):
            st.markdown(f"[{document['title']}]({document['url']}) · `{document['fetch_status']}`")
            st.text(document["content"][:600])
        duplicates = run.get("duplicate_citation_urls", [])
        if duplicates:
            st.caption(f"{len(duplicates)} 个 URL 在正文和来源列表中重复引用；指标按唯一 URL 计数。")
    with st.expander("研究计划"):
        st.json(run.get("plan", {}))
    if run.get("judge"):
        with st.expander("LLM Judge"):
            st.json(run["judge"])


research, trace, evaluation = st.tabs(["Research", "Trace", "Evaluation"])
with research:
    with st.form("research_form"):
        mode = st.radio("输入类型", ["研究主题", "岗位描述"], horizontal=True)
        text = st.text_area("研究主题 / 岗位描述", "比较 LangGraph、CrewAI 和 AutoGen 的适用场景", height=150)
        columns = st.columns(4)
        count = columns[0].number_input("每个查询结果数", min_value=1, max_value=10, value=5)
        mock = columns[1].checkbox("Mock 搜索与规则报告", value=settings.search_provider == "mock")
        judge = columns[2].checkbox("启用 LLM Judge", value=False)
        cache = columns[3].checkbox("使用已有结果缓存", value=False)
        model = st.text_input("模型名称", value=settings.llm_model)
        submitted = st.form_submit_button("开始研究", disabled=st.session_state.busy, icon=":material/search:", on_click=mark_busy, args=("research",))
    if submitted or st.session_state.get("pending_action") == "research":
        st.session_state.pop("pending_action", None)
        st.session_state.busy = True
        try:
            with st.status("研究运行中", expanded=True) as status:
                current = st.empty()
                result = run_research(text, mock=mock, search_count=int(count), model=model, input_mode="job_description" if mode == "岗位描述" else "research_question", use_cache=cache, settings=settings, store=store, on_node=lambda node: current.write(f"当前节点：{node}"))
                if judge and result.get("report"):
                    attach_judge(result, text, settings, model)
                    store.save_run(result)
                st.session_state.research_result = result
                status.update(label="研究完成" if result["success"] else "研究失败", state="complete" if result["success"] else "error", expanded=False)
        except Exception as exc:
            st.session_state.last_error = safe_error(exc, settings)
        finally:
            st.session_state.busy = False
        st.rerun()
    if st.session_state.get("last_error"):
        st.error(st.session_state.pop("last_error"))
    if "research_result" in st.session_state:
        show_run(st.session_state.research_result, "research")

with trace:
    runs = store.list_runs()
    if not runs:
        st.info("暂无运行记录。")
    else:
        records = [{"run_id": r["run_id"], "时间（上海）": display_time(r["created_at"]), "输入": r["input_text"][:100], "状态": "失败" if r["errors"] else "成功", "耗时 ms": r["total_duration_ms"], "Token": r["token_usage"], "成本 USD": r["estimated_cost"]} for r in runs]
        st.dataframe(records, hide_index=True, width="stretch")
        run_id = st.selectbox("选择运行", [r["run_id"] for r in runs], format_func=lambda selected: next(f"{display_time(r['created_at'])} · {r['input_text'][:50]} · {selected[:8]}" for r in runs if r["run_id"] == selected))
        selected = store.get_run(run_id)
        st.code(run_id)
        events = [event for event in selected["traces"] if event["event_type"] != "start"]
        if events:
            timeline = pd.DataFrame(events)
            timeline["started_at"] = pd.to_datetime(timeline["started_at"], utc=True).dt.tz_convert("Asia/Shanghai")
            timeline["ended_at"] = pd.to_datetime(timeline["ended_at"], utc=True).dt.tz_convert("Asia/Shanghai")
            chart = px.timeline(timeline, x_start="started_at", x_end="ended_at", y="node_name", color="event_type", color_discrete_map={"success": "#168a65", "error": "#d94948"}, hover_data=["duration_ms", "token_usage", "error_message"])
            chart.update_yaxes(autorange="reversed")
            st.plotly_chart(chart, width="stretch")
            st.dataframe([{k: e.get(k) for k in ["node_name", "event_type", "duration_ms", "llm_calls", "search_calls", "token_usage", "estimated_cost", "output_summary", "error_message"]} for e in events], hide_index=True, width="stretch")
        st.caption(f"LLM 调用：{selected.get('llm_call_count', 0)} · 搜索调用：{selected.get('search_call_count', 0)} · 抓取成功率：{selected.get('fetch_success_rate', 0):.0%}")
        with st.expander("运行详情"):
            show_run(selected, "trace")

with evaluation:
    with st.form("evaluation_form"):
        columns = st.columns(3)
        limit = columns[0].number_input("评测任务数量", min_value=1, max_value=20, value=10)
        eval_mock = columns[1].checkbox("Mock 评测", value=True)
        eval_judge = columns[2].checkbox("LLM Judge", value=False, key="eval_judge")
        variant = st.selectbox("Prompt / 规则摘要策略", ["structured", "baseline"])
        eval_model = st.text_input("评测模型", value=settings.llm_model)
        run_eval = st.form_submit_button("运行评测集", disabled=st.session_state.busy, icon=":material/play_arrow:", on_click=mark_busy, args=("evaluation",))
    if run_eval or st.session_state.get("pending_action") == "evaluation":
        st.session_state.pop("pending_action", None)
        st.session_state.busy = True
        try:
            progress = st.progress(0)
            result = run_evaluation(limit=int(limit), mock=eval_mock, variant=variant, model=eval_model, judge=eval_judge, settings=settings, store=store, on_progress=lambda current, total: progress.progress(current / total))
            st.session_state.comparisons.append(result)
            st.session_state.evaluation_result = result
        except Exception as exc:
            st.session_state.last_error = safe_error(exc, settings)
        finally:
            st.session_state.busy = False
        st.rerun()
    saved = sorted((ROOT / "evals" / "results").glob("*.json")) if (ROOT / "evals" / "results").exists() else []
    if "evaluation_result" not in st.session_state and saved:
        chosen = st.selectbox("已保存的评测", saved, format_func=lambda path: path.name)
        result = json.loads(chosen.read_text(encoding="utf-8"))
    else:
        result = st.session_state.get("evaluation_result")
    if result:
        summary = result["summary"]
        cols = st.columns(4)
        for col, label, value in zip(cols, ["完成率", "关键词召回率", "引用覆盖率", "平均来源数"], [f"{summary['completion_rate']:.0%}", f"{summary['avg_keyword_recall']:.0%}", f"{summary['avg_citation_coverage']:.0%}", f"{summary['avg_source_count']:.1f}"]):
            col.metric(label, value)
        cols = st.columns(3)
        cols[0].metric("平均延迟", f"{summary['avg_latency_ms']:.1f} ms")
        cols[1].metric("平均成本", f"${summary['avg_cost']:.6f}")
        cols[2].metric("失败任务", summary["failed_tasks"])
        frame = pd.DataFrame(result["results"])
        st.plotly_chart(px.bar(frame, x="task_id", y=["keyword_recall", "citation_coverage"], barmode="group", color_discrete_sequence=["#168a65", "#dd594c"]), width="stretch")
        st.dataframe(frame.drop(columns=["judge", "judge_usage"], errors="ignore"), hide_index=True, width="stretch")
        failed = [row for row in result["results"] if not row["completed"]]
        with st.expander(f"失败样例 ({len(failed)})"):
            st.json(failed)
        task_id = st.selectbox("任务详情", [row["task_id"] for row in result["results"]])
        row = next(row for row in result["results"] if row["task_id"] == task_id)
        st.json(row)
        detail = store.get_run(row["run_id"])
        if detail:
            with st.expander("任务报告与来源"):
                show_run(detail, "evaluation")
        st.download_button("下载评测 JSON", json.dumps(result, ensure_ascii=False, indent=2), "evaluation.json", "application/json", icon=":material/download:")
    comparison_runs = st.session_state.comparisons or [json.loads(path.read_text(encoding="utf-8")) for path in saved]
    if comparison_runs:
        st.subheader("模型与策略对比")
        comparison_rows = [{"variant": r["variant"], "model": r["model"], "mock": r["mock"], **r["summary"]} for r in comparison_runs]
        st.dataframe(comparison_rows, hide_index=True, width="stretch")
