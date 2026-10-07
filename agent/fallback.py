from __future__ import annotations

import re
from typing import Any

from models.schemas import InputClassification, ResearchPlan


ROLE_RE = re.compile(r"(?:position|role|岗位|职位|招聘|intern|engineer|实习)", re.I)


def classify_input_fallback(text: str) -> InputClassification:
    clean = (text or "").strip()
    is_job = bool(ROLE_RE.search(clean)) and ("responsibil" in clean.lower() or "要求" in clean or "jd" in clean.lower() or len(clean.split()) > 35)
    target_role = None
    if is_job:
        m = re.search(r"(?:AI|ML|Agent|LLM|人工智能|算法)[^\n,，。;；]{0,30}(?:实习生|工程师|研究员|intern|engineer|岗位)", clean, re.I)
        target_role = m.group(0).strip() if m else "AI Agent 相关岗位"
    topic = clean if not is_job else (target_role or "AI Agent 岗位")
    return InputClassification(input_type="job_description" if is_job else "research_question", topic=topic, target_role=target_role)


def plan_research_fallback(text: str, classification: InputClassification | None = None, max_questions: int = 5) -> ResearchPlan:
    cls = classification or classify_input_fallback(text)
    topic = cls.topic or text.strip()
    if cls.input_type == "job_description":
        questions = [
            f"{topic} 的核心职责和日常工作是什么？",
            f"{topic} 需要哪些技术栈、模型和工具能力？",
            f"{topic} 的候选人应具备哪些项目或研究经验？",
            f"如何准备 {topic} 的面试与作品集？",
        ]
    else:
        questions = [
            f"{topic} 的定义、背景与核心概念是什么？",
            f"{topic} 的主要方案、工具或框架有哪些？",
            f"{topic} 中各方案的优缺点、适用场景和限制是什么？",
            f"{topic} 的实践建议、评估指标和常见风险是什么？",
        ]
    questions = questions[:max_questions]
    queries = []
    for q in questions:
        q = re.sub(r"\s+", " ", q).strip()
        if cls.input_type == "job_description":
            q = f"{q} {re.sub(r'\s+', ' ', text).strip()[:160]}"
        if q not in queries:
            queries.append(q)
    return ResearchPlan(questions=questions, search_queries=queries[:max_questions])


def estimate_tokens(text: str) -> int:
    return max(1, len((text or "").split()) * 2)

