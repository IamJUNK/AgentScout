from agent.fallback import prepare_brief, plan_research_fallback
from agent.nodes import AgentNodes
from config import Settings


def test_manufacturing_request_is_not_rewritten_as_career_advice():
    text = "研究中国制造业岗位技能要求变化的原因，不需要求职或面试建议。"
    nodes = AgentNodes(Settings(), {"mock": True})
    state = {"input_text": text}
    state.update(nodes.prepare_research(state))
    plan = nodes.plan_research(state)["plan"]
    assert state["brief"]["original_request"] == text
    assert state["topic"] == text
    assert len(plan["questions"]) == 1
    assert plan["questions"][0]["queries"] == [text]
    assert "AI Agent" not in str(plan)


def test_fallback_preserves_exclusions():
    text = "只分析 SQLite 的单机写入限制，不比较云数据库。"
    assert plan_research_fallback(text).questions[0].text == text
    assert prepare_brief(text).original_request == text


def test_no_search_instruction_is_honored():
    assert not prepare_brief("仅使用提供材料回答，不要联网").allow_web_research
    assert not prepare_brief("Only use the supplied material").allow_web_research
    assert prepare_brief("研究在线搜索工具").allow_web_research


def test_time_scope_is_preserved():
    brief = prepare_brief("截至2024年，比较 SQLite 与其他方案，不使用2025年数据。")
    assert "2024" in brief.time_scope and "2025" in brief.time_scope
    assert prepare_brief("最新 SQLite 发布情况").freshness_required
