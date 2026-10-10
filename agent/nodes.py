from __future__ import annotations

import hashlib
import json
import math
import time
import httpx
from agent.citations import validate_report, duplicate_citations
from agent.evidence import select_evidence
from agent.fallback import prepare_brief, plan_research_fallback, estimate_tokens
from agent.llm import OpenAICompatibleClient, extract_json
from agent.prompts import PLAN_SYSTEM, ASSESS_SYSTEM, BASELINE_REPORT_SYSTEM, STRUCTURED_REPORT_SYSTEM, REVIEW_SYSTEM
from config import Settings, safe_error
from models.schemas import ResearchPlan, ResearchBrief, SearchResult, SourceDocument, EvidenceAssessment, ReportReview
from tools.search import MockSearchProvider, TavilySearchProvider, dedupe_results
from tools.webpage import fetch_page


class BudgetExceeded(RuntimeError):
    pass


def transient(exc):
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)) or (isinstance(exc, httpx.HTTPStatusError) and (exc.response.status_code == 429 or exc.response.status_code >= 500))


class AgentNodes:
    def __init__(self, settings: Settings, options: dict):
        self.settings, self.options = settings, options
        self.deadline = time.monotonic() + settings.research_timeout_seconds
        self.client = OpenAICompatibleClient(settings.llm_base_url, settings.llm_api_key, options.get("model") or settings.llm_model, settings.llm_timeout_seconds)

    @property
    def cloud(self):
        return self.client.available and not self.options.get("mock", True)

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def warn(self, state, message):
        if message not in state.setdefault("warnings", []):
            state["warnings"].append(message)

    def charge(self, state, tokens, estimated=False):
        state["token_usage"] += tokens
        cost = tokens * self.settings.price_per_million_tokens / 1_000_000
        state["estimated_cost"] += cost
        state["usage_estimated"] = state.get("usage_estimated", False) or estimated
        state.setdefault("llm_usage", []).append({"tokens": tokens, "estimated": estimated, "cost": cost})

    def call_llm(self, state, system, payload, max_tokens=None):
        prompt = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        max_tokens = max_tokens or self.settings.plan_max_tokens
        if estimate_tokens(system + prompt) + max_tokens > self.settings.context_token_budget:
            raise BudgetExceeded("请求超出上下文预算；保留需求，拒绝静默截断。")
        estimated_request = estimate_tokens(system + prompt) + max_tokens
        for attempt in range(2):
            reserved = state.get("unaccounted_token_budget", 0)
            projected_tokens = state["token_usage"] + reserved + estimated_request
            projected_cost = state["estimated_cost"] + (reserved + estimated_request) * self.settings.price_per_million_tokens / 1_000_000
            if projected_tokens > self.settings.max_total_tokens or (self.settings.max_cost_usd and projected_cost > self.settings.max_cost_usd):
                state["budget_exhausted"] = True
                raise BudgetExceeded("本次研究 Token 或成本预算不足，未发起新模型请求。")
            if self.settings.max_cost_usd and not self.settings.price_per_million_tokens:
                raise BudgetExceeded("配置了成本预算但未配置价格，不能可靠执行付费调用。")
            if self.remaining() <= 0 or state["llm_call_count"] >= self.settings.max_llm_calls:
                state["budget_exhausted"] = True
                raise BudgetExceeded("研究时间或模型调用预算耗尽。")
            state["llm_call_count"] += 1
            self.client.timeout = min(self.settings.llm_timeout_seconds, self.remaining())
            charged = False
            try:
                text, tokens = self.client.chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}], max_tokens=max_tokens)
                estimated = tokens is None
                self.charge(state, tokens if tokens is not None else estimate_tokens(system + prompt + text), estimated)
                charged = True
                if not text.strip():
                    raise ValueError("模型返回空结果。")
                return text
            except Exception as exc:
                if getattr(exc, "tokens", None) is not None:
                    self.charge(state, exc.tokens)
                elif not charged:
                    state["cost_incomplete"] = True
                    state["unaccounted_token_budget"] = state.get("unaccounted_token_budget", 0) + estimated_request
                if attempt == 0 and transient(exc) and self.remaining() > .25:
                    self.warn(state, "瞬时模型错误，有限重试一次。")
                    time.sleep(.2)
                    continue
                raise

    def prepare_research(self, state):
        brief = prepare_brief(state["input_text"])
        documents = []
        if state.get("supplied_text", "").strip():
            digest = hashlib.sha256(state["supplied_text"].encode()).hexdigest()[:12]
            documents.append(SourceDocument(title="用户提供的研究材料", url="user://material/" + digest, source_id="S" + digest, content=state["supplied_text"]).model_dump())
        return {"brief": brief.model_dump(), "topic": brief.objective, "input_type": "research", "plan": {}, "search_results": [], "source_documents": documents, "evidence": [], "assessment": [], "round": 0, "searched_queries": [], "attempted_urls": [], "search_counts": {}}

    def plan_research(self, state):
        plan = plan_research_fallback(state["input_text"])
        brief = ResearchBrief.model_validate(state["brief"])
        if self.cloud:
            try:
                data = extract_json(self.call_llm(state, PLAN_SYSTEM, {"original_request": state["input_text"], "brief": state["brief"], "budget": self.settings.max_questions}))
                plan = ResearchPlan.model_validate({"questions": data["questions"]})
                if len(plan.questions) > self.settings.max_questions:
                    raise ValueError("Plan exceeds configured question budget")
                seen = set()
                for i, q in enumerate(plan.questions, 1):
                    q.text = q.text.strip()
                    q.queries = list(dict.fromkeys(query.strip() for query in q.queries if query.strip()))
                    if not q.text or q.text.casefold() in seen or not q.queries:
                        raise ValueError("Plan contains empty or duplicate questions/queries")
                    seen.add(q.text.casefold())
                    q.id = f"q{i}"
                brief.objective = str(data.get("objective") or brief.objective)
                for key in ("scope", "constraints", "output_requirements"):
                    if key in data:
                        if not isinstance(data[key], list) or not all(isinstance(x, str) for x in data[key]):
                            raise ValueError("Invalid brief fields")
                        setattr(brief, key, list(dict.fromkeys(getattr(brief, key) + data[key])))
                brief.time_scope = brief.time_scope or str(data.get("time_scope") or "")
                brief.freshness_required = brief.freshness_required or bool(brief.time_scope)
            except Exception as exc:
                plan = plan_research_fallback(state["input_text"])
                brief = ResearchBrief.model_validate(state["brief"])
                self.warn(state, "规划降级，保留完整原始问题：" + safe_error(exc, self.settings))
        return {"brief": brief.model_dump(), "plan": plan.model_dump()}

    def search_sources(self, state):
        state["round"] += 1
        if not state["brief"]["allow_web_research"]:
            self.warn(state, "需求限制外部检索；仅处理用户提供的材料。")
            return {}
        questions = state["plan"]["questions"]
        if state["round"] == 1:
            schedules = [(q["id"], q["queries"]) for q in questions]
        else:
            schedules = [(a["question_id"], a.get("next_queries", [])) for a in state["assessment"] if a["status"] != "supported"]
        ordered = {}
        for index in range(max((len(qs) for _, qs in schedules), default=0)):
            for qid, queries in schedules:
                if index < len(queries):
                    query = queries[index].strip()
                    if query and query not in state["searched_queries"]:
                        ordered.setdefault(query, []).append(qid)
        provider = MockSearchProvider() if self.options["mock"] else TavilySearchProvider(api_key=self.settings.tavily_api_key)
        batches = []
        for query, qids in ordered.items():
            if self.remaining() <= 0 or state["search_call_count"] >= self.settings.max_search_calls:
                state["budget_exhausted"] = True
                break
            state["searched_queries"].append(query)
            results = []
            for attempt in range(2):
                if state["search_call_count"] >= self.settings.max_search_calls or self.remaining() <= 0:
                    state["budget_exhausted"] = True
                    break
                state["search_call_count"] += 1
                try:
                    results = provider.search(query, max_results=self.options["search_count"], timeout=min(10, self.remaining()))
                    break
                except Exception as exc:
                    self.warn(state, "搜索失败：" + safe_error(exc, self.settings))
                    if not (attempt == 0 and transient(exc) and self.remaining() > .25):
                        break
                    time.sleep(.2)
            state["search_counts"][query] = len(results)
            batch = []
            for raw in results:
                item = raw if isinstance(raw, SearchResult) else SearchResult.model_validate(raw)
                item.source_id = "S" + hashlib.sha256(item.url.encode()).hexdigest()[:12]
                item.question_ids = list(dict.fromkeys(item.question_ids + qids))
                item.queries = list(dict.fromkeys(item.queries + [query]))
                batch.append(item)
            batches.append(batch)
        # Interleave queries before candidate limits. Preserve provenance on duplicates.
        mixed = [batch[i] for i in range(max(map(len, batches), default=0)) for batch in batches if i < len(batch)]
        old = [SearchResult.model_validate(r) for r in state["search_results"]]
        if state["round"] > 1:
            # Make room for targeted follow-up results without losing acquired provenance.
            acquired = [r for r in old if r.url in state["attempted_urls"]]
            pending = [r for r in old if r.url not in state["attempted_urls"]]
            candidates = mixed + acquired + pending
        else:
            candidates = old + mixed
        results = dedupe_results(candidates, self.settings.max_candidates)
        return {"search_results": [r.model_dump() for r in results]}

    def fetch_pages(self, state):
        if not state["brief"]["allow_web_research"]:
            return {}
        remaining = self.settings.max_fetch_pages - len(state["attempted_urls"])
        rounds_left = max(1, self.settings.max_rounds - state["round"] + 1)
        allowance = min(remaining, max(len(state["plan"]["questions"]), math.ceil(remaining / rounds_left)))
        candidates = [r for r in state["search_results"] if r["url"] not in state["attempted_urls"]]
        qids = [a["question_id"] for a in state["assessment"] if a["status"] != "supported"] if state["assessment"] else [q["id"] for q in state["plan"]["questions"]]
        selected = []
        while candidates and len(selected) < allowance:
            changed = False
            for qid in qids:
                item = next((r for r in candidates if qid in r["question_ids"]), None)
                if item and len(selected) < allowance:
                    selected.append(item)
                    candidates.remove(item)
                    changed = True
            if not changed:
                break
        documents = list(state["source_documents"])
        for raw in selected:
            if self.remaining() <= 0:
                state["budget_exhausted"] = True
                break
            item = SearchResult.model_validate(raw)
            state["attempted_urls"].append(item.url)
            if self.options["mock"]:
                doc = SourceDocument(title=item.title, url=item.url, source_id=item.source_id, question_ids=item.question_ids, content=item.snippet, snippet=item.snippet, fetch_status="snippet_only", mock=True)
            else:
                doc = fetch_page(item, timeout_seconds=min(10, self.remaining()), max_bytes=self.settings.max_download_bytes, cache_ttl=self.settings.cache_ttl_seconds, force_refresh=self.options.get("force_refresh", False) or state["brief"]["freshness_required"], deadline=self.deadline)
            if doc.fetch_error:
                self.warn(state, "资料限制：" + safe_error(ValueError(doc.fetch_error), self.settings))
            documents.append(doc.model_dump())
        by_url = {r["url"]: r for r in state["search_results"]}
        for doc in documents:
            doc["question_ids"] = by_url.get(doc["url"], doc).get("question_ids", [])
        rate = sum(d["fetch_status"] == "success" for d in documents) / len(documents) if documents else 0.0
        return {"source_documents": documents, "fetch_success_rate": rate}

    def assess_evidence(self, state):
        overhead = estimate_tokens(json.dumps({"request": state["input_text"], "brief": state["brief"], "plan": state["plan"]}, ensure_ascii=False))
        evidence_budget = max(0, min(self.settings.evidence_token_budget, self.settings.context_token_budget - overhead - 2*self.settings.report_max_tokens - 1200))
        evidence, selection = select_evidence(state["source_documents"], state["plan"]["questions"], evidence_budget)
        fallback = []
        for q in state["plan"]["questions"]:
            ids = [e["id"] for e in evidence if q["id"] in e["question_ids"]]
            fallback.append({"question_id": q["id"], "status": "partial" if ids else "missing", "evidence_ids": ids, "explanation": "找到词法相关片段，尚未验证能否充分回答问题。" if ids else "没有找到可用的相关证据。", "next_queries": []})
        assessment = fallback
        if self.cloud and evidence:
            try:
                parsed = EvidenceAssessment.model_validate(extract_json(self.call_llm(state, ASSESS_SYSTEM, {"original_request": state["input_text"], "brief": state["brief"], "questions": state["plan"]["questions"], "evidence": evidence, "evidence_selection": selection}, self.settings.review_max_tokens)))
                required = {q["id"] for q in state["plan"]["questions"]}
                if {a.question_id for a in parsed.questions} != required or len(parsed.questions) != len(required):
                    raise ValueError("Assessment must cover each question exactly once")
                by_id = {e["id"]: e for e in evidence}
                for a in parsed.questions:
                    if any(eid not in by_id or a.question_id not in by_id[eid]["question_ids"] for eid in a.evidence_ids):
                        raise ValueError("Assessment cites unknown/unrelated evidence")
                    chosen = [by_id[eid] for eid in a.evidence_ids]
                    if a.status == "supported" and (not chosen or not any(e["kind"] in {"body", "user"} and not e["download_truncated"] for e in chosen)):
                        a.status = "partial"
                        a.explanation += " 只有摘要或不完整正文，不能判为充分支持。"
                    if a.status == "supported" and state["brief"]["time_scope"] and a.temporal_applicability != "confirmed":
                        a.status = "partial"
                        a.explanation += " 时间或版本适用性尚未确认。"
                assessment = [a.model_dump() for a in parsed.questions]
            except Exception as exc:
                self.warn(state, "证据评估降级：" + safe_error(exc, self.settings))
        return {"evidence": evidence, "evidence_selection": selection, "assessment": assessment}

    def should_research_more(self, state):
        if all(a["status"] == "supported" for a in state["assessment"]):
            state["stop_reason"] = "evidence_sufficient"
            return "synthesize_report"
        gaps = {a["question_id"] for a in state["assessment"] if a["status"] != "supported"}
        unread = any(r["url"] not in state["attempted_urls"] and gaps.intersection(r["question_ids"]) for r in state["search_results"])
        new_queries = any(q.strip() and q.strip() not in state["searched_queries"] for a in state["assessment"] if a["question_id"] in gaps for q in a["next_queries"])
        time_ok = self.remaining() > 0
        fetch_ok = len(state["attempted_urls"]) < self.settings.max_fetch_pages
        search_ok = state["search_call_count"] < self.settings.max_search_calls
        if state["brief"]["allow_web_research"] and state["round"] < self.settings.max_rounds and time_ok and fetch_ok and (unread or (new_queries and search_ok)):
            return "search_sources"
        limited = not time_ok or not fetch_ok or ((unread or new_queries) and state["round"] >= self.settings.max_rounds) or (new_queries and not search_ok)
        state["budget_exhausted"] = state.get("budget_exhausted", False) or limited
        state["stop_reason"] = "budget_exhausted" if limited else "evidence_gap"
        return "synthesize_report"

    def payload(self, state):
        return {"original_request": state["input_text"], "brief": state["brief"], "plan": state["plan"], "evidence": state["evidence"], "evidence_selection": state.get("evidence_selection", {}), "assessment": state["assessment"], "stop_reason": state.get("stop_reason"), "prompt_variant": self.options["prompt_variant"]}

    def synthesize_report(self, state):
        if self.cloud and state["evidence"]:
            try:
                system = BASELINE_REPORT_SYSTEM if self.options["prompt_variant"] == "baseline" else STRUCTURED_REPORT_SYSTEM
                report = self.call_llm(state, system, self.payload(state), self.settings.report_max_tokens)
                return {"report": report, "report_kind": "model_answer"}
            except Exception as exc:
                self.warn(state, "写作未完成，提供资料摘录：" + safe_error(exc, self.settings))
        return {"report": local_report(state), "report_kind": "evidence_digest"}

    def review(self, state, report):
        if not self.cloud or not state["evidence"] or state.get("report_kind") != "model_answer":
            return {"task_compliant": False, "complete": False, "supported": False, "issues": ["资料摘录未完成研究答案的语义验证。"]}
        try:
            result = ReportReview.model_validate(extract_json(self.call_llm(state, REVIEW_SYSTEM, {**self.payload(state), "report": report}, self.settings.review_max_tokens)))
            return result.model_dump()
        except Exception as exc:
            self.warn(state, "报告语义检查未完成：" + safe_error(exc, self.settings))
            return {"task_compliant": False, "complete": False, "supported": False, "issues": ["无法完成报告语义检查。"]}

    def validate_citations(self, state):
        original = state["report"]
        metrics = validate_report(original, evidence=state["evidence"])
        review = self.review(state, original)
        issues = len(metrics.invalid_citations) + len(metrics.uncited_claims)
        semantic_ok = all(review.get(k) for k in ("task_compliant", "complete", "supported")) and not review.get("issues")
        if self.cloud and state["evidence"] and state["report_kind"] == "model_answer" and (issues or not semantic_ok):
            state["citation_repair_count"] = 1
            try:
                system = BASELINE_REPORT_SYSTEM if self.options["prompt_variant"] == "baseline" else STRUCTURED_REPORT_SYSTEM
                candidate = self.call_llm(state, system + " 修复以下问题，保留全部原始约束、已有支持和未解答事项。", {**self.payload(state), "report": original, "issues": metrics.model_dump(), "review": review}, self.settings.report_max_tokens)
                checked = validate_report(candidate, evidence=state["evidence"])
                candidate_review = self.review(state, candidate)
                new_issues = len(checked.invalid_citations) + len(checked.uncited_claims)
                review_ok = all(candidate_review.get(k) for k in ("task_compliant", "complete", "supported")) and not candidate_review.get("issues")
                if candidate.strip() and new_issues <= issues and review_ok:
                    state["report"], metrics, review = candidate, checked, candidate_review
                else:
                    self.warn(state, "修复未通过质量检查，保留原报告。")
            except Exception as exc:
                self.warn(state, "修复失败，保留原报告：" + safe_error(exc, self.settings))
        warning = "存在未解决的引用或语义检查问题；不能视为已完成研究。" if metrics.invalid_citations or metrics.uncited_claims or not all(review.get(k) for k in ("task_compliant", "complete", "supported")) or review.get("issues") else None
        return {"citation_metrics": metrics.model_dump(), "report_review": review, "citation_warning": warning, "duplicate_citation_urls": duplicate_citations(state["report"])}

    def finalize(self, state):
        metrics, review = state.get("citation_metrics", {}), state.get("report_review", {})
        if not state["evidence"]:
            status = "insufficient_evidence"
        elif self.options["mock"]:
            status = "demo"
        elif state.get("report_kind") == "evidence_digest":
            status = "partial"
        elif any(a["status"] != "supported" for a in state["assessment"]):
            status = "partial"
        elif metrics.get("invalid_citations") or metrics.get("uncited_claims") or not all(review.get(k) for k in ("task_compliant", "complete", "supported")) or review.get("issues"):
            status = "needs_review"
        else:
            status = "completed"
        return {"status": status, "success": status == "completed", "execution_status": "finished"}


