from __future__ import annotations
import math
import re
from models.schemas import ResearchBrief, ResearchPlan, ResearchQuestion


def prepare_brief(text: str) -> ResearchBrief:
    clean = text.strip()
    if not clean:
        raise ValueError("请输入研究需求。")
    sentences = [s.strip() for s in re.split(r"[。；\n]", clean) if s.strip()]
    constraints = [s for s in sentences if re.search(r"不要|不需要|仅|只使用|禁止|不得|do not|only|must not", s, re.I)]
    times = re.findall(r"20\d{2}(?:[-年/]\d{1,2})?(?:[-月/]\d{1,2})?|最新|最近|当前|今天|昨天|今年|去年|today|yesterday|this year|last year|截至[^，。；\n]+|latest|current|recent", clean, re.I)
    no_web = bool(re.search(r"(?:不要|禁止|不得|无需)(?:联网|搜索|检索)|不联网|do not (?:browse|search)|offline only|仅(?:使用|根据|依据).*(?:提供|给定)|只(?:使用|根据|依据).*(?:提供|给定)|only (?:use|using) (?:the )?(?:supplied|provided)", clean, re.I))
    return ResearchBrief(original_request=clean, objective=clean, constraints=constraints, time_scope="; ".join(times), freshness_required=bool(times), allow_web_research=not no_web)


def plan_research_fallback(text: str, max_questions: int = 8) -> ResearchPlan:
    # Preserve the request instead of inventing background/career questions.
    clean = text.strip()
    return ResearchPlan(questions=[ResearchQuestion(id="q1", text=clean, queries=[clean])])


def estimate_tokens(text: str) -> int:
    """Conservative mixed-language budget estimate, not a tokenizer guarantee."""
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    return max(1, cjk + math.ceil((len(text) - cjk) / 3))
