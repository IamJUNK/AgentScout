from __future__ import annotations

import json
from typing import Any

from agent.citations import duplicate_citations, validate_report
from agent.fallback import classify_input_fallback, plan_research_fallback
from agent.llm import OpenAICompatibleClient, extract_json
from agent.prompts import PLAN_SYSTEM, REPORT_SYSTEM, BASELINE_REPORT_SYSTEM, STRUCTURED_REPORT_SYSTEM
from config import Settings, safe_error
from models.schemas import InputClassification, ResearchPlan, SearchResult, SourceDocument
from tools.search import MockSearchProvider, TavilySearchProvider, dedupe_results
from tools.webpage import fetch_pages


class AgentNodes:
    def __init__(self, settings: Settings, options: dict[str, Any]):
        self.settings, self.options = settings, options
        self.client = OpenAICompatibleClient(settings.llm_base_url, settings.llm_api_key, options.get("model") or settings.llm_model, settings.llm_timeout_seconds)

    def call_llm(self, state: dict, system: str, prompt: str) -> str:
        state["llm_call_count"] += 1
        text, tokens = self.client.chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        estimated = tokens is None
        if tokens is None:
            tokens = max(1, (len(system) + len(prompt) + len(text) + 1) // 2)
        state["token_usage"] += tokens
        cost = tokens * self.settings.price_per_million_tokens / 1_000_000
        state["estimated_cost"] += cost
        state["usage_estimated"] = state.get("usage_estimated", False) or estimated
        state.setdefault("llm_usage", []).append({"tokens": tokens, "estimated": estimated, "cost": cost})
        return text

    def classify_input(self, state: dict) -> dict:
        classification = classify_input_fallback(state["input_text"])
        mode = self.options.get("input_mode", "auto")
        if mode in {"research_question", "job_description"}:
            classification.input_type = mode
            if mode == "job_description":
                classification.target_role = classification.target_role or "AI Agent 岗位"
        if self.client.available and not self.options.get("mock", True):
            try:
                answer = self.call_llm(state, "Classify the task. Return JSON with input_type (research_question or job_description), topic, target_role.", state["input_text"])
                classification = InputClassification.model_validate(extract_json(answer))
                if mode != "auto":
                    classification.input_type = mode
            except Exception as exc:
                state["warnings"].append("Classification fallback: " + safe_error(exc, self.settings))
        return {**classification.model_dump(), "classification": classification.model_dump()}

    def plan_research(self, state: dict) -> dict:
        fallback = plan_research_fallback(state["input_text"], InputClassification.model_validate(state["classification"]))
        plan = fallback
        if self.client.available and not self.options.get("mock", True):
            try:
                plan = ResearchPlan.model_validate(extract_json(self.call_llm(state, PLAN_SYSTEM, state["input_text"])))
                plan.questions = list(dict.fromkeys(q.strip() for q in plan.questions if q.strip()))[:5]
                plan.search_queries = list(dict.fromkeys(q.strip() for q in plan.search_queries if q.strip()))[:5]
                if not 3 <= len(plan.questions) <= 5 or not 3 <= len(plan.search_queries) <= 5:
                    raise ValueError("Planner must return 3 to 5 distinct questions and queries")
                topic = state["topic"].strip()
                plan.search_queries = [query if topic.casefold() in query.casefold() else f"{topic[:120]} {query}" for query in plan.search_queries]
            except Exception as exc:
                plan = fallback
                state["warnings"].append("Planner fallback: " + safe_error(exc, self.settings))
        return {"plan": plan.model_dump()}

    def search_sources(self, state: dict) -> dict:
        searcher = MockSearchProvider() if self.options.get("mock", True) else TavilySearchProvider(api_key=self.settings.tavily_api_key)
        found, counts, failures = [], {}, []
        for query in state["plan"]["search_queries"]:
            state["search_call_count"] += 1
            try:
                results = searcher.search(query, max_results=self.options["search_count"])
                counts[query] = len(results)
                found.extend(results)
            except Exception as exc:
                counts[query] = 0
                failures.append(safe_error(exc, self.settings))
        state["search_counts"] = counts
        if failures:
            state["warnings"].append("搜索失败：" + "; ".join(dict.fromkeys(failures)))
        unique = dedupe_results(found, 10)
        if not unique:
            detail = " ".join(dict.fromkeys(failures)) if failures else "搜索没有返回可用来源。"
            raise RuntimeError("搜索未返回可用来源。" + detail + " 可切换 Mock 模式重试。")
        return {"search_results": [item.model_dump() for item in unique], "search_counts": counts}

    def fetch_pages(self, state: dict) -> dict:
        results = [SearchResult.model_validate(item) for item in state["search_results"]]
        if self.options.get("mock", True):
            documents = [SourceDocument(title=item.title, url=item.url, content=item.snippet[:8000], fetch_status="snippet_only") for item in results[:5]]
        else:
            documents = fetch_pages(results)
        state["warnings"].extend("抓取降级：" + doc.fetch_error for doc in documents if doc.fetch_error)
        rate = sum(doc.fetch_status == "success" for doc in documents) / len(documents) if documents else 0.0
        return {"source_documents": [doc.model_dump() for doc in documents], "fetch_success_rate": rate}

    def synthesize_report(self, state: dict) -> dict:
        if self.client.available and not self.options.get("mock", True):
            payload = json.dumps({"input": state["input_text"], "plan": state["plan"], "sources": state["source_documents"], "prompt_variant": self.options.get("prompt_variant", "structured")}, ensure_ascii=False)
            try:
                system = BASELINE_REPORT_SYSTEM if self.options.get("prompt_variant") == "baseline" else STRUCTURED_REPORT_SYSTEM
                report = self.call_llm(state, system, payload)
                if not report.strip():
                    raise ValueError("Model returned an empty report")
                return {"report": report}
            except Exception as exc:
                state["warnings"].append("Writer fallback: " + safe_error(exc, self.settings))
        return {"report": local_report(state, self.options.get("prompt_variant", "structured"))}

    def validate_citations(self, state: dict) -> dict:
        metrics = validate_report(state["report"], state["search_results"], state["source_documents"])
        if metrics.invalid_citations or metrics.uncited_claims:
            state["citation_repair_count"] = 1
            if self.client.available and not self.options.get("mock", True):
                try:
                    prompt = json.dumps({"report": state["report"], "issues": metrics.model_dump(), "allowed_sources": state["source_documents"]}, ensure_ascii=False)
                    state["report"] = self.call_llm(state, REPORT_SYSTEM + " 修复错误引用和无引用的发现，仅返回修复报告。", prompt)
                except Exception as exc:
                    state["warnings"].append("Citation repair failed: " + safe_error(exc, self.settings))
            else:
                state["report"] = local_report(state, "structured")
            metrics = validate_report(state["report"], state["search_results"], state["source_documents"])
        warning = "部分引用无效或关键发现缺少引用，请人工复核。" if metrics.invalid_citations or metrics.uncited_claims else None
        return {"citation_metrics": metrics.model_dump(), "citation_warning": warning, "duplicate_citation_urls": duplicate_citations(state["report"])}


def local_report(state: dict, variant: str = "structured") -> str:
    docs = state["source_documents"]
    if not docs:
        raise RuntimeError("No source documents available for report generation")
    selected = docs[:2] if variant == "baseline" else docs
    title = state["topic"].replace("\n", " ")[:120]
    lines = [f"# {title}", "", "## 摘要", "", "以下内容根据收集到的来源摘要整理；Mock 模式使用固定演示数据，不代表实时检索结果。" if state["config"]["mock"] else "以下内容为本地规则摘要，请复核完整原文。", "", "## 关键发现", ""]
    for i, document in enumerate(selected, 1):
        lines.append(f"- **{document['title']}**：{document['content'].replace(chr(10), ' ')[:1000]} [来源 {i}]({document['url']})")
    lines += ["", "## 分点分析", ""]
    for i, question in enumerate(state["plan"]["questions"]):
        document = selected[i % len(selected)]
        number = i % len(selected) + 1
        lines.append(f"- **{question}** 可参考 {document['title']} 的相关内容；具体适用性需要结合任务进一步验证。[来源 {number}]({document['url']})")
    lines += ["", "## 局限性", "", "- 来源内容可能过时；规则摘要不进行开放式推断，引用存在不等于事实正确。", "- 未经人工核实的结论不应用于关键决策；Mock 数据仅用于演示与离线规则测试。", "", "## 来源列表", ""]
    lines.extend(f"- [来源 {i}]({doc['url']})：{doc['title']}" for i, doc in enumerate(selected, 1))
    return "\n".join(lines)