def local_report(state, variant=None):
    # A digest is explicit about its limitations; never fabricate per-question answers.
    lines = ["# 研究资料与未解答问题", "", "> 状态：演示资料摘录。" if state["config"]["mock"] else "> 状态：资料摘录，尚未完成研究答案。", "> 研究需求：" + state["input_text"].replace("\n", " "), "", "> 限制：片段按词法相关性筛选，相关不代表充分支持；日期未知时不能确认时效性。", ""]
    for question in state["plan"]["questions"]:
        lines += ["## " + question["text"].replace("\n", " "), ""]
        matched = [e for e in state["evidence"] if question["id"] in e["question_ids"]]
        if not matched:
            lines.append("> 未解答：未找到可用的相关证据。")
        for evidence in matched:
            kind = {"body": "正文片段", "snippet": "搜索摘要，未核实原文", "mock": "演示摘要", "user": "用户提供材料，未独立核实"}[evidence["kind"]]
            text = evidence["text"].replace("\n", " ")
            # Escape fixture/site Markdown so a quotation cannot alter report structure.
            for char in ("[", "]", "*", "_", "<", ">"):
                text = text.replace(char, "\\" + char)
            lines.append(f"- {kind}，{evidence['title']}（位置 {evidence['start']}–{evidence['end']}）：{text} [证据 {evidence['id']}]({evidence['url']})")
        assessment = next((a for a in state.get("assessment", []) if a["question_id"] == question["id"]), {})
        lines += ["> 未解答：" + assessment.get("explanation", "尚未完成答案验证。"), ""]
    if state.get("budget_exhausted"):
        lines.append("> 预算：本次预算耗尽，缺口不等于不存在答案。")
    return "\n".join(lines)
